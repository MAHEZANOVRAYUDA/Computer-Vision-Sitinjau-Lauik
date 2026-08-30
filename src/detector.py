"""
detector.py
===========
Modul inti yang menggabungkan:
1. YOLOv8 - deteksi objek (jenis kendaraan) per frame
2. ByteTrack - pelacakan objek antar frame (built-in di Ultralytics)
3. PelacakLintasGaris - penghitungan kendaraan yang melewati garis virtual

Ini adalah "otak" dari sistem edge yang akan berjalan di setiap gerbang
(saat prototipe: laptop Anda, saat produksi: Raspberry Pi + Coral).
"""

import time
from collections import defaultdict
from typing import Dict, List, Optional

import cv2
from ultralytics import YOLO

from src.config_loader import Config
from src.counting_line import GarisVirtual, PelacakLintasGaris
from src.event_publisher import EventPublisher
from src.logger import get_logger
from src.visualizer import Visualizer

logger = get_logger(__name__)


class DetektorKendaraan:
    def __init__(self, config: Config, kamera_config: dict, publisher: Optional[EventPublisher] = None):
        self.config = config
        self.kamera_config = kamera_config
        self.publisher = publisher

        # Model loading
        weights_path = config.get("model.weights_path")
        logger.info(f"Memuat model YOLO dari: {weights_path}")
        self.model = YOLO(weights_path)

        self.device = config.get("model.device", "cpu")
        self.confidence = config.get("model.confidence_threshold", 0.30)
        self.confidence_motor = float(
            config.get("model.confidence_threshold_motor", self.confidence)
        )
        self.iou = config.get("model.iou_threshold", 0.45)
        self.tracker_cfg = config.get("tracker.type", "bytetrack.yaml")
        self.inference_size = config.get("model.inference_size", 416)
        self.use_half = config.get("model.half_precision", self.device == "cuda")

        self.coco_mapping = {
            int(k): v for k, v in config.get("model.coco_class_mapping", {}).items()
        }
        # Kelas COCO yang relevan untuk kita filter (buang objek non-kendaraan)
        self.kelas_relevan = set(self.coco_mapping.keys())

        # Siapkan garis virtual dari konfigurasi
        self.daftar_garis = self._buat_garis_dari_config()
        self.pelacak_garis = PelacakLintasGaris(self.daftar_garis)

        # Counter kumulatif sejak sistem mulai berjalan (untuk ditampilkan di layar/log)
        self.counter_kumulatif: Dict[str, int] = defaultdict(int)
        # Counter per interval agregasi (direset tiap interval, dikirim ke server)
        self.counter_interval: Dict[str, int] = defaultdict(int)
        
        # Penampung kecepatan untuk dirata-rata per interval agregasi
        self.kecepatan_interval: List[float] = []
        self.kecepatan_per_topografi: Dict[str, List[float]] = defaultdict(list)

        self.gerbang_id = self.kamera_config.get("id", "gerbang_a")

        logger.info(
            f"Detektor siap: device={self.device} | conf={self.confidence} | "
            f"iou={self.iou} | imgsz={self.inference_size} | "
            f"half={self.use_half} | kelas={list(self.coco_mapping.values())}"
        )

    def _buat_garis_dari_config(self) -> List[GarisVirtual]:
        garis_list = []
        counting_lines = self.kamera_config.get("counting_lines", [])
        for line in counting_lines:
            titik_1 = line.get("garis", {}).get("titik_1", [100, 400])
            titik_2 = line.get("garis", {}).get("titik_2", [450, 400])
            if line.get("arah") == "keluar" and not line.get("garis"):
                titik_1, titik_2 = [510, 400], [860, 400]
                
            garis_list.append(
                GarisVirtual(
                    lajur_id=line["id"],
                    arah=line["arah"],
                    titik_1=tuple(titik_1),
                    titik_2=tuple(titik_2),
                    toleransi_piksel=line.get("toleransi_piksel", 8),
                    pixel_per_meter=line.get("pixel_per_meter", 25.0),
                    arah_topografi=line.get("arah_topografi"),
                )
            )
        return garis_list

    def _kunci_counter(self, arah: str, kelas: str) -> str:
        """Membuat key konsisten untuk dictionary counter, mis. 'masuk_motor'."""
        return f"{arah}_{kelas}"

    def _catat_event(self, line_id: str, arah: str, kelas: str, track_id: int):
        key = self._kunci_counter(arah, kelas)
        self.counter_kumulatif[key] += 1
        self.counter_interval[key] += 1

        logger.info(
            f"[HITUNG] Gerbang={self.gerbang_id} | Line={line_id} | "
            f"Arah={arah} | Kelas={kelas.capitalize()} | TrackID={track_id} | "
            f"Total kumulatif {kelas.capitalize()}={self.counter_kumulatif[key]}"
        )

        if self.publisher:
            self.publisher.kirim_event_hitungan(
                gerbang_id=self.gerbang_id,
                line_id=line_id,
                arah=arah,
                kelas=kelas,
                track_id=track_id,
            )



    def proses_frame(self, frame):
        """
        Memproses satu frame: deteksi + tracking + cek lintas garis.
        Mengembalikan frame yang sudah digambari overlay (untuk ditampilkan).
        """
        hasil = self.model.track(
            frame,
            persist=True,
            conf=self.confidence,
            iou=self.iou,
            tracker=self.tracker_cfg,
            device=self.device,
            classes=list(self.kelas_relevan),
            verbose=False,
            imgsz=self.inference_size,
            half=self.use_half,
        )[0]

        track_id_aktif = []

        if hasil.boxes is not None and hasil.boxes.id is not None:
            boxes = hasil.boxes.xyxy.cpu().numpy()
            track_ids = hasil.boxes.id.cpu().numpy().astype(int)
            class_ids = hasil.boxes.cls.cpu().numpy().astype(int)
            confs = (
                hasil.boxes.conf.cpu().numpy()
                if hasil.boxes.conf is not None
                else [1.0] * len(boxes)
            )

            for box, tid, cid, conf in zip(boxes, track_ids, class_ids, confs):
                if cid not in self.coco_mapping:
                    continue

                kelas = self.coco_mapping[cid]
                if kelas == "motor" and float(conf) < self.confidence_motor:
                    continue

                track_id_aktif.append(tid)

                x1, y1, x2, y2 = box
                x_center = (x1 + x2) / 2
                y_center = (y1 + y2) / 2

                events = self.pelacak_garis.proses_deteksi(tid, x_center, y_center)
                for event in events:
                    self._catat_event(
                        line_id=event["lajur_id"],
                        arah=event["arah"],
                        kelas=kelas,
                        track_id=tid,
                    )
                    
                    if event.get("kecepatan_kmh") is not None:
                        self.kecepatan_interval.append(event["kecepatan_kmh"])
                        topo = event.get("arah_topografi")
                        if topo in ("naik", "turun"):
                            self.kecepatan_per_topografi[topo].append(event["kecepatan_kmh"])

        self.pelacak_garis.bersihkan_track_hilang(track_id_aktif)

        tampilkan_garis = self.config.get("tampilan.tampilkan_garis_virtual", True)
        nama_gerbang = self.kamera_config.get("nama", "Kamera")
        frame_overlay = Visualizer.gambar_overlay(
            frame, hasil, self.daftar_garis, self.coco_mapping, self.counter_kumulatif, nama_gerbang, tampilkan_garis
        )
        return frame_overlay

    def peta_arah_topografi(self) -> Dict[str, str]:
        """Mapping arah masuk/keluar → naik/turun dari counting lines."""
        hasil: Dict[str, str] = {}
        for garis in self.daftar_garis:
            if garis.arah_topografi:
                hasil[garis.arah] = garis.arah_topografi
        return hasil

    def reset_counter_interval(self) -> tuple:
        """
        Dipanggil oleh scheduler agregasi setiap N detik (lihat main.py).
        Return: (snapshot, avg_speed, kecepatan_per_topografi, arah_topografi_map)
        """
        snapshot = dict(self.counter_interval)
        self.counter_interval = defaultdict(int)
        
        avg_speed = None
        if self.kecepatan_interval:
            avg_speed = sum(self.kecepatan_interval) / len(self.kecepatan_interval)
            self.kecepatan_interval.clear()

        speed_topo: Dict[str, float] = {}
        for topo, vals in self.kecepatan_per_topografi.items():
            if vals:
                speed_topo[topo] = sum(vals) / len(vals)
        self.kecepatan_per_topografi.clear()
            
        return snapshot, avg_speed, speed_topo, self.peta_arah_topografi()

    def reset_tracker(self):
        """
        Mereset state internal tracker ByteTrack dan pelacak garis.

        WAJIB dipanggil setiap kali video di-loop ulang dari awal (mode file).
        Alasannya: model.track(persist=True) menyimpan state tracker antar
        pemanggilan supaya track_id konsisten. Saat video di-set balik ke
        frame 0, track_id lama bisa bertabrakan dengan objek baru, membuat
        kendaraan yang sebenarnya baru tidak terhitung (dikira duplikat).
        Mereset state internal tracker tanpa perlu memuat ulang model YOLO (yang memakan waktu).
        """
        logger.info("[detector] Mereset tracker & state...")
        
        # Hapus instance predictor agar ultralytics membuat yang baru
        # Ini akan mereset tracker state (ByteTrack/BoT-SORT) dengan aman.
        if hasattr(self.model, "predictor") and self.model.predictor is not None:
            self.model.predictor = None
            logger.debug("[detector] State predictor Ultralytics direset.")
            
        self.pelacak_garis = PelacakLintasGaris(self.daftar_garis)

        logger.info("Tracker & pelacak garis direset (video di-loop ulang).")
