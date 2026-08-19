import time
import os
import cv2
from src.logger import get_logger

logger = get_logger(__name__)

class SumberVideo:
    """
    Wrapper di atas cv2.VideoCapture yang menangani reconnect otomatis
    jika koneksi RTSP terputus. Ini PENTING untuk kamera IP di lapangan -
    tanpa ini, program akan crash atau macet total begitu koneksi
    jaringan sempat putus sesaat.
    """

    def __init__(self, config, kamera_config):
        mode = kamera_config.get("source_type") or config.get("video_source.mode", "file")
        
        if mode == "rtsp" or mode == "stream":
            source = kamera_config.get("rtsp_url") or config.get("video_source.rtsp_url")
        else:
            source = kamera_config.get("source") or kamera_config.get("file_path") or config.get("video_source.file_path")
            
        if source and source.startswith("${") and source.endswith("}"):
            env_var = source[2:-1]
            source = os.environ.get(env_var, source)

        if mode == "rtsp" or mode == "stream":
            self.source = source
            logger.info(f"[VIDEO] Mode RTSP - menghubungkan ke kamera IP: {self._sensor_url(self.source)}")
        else:
            self.source = source
            logger.info(f"[VIDEO] Mode File - membuka video: {self.source}")

        self.mode = mode
        self.width = config.get("video_source.process_width", 960)
        self.height = config.get("video_source.process_height", 540)
        self.cap = None
        self.baru_saja_di_loop = False  # dicek oleh main.py setiap iterasi
        self._buka_koneksi()

    def _sensor_url(self, url: str) -> str:
        """Menyembunyikan password saat mencetak URL RTSP ke log/terminal."""
        if "@" in url and "://" in url:
            skema, sisa = url.split("://", 1)
            if "@" in sisa:
                kredensial, host = sisa.split("@", 1)
                return f"{skema}://***:***@{host}"
        return url

    def _buka_koneksi(self):
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            logger.warning("[VIDEO] Gagal membuka sumber video.")
            if self.mode == "rtsp":
                logger.warning(
                    "Kemungkinan penyebab: (1) URL RTSP salah, "
                    "(2) kamera tidak dalam jaringan yang sama, "
                    "(3) username/password salah, (4) firewall memblokir port 554."
                )
            else:
                logger.warning(
                    "Pastikan path file video benar dan file ada di lokasi tersebut."
                )

    def baca_frame(self):
        """
        Membaca satu frame. Jika gagal (mis. koneksi RTSP putus),
        mencoba reconnect otomatis sebelum menyerah.
        """
        if self.cap is None or not self.cap.isOpened():
            self._buka_koneksi()
            time.sleep(1)
            return None

        ret, frame = self.cap.read()
        if not ret:
            if self.mode == "rtsp":
                logger.warning("[VIDEO] Frame gagal dibaca, mencoba reconnect ke kamera...")
                self._buka_koneksi()
            else:
                logger.info("[VIDEO] Video mencapai akhir, memutar ulang dari awal...")
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self.baru_saja_di_loop = True
            return None

        frame = cv2.resize(frame, (self.width, self.height))
        return frame

    def lepas(self):
        if self.cap is not None:
            self.cap.release()
