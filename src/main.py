"""
main.py
=======
Entry point utama untuk menjalankan sistem deteksi kendaraan di satu gerbang.

Cara menjalankan (dari root folder proyek, dengan virtual environment aktif):
    python src/main.py
    python src/main.py --config config/config_gerbang_b.yaml

Tekan 'q' pada jendela video untuk menghentikan program dengan aman.

Alur program:
1. Muat konfigurasi dari config.yaml (atau file yang ditentukan via --config)
2. Setup logging terpusat
3. Buka koneksi video via threaded reader (RTSP atau file lokal)
4. Siapkan detektor (YOLO + ByteTrack + counting line)
5. Siapkan publisher MQTT (opsional, jika broker tidak ada tetap jalan)
6. Loop: ambil frame terbaru → proses → tampilkan → tiap N detik kirim agregasi
"""

import sys
import time
import argparse
from pathlib import Path

import cv2

# Pastikan root proyek ada di sys.path agar import 'src.*' berfungsi
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config_loader import load_config
from src.detector import DetektorKendaraan
from src.event_publisher import EventPublisher
from src.logger import setup_logging, get_logger
from src.mjpeg_streamer import start_stream_server, update_frame
from src.video_source import SumberVideo

# Logger diinisialisasi SETELAH setup_logging() dipanggil di jalankan()
logger = get_logger(__name__)


def jalankan():
    parser = argparse.ArgumentParser(
        description="Jalankan edge detector untuk kamera tertentu."
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path ke file konfigurasi",
    )
    parser.add_argument(
        "--kamera",
        default=None,
        help="ID Kamera yang akan dijalankan (mis: gerbang_a, gerbang_b)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    # --- Setup Logging Terpusat ---
    setup_logging(
        level_str=config.get("logging.level", "INFO"),
        log_file_path=config.get("logging.file_path", "data/logs/sistem.log"),
    )

    # --- Pilih kamera yang akan dijalankan ---
    daftar_kamera = config.get("kamera", [])
    kamera_config = None
    if args.kamera:
        for k in daftar_kamera:
            if k.get("id") == args.kamera:
                kamera_config = k
                break
    else:
        for k in daftar_kamera:
            if k.get("aktif"):
                kamera_config = k
                break

    if not kamera_config:
        logger.error(
            "Kamera tidak ditemukan atau tidak ada kamera yang aktif."
        )
        return

    gerbang_id_tampil = kamera_config.get("nama", "Kamera").upper()
    gerbang_id = kamera_config.get("id", "gerbang_a")

    logger.info("=" * 70)
    logger.info(
        f"SISTEM DETEKSI KEMACETAN SITINJAU LAUIK — Edge ({gerbang_id_tampil})"
    )
    logger.info("=" * 70)

    # --- Inisialisasi komponen ---
    publisher = EventPublisher(config, kamera_config)
    publisher.hubungkan(timeout_detik=5)

    detektor = DetektorKendaraan(config, kamera_config, publisher=publisher)
    sumber_video = SumberVideo(config, kamera_config)

    tampilkan_window = config.get("tampilan.tampilkan_window", False)
    simpan_output = config.get("tampilan.simpan_video_output", False)
    interval_agregasi = config.get("agregasi.interval_detik", 30)
    stream_port = kamera_config.get("stream_port")
    # Frame skip: proses YOLO hanya setiap N frame (hemat CPU)
    # Capture FPS biasanya 24-30, dengan skip=4 efektif 6-8 FPS inference
    frame_skip = config.get("tampilan.frame_skip", 4)

    if stream_port:
        start_stream_server(stream_port)
        logger.info(
            f"Video streaming aktif di http://localhost:{stream_port}/video_feed"
        )

    # --- Video writer (opsional) ---
    video_writer = None
    if simpan_output:
        path_output = config.get("tampilan.path_video_output")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        video_writer = cv2.VideoWriter(
            path_output,
            fourcc,
            20.0,
            (
                config.get("video_source.process_width", 960),
                config.get("video_source.process_height", 540),
            ),
        )
        logger.info(f"Video output akan disimpan ke: {path_output}")

    # --- State tracking ---
    waktu_agregasi_terakhir = time.time()
    frame_count = 0
    waktu_mulai = time.time()

    # FPS monitoring (processing FPS, bukan capture FPS)
    fps_counter = 0
    fps_timer = time.time()
    processing_fps = 0.0

    logger.info("Sistem berjalan. Tekan 'q' pada jendela video untuk berhenti.")

    try:
        while True:
            # Ambil frame TERBARU dari threaded reader (non-blocking)
            frame = sumber_video.baca_frame()

            if frame is None:
                # Belum ada frame (koneksi belum siap) — tunggu sebentar
                time.sleep(0.01)
                continue

            # Cek apakah video baru di-loop (mode file)
            if sumber_video.baru_saja_di_loop:
                detektor.reset_tracker()
                sumber_video.baru_saja_di_loop = False

            frame_count += 1

            # --- Frame skip dinonaktifkan sementara untuk akurasi tracking dan visualisasi ---
            # if frame_count % frame_skip != 0:
            #     update_frame(frame)
            #     continue

            # --- Proses frame: deteksi + tracking + counting ---
            frame_hasil = detektor.proses_frame(frame)

            # Update MJPEG stream dengan frame yang sudah ada overlay
            update_frame(frame_hasil)

            # Tampilkan window (jika diaktifkan — nonaktif di Docker)
            if tampilkan_window:
                cv2.imshow(
                    f"Sitinjau Lauik — {gerbang_id_tampil}", frame_hasil
                )
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    logger.info("Menghentikan program atas permintaan pengguna...")
                    break

            # Simpan video output (jika diaktifkan)
            if video_writer is not None:
                video_writer.write(frame_hasil)

            # --- FPS monitoring ---
            fps_counter += 1
            fps_elapsed = time.time() - fps_timer
            if fps_elapsed >= 5.0:
                processing_fps = fps_counter / fps_elapsed
                capture_fps = sumber_video.capture_fps
                logger.info(
                    f"[FPS] Processing: {processing_fps:.1f} | "
                    f"Capture: {capture_fps:.1f} | "
                    f"Frame skip: 1/{frame_skip}"
                )
                fps_counter = 0
                fps_timer = time.time()

            # --- Cek apakah sudah waktunya kirim agregasi interval ---
            waktu_sekarang = time.time()
            if waktu_sekarang - waktu_agregasi_terakhir >= interval_agregasi:
                snapshot, avg_speed = detektor.reset_counter_interval()
                publisher.kirim_agregasi_interval(
                    gerbang_id, snapshot, avg_speed
                )
                waktu_agregasi_terakhir = waktu_sekarang

    except KeyboardInterrupt:
        logger.info("Program dihentikan (Ctrl+C).")

    finally:
        durasi = time.time() - waktu_mulai
        fps_rata = frame_count / durasi if durasi > 0 else 0
        logger.info("=" * 70)
        logger.info("RINGKASAN SESI")
        logger.info("=" * 70)
        logger.info(f"Durasi berjalan     : {durasi:.1f} detik")
        logger.info(f"Total frame diproses: {frame_count}")
        logger.info(f"FPS rata-rata       : {fps_rata:.2f}")
        logger.info("Total hitungan kumulatif:")
        for k, v in sorted(detektor.counter_kumulatif.items()):
            nama_kelas = k.split("_", 1)[-1].capitalize()
            logger.info(f"  {nama_kelas}: {v}")
        logger.info("=" * 70)

        sumber_video.lepas()
        if video_writer is not None:
            video_writer.release()
        cv2.destroyAllWindows()
        publisher.putuskan()


if __name__ == "__main__":
    jalankan()
