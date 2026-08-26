"""
video_source.py
================
Wrapper di atas cv2.VideoCapture dengan THREADED FRAME GRABBER.

Arsitektur:
    [Camera/RTSP/File]
         ↓
    [Background Thread] → terus memanggil cap.read()
         ↓                 menyimpan HANYA frame terbaru
    [shared _latest_frame] ← dilindungi threading.Lock
         ↓
    [Main Thread]         → ambil frame terbaru kapanpun siap

Mengapa threaded?
    Tanpa threading, saat YOLO inference memakan 200-500ms per frame,
    buffer internal OpenCV menumpuk frame lama. Akibatnya:
    - Video terlihat "lag" / menampilkan frame yang sudah lewat
    - Semakin lama dijalankan, delay semakin besar (buffer terus tumbuh)

    Dengan threading, background thread terus membaca dan MEMBUANG
    frame lama — main thread selalu mendapat frame TERBARU.

Fitur production-ready:
    - Auto-reconnect RTSP dengan exponential backoff
    - Loop detection untuk mode file (video habis → mulai ulang)
    - FPS tracking di sisi capture
    - Graceful shutdown via threading.Event
    - Thread-safe frame access
"""

import time
import threading
from typing import Optional, Tuple

import cv2

from src.logger import get_logger

logger = get_logger(__name__)

# Batas maksimum percobaan reconnect sebelum backoff mencapai plateu
_MAX_BACKOFF_DETIK = 30.0


class SumberVideo:
    """
    Threaded video source — decouples frame capture dari processing loop.

    Usage:
        sumber = SumberVideo(config, kamera_config)
        # ... di main loop:
        frame = sumber.baca_frame()  # non-blocking, return latest frame
        # ... saat selesai:
        sumber.lepas()
    """

    def __init__(self, config, kamera_config):
        # Tentukan mode dan source
        mode = (
            kamera_config.get("source_type")
            or config.get("video_source.mode", "file")
        )

        if mode in ("rtsp", "stream"):
            source = (
                kamera_config.get("rtsp_url")
                or config.get("video_source.rtsp_url")
            )
        else:
            source = (
                kamera_config.get("source")
                or kamera_config.get("file_path")
                or config.get("video_source.file_path")
            )

        self.source = source
        self.mode = mode
        self.width = config.get("video_source.process_width", 960)
        self.height = config.get("video_source.process_height", 540)

        # State untuk threaded reader
        self._latest_frame: Optional[cv2.typing.MatLike] = None
        self._frame_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._baru_saja_di_loop = False
        self._loop_lock = threading.Lock()

        # FPS tracking sisi capture
        self._capture_fps: float = 0.0
        self._frame_count: int = 0
        self._fps_waktu_mulai: float = time.time()

        # Reconnect state
        self._reconnect_attempt: int = 0

        # Log info
        if mode in ("rtsp", "stream"):
            logger.info(
                f"[VIDEO] Mode RTSP — menghubungkan ke: "
                f"{self._sensor_url(self.source)}"
            )
        else:
            logger.info(f"[VIDEO] Mode File — membuka: {self.source}")

        # Buka koneksi awal dan mulai thread
        self._cap: Optional[cv2.VideoCapture] = None
        self._buka_koneksi()
        self._thread = threading.Thread(
            target=self._loop_baca, daemon=True, name="video_reader"
        )
        self._thread.start()
        logger.info("[VIDEO] Background reader thread dimulai.")

    # ------------------------------------------------------------------
    # Properties publik
    # ------------------------------------------------------------------

    @property
    def baru_saja_di_loop(self) -> bool:
        """Cek apakah video baru saja di-loop (mode file)."""
        with self._loop_lock:
            return self._baru_saja_di_loop

    @baru_saja_di_loop.setter
    def baru_saja_di_loop(self, value: bool):
        with self._loop_lock:
            self._baru_saja_di_loop = value

    @property
    def capture_fps(self) -> float:
        """FPS aktual sisi capture (bukan processing)."""
        return self._capture_fps

    # ------------------------------------------------------------------
    # Internal: koneksi
    # ------------------------------------------------------------------

    def _sensor_url(self, url: str) -> str:
        """Sembunyikan password saat mencetak URL RTSP ke log."""
        if not url or "@" not in url or "://" not in url:
            return str(url)
        skema, sisa = url.split("://", 1)
        if "@" in sisa:
            _, host = sisa.split("@", 1)
            return f"{skema}://***:***@{host}"
        return url

    def _buka_koneksi(self):
        """Buka atau reconnect koneksi video."""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass

        self._cap = cv2.VideoCapture(self.source)

        if not self._cap.isOpened():
            logger.warning("[VIDEO] Gagal membuka sumber video.")
            if self.mode in ("rtsp", "stream"):
                logger.warning(
                    "Kemungkinan: (1) URL RTSP salah, "
                    "(2) kamera tidak dalam jaringan sama, "
                    "(3) username/password salah, "
                    "(4) firewall memblokir port 554."
                )
            else:
                logger.warning(
                    "Pastikan path file video benar dan file ada."
                )
        else:
            self._reconnect_attempt = 0
            logger.info("[VIDEO] Koneksi video berhasil dibuka.")

    def _reconnect_dengan_backoff(self):
        """Reconnect RTSP dengan exponential backoff."""
        self._reconnect_attempt += 1
        delay = min(
            2.0 ** self._reconnect_attempt, _MAX_BACKOFF_DETIK
        )
        logger.warning(
            f"[VIDEO] Reconnect attempt #{self._reconnect_attempt}, "
            f"menunggu {delay:.1f}s..."
        )
        # Tunggu dengan cek stop event (agar bisa dihentikan saat menunggu)
        self._stop_event.wait(timeout=delay)
        if not self._stop_event.is_set():
            self._buka_koneksi()

    # ------------------------------------------------------------------
    # Background thread: loop baca frame
    # ------------------------------------------------------------------

    def _loop_baca(self):
        """
        Loop utama background thread.
        Terus membaca frame dari VideoCapture dan menyimpan yang terbaru.
        Frame lama OTOMATIS dibuang (tidak di-buffer).
        """
        while not self._stop_event.is_set():
            # Cek koneksi
            if self._cap is None or not self._cap.isOpened():
                if self.mode in ("rtsp", "stream"):
                    self._reconnect_dengan_backoff()
                else:
                    self._buka_koneksi()
                    if not self._cap or not self._cap.isOpened():
                        self._stop_event.wait(timeout=1.0)
                continue

            ret, frame = self._cap.read()

            if not ret:
                if self.mode in ("rtsp", "stream"):
                    logger.warning(
                        "[VIDEO] Frame gagal dibaca, reconnecting..."
                    )
                    self._reconnect_dengan_backoff()
                else:
                    # Mode file: loop ulang dari awal
                    logger.info(
                        "[VIDEO] Video selesai, memutar ulang..."
                    )
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    with self._loop_lock:
                        self._baru_saja_di_loop = True
                continue

            # Resize ke resolusi target
            frame = cv2.resize(frame, (self.width, self.height))

            # Simpan frame terbaru (thread-safe)
            with self._frame_lock:
                self._latest_frame = frame

            # Update FPS counter
            self._frame_count += 1
            elapsed = time.time() - self._fps_waktu_mulai
            if elapsed >= 2.0:  # Update FPS setiap 2 detik
                self._capture_fps = self._frame_count / elapsed
                self._frame_count = 0
                self._fps_waktu_mulai = time.time()

            # Kecilkan CPU usage — sleep singkat agar thread lain dapat jatah
            # 1ms cukup untuk yield tanpa menambah latency signifikan
            time.sleep(0.001)

        logger.info("[VIDEO] Background reader thread berhenti.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def baca_frame(self) -> Optional[cv2.typing.MatLike]:
        """
        Ambil frame TERBARU yang tersedia (non-blocking).

        Return None jika belum ada frame (mis. koneksi belum siap).
        Frame yang dikembalikan adalah COPY — aman untuk dimodifikasi
        tanpa mempengaruhi frame di thread reader.
        """
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def lepas(self):
        """Hentikan thread dan lepas resource."""
        logger.info("[VIDEO] Menghentikan video reader...")
        self._stop_event.set()

        # Tunggu thread selesai (max 3 detik)
        if self._thread.is_alive():
            self._thread.join(timeout=3.0)

        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

        logger.info("[VIDEO] Video reader dihentikan dan resource dilepas.")
