"""
mqtt_consumer.py
=================
Proses SERVER yang berjalan terpisah dari edge (src/main.py).
Tugasnya:
1. Berlangganan (subscribe) topik MQTT dari semua gerbang
2. Ketika terima snapshot agregasi interval dari suatu gerbang,
   simpan ke database
3. Jalankan sistem pakar untuk update status ruas (lancar/padat/macet)
4. Simpan status baru ke database (untuk dibaca dashboard)

Cara menjalankan (proses terpisah, di terminal lain, SETELAH src/main.py jalan):
    python src/mqtt_consumer.py config/config_gerbang_a.yaml

PENTING: modul ini mengasumsikan HANYA ADA 1 gerbang aktif untuk prototipe ini.
Rumus occupancy (masuk - keluar) di sini disederhanakan: karena baru gerbang A
yang ada, "occupancy" dihitung sebagai estimasi kendaraan yang sedang berada di
ruas menggunakan flow × waktu tempuh (bukan akumulasi mentah yang terus naik).
Ini disebut eksplisit di dashboard sebagai "Mode Prototipe 1 Gerbang" agar
tidak menyesatkan saat demo.

Perbaikan v2:
- Startup recovery: occupancy dipulihkan dari DB saat proses restart
  (mencegah occupancy mulai dari 0 padahal kendaraan sudah ada di ruas)
- Logging terpusat menggantikan print()

Perbaikan v3 (Blueprint Perbaikan):
- Fix BUG: tambah import sys yang hilang (menyebabkan NameError crash)
- Fix pembacaan ambang_lancar / ambang_padat menggunakan flat key langsung
  di sistem_pakar (sesuai config.yaml v2 — key nested ambang_batas dihapus)
- Integrasikan occupancy_estimator: gunakan flow × waktu tempuh sebagai
  estimasi occupancy (bukan akumulasi kumulatif yang terus naik sepanjang hari)
- Kapasitas dibaca dari kapasitas_meter_lajur_computed (dihitung dari ruas_jalan)
  bukan nilai mentah dari config — konsisten dengan config_loader v2
"""

import json
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Tambah root proyek ke sys.path agar import 'src.*' bekerja
# baik dengan 'python src/mqtt_consumer.py' maupun 'python -m src.mqtt_consumer'
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import paho.mqtt.client as mqtt

from src.config_loader import load_config
from src.database import Database
from src.logger import setup_logging, get_logger
from src.mkji import evaluasi_mkji
from src.sistem_pakar import evaluasi
from src.occupancy_estimator import (
    hitung_occupancy_ruas,
    OccupancyRuas,
)

logger = get_logger(__name__)

# State occupancy kumulatif per arah per gerbang
kumulatif_gerbang_a_masuk = defaultdict(int)
kumulatif_gerbang_a_keluar = defaultdict(int)
kumulatif_gerbang_b_masuk = defaultdict(int)
kumulatif_gerbang_b_keluar = defaultdict(int)


def recover_occupancy_dari_db(db: Database) -> None:
    """
    Memulihkan state kumulatif in-memory dari database saat proses
    consumer baru start/restart, supaya occupancy tidak mulai dari
    0 secara keliru.
    """
    global kumulatif_gerbang_a_masuk, kumulatif_gerbang_a_keluar
    global kumulatif_gerbang_b_masuk, kumulatif_gerbang_b_keluar

    try:
        data = db.ambil_kumulatif_masuk_keluar_per_gerbang(sejak_jam=24)
    except Exception as e:
        logger.error(f"[Recovery] Gagal memulihkan occupancy dari DB: {e}. Mulai dari 0.")
        return

    for kelas, jumlah in data.get("gerbang_a_masuk", {}).items():
        kumulatif_gerbang_a_masuk[kelas] = jumlah
    for kelas, jumlah in data.get("gerbang_a_keluar", {}).items():
        kumulatif_gerbang_a_keluar[kelas] = jumlah
    for kelas, jumlah in data.get("gerbang_b_masuk", {}).items():
        kumulatif_gerbang_b_masuk[kelas] = jumlah
    for kelas, jumlah in data.get("gerbang_b_keluar", {}).items():
        kumulatif_gerbang_b_keluar[kelas] = jumlah

    total_recovered = sum(kumulatif_gerbang_a_masuk.values()) + sum(kumulatif_gerbang_b_masuk.values())
    logger.info(
        f"[Recovery] State occupancy dipulihkan dari DB: "
        f"A_masuk={dict(kumulatif_gerbang_a_masuk)} | A_keluar={dict(kumulatif_gerbang_a_keluar)} | "
        f"B_masuk={dict(kumulatif_gerbang_b_masuk)} | B_keluar={dict(kumulatif_gerbang_b_keluar)} | "
        f"Total unit dipulihkan: {total_recovered}"
    )


def _hitung_detik_ke_tengah_malam() -> float:
    """Hitung detik hingga tengah malam hari ini."""
    sekarang = datetime.now()
    tengah_malam = sekarang.replace(hour=0, minute=0, second=0, microsecond=0)
    # Jika sudah lewat tengah malam hari ini, hitung ke tengah malam besok
    delta = (tengah_malam - sekarang).total_seconds()
    if delta <= 0:
        delta += 86400  # tambah 1 hari (86400 detik)
    return delta


def _jadwalkan_reset_harian():
    """
    Scheduler ringan dengan threading.Timer yang me-reset ke-4 dictionary
    kumulatif ke 0 setiap pukul 00:00 waktu lokal.
    Menjadwalkan ulang dirinya sendiri setiap kali dipanggil.
    """
    global kumulatif_gerbang_a_masuk, kumulatif_gerbang_a_keluar
    global kumulatif_gerbang_b_masuk, kumulatif_gerbang_b_keluar

    kumulatif_gerbang_a_masuk.clear()
    kumulatif_gerbang_a_keluar.clear()
    kumulatif_gerbang_b_masuk.clear()
    kumulatif_gerbang_b_keluar.clear()
    logger.info("[Reset Harian] Kumulatif occupancy di-reset ke 0 (pukul 00:00).")

    # Jadwalkan lagi untuk hari berikutnya
    threading.Timer(_hitung_detik_ke_tengah_malam(), _jadwalkan_reset_harian).start()


def buat_handler_pesan(config, db):
    topic_prefix = config.get("mqtt.topic_prefix", "sitinjau_lauik")
    id_ruas = 1  # sesuai seed di setup_database.sql untuk prototipe 1 ruas

    # Baca kapasitas yang sudah dihitung (bukan nilai config mentah)
    # Fallback ke nilai config lama jika computed tidak tersedia
    kapasitas = (
        config.get("kapasitas_meter_lajur_computed")
        or config.get("sistem_pakar.kapasitas_meter_lajur", 56100)
    )
    kapasitas = float(kapasitas)

    panjang_kendaraan = config.get("panjang_kendaraan", {})

    # PERBAIKAN: gunakan flat key langsung di sistem_pakar (bukan nested ambang_batas)
    # Config v1 punya: sistem_pakar.ambang_batas.lancar_maks_persen (TIDAK bisa dibaca
    # dengan dot notation karena ada 3 level). Config v2 punya flat key:
    # sistem_pakar.ambang_lancar dan sistem_pakar.ambang_padat — ini yang benar.
    ambang_lancar = float(config.get("sistem_pakar.ambang_lancar", 50.0))
    ambang_padat = float(config.get("sistem_pakar.ambang_padat", 75.0))
    ambang_kecepatan = float(config.get("sistem_pakar.ambang_kecepatan_lambat_kmh", 15.0))

    # Parameter untuk occupancy estimator
    panjang_ruas_km = float(config.get("ruas_jalan.panjang_meter", 16500)) / 1000.0
    kecepatan_referensi = float(config.get("ruas_jalan.kecepatan_referensi_kmh", 42.0))
    interval_detik = float(config.get("agregasi.interval_detik", 20))

    logger.info(
        f"[Consumer] Kapasitas volumetrik ruas: {kapasitas:.0f} meter-lajur | "
        f"Ambang lancar: {ambang_lancar}% | Ambang padat: {ambang_padat}%"
    )

    def on_connect(client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info("[MQTT-Consumer] Terhubung ke broker.")
            topik_agregasi = f"{topic_prefix}/+/agregasi"
            client.subscribe(topik_agregasi, qos=1)
            logger.info(f"[MQTT-Consumer] Berlangganan topik: {topik_agregasi}")
        else:
            logger.error(f"[MQTT-Consumer] Gagal terhubung, kode: {reason_code}")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            logger.warning(
                f"[MQTT-Consumer] Payload tidak valid JSON, diabaikan: {msg.payload[:100]}"
            )
            return

        gerbang_id = payload.get("gerbang_id")
        counter = payload.get("counter", {})
        timestamp = payload.get("timestamp", time.time())

        logger.info(f"[MQTT-Consumer] Menerima agregasi dari {gerbang_id}: {counter}")

        # Deteksi clock drift — Tahap 5: validasi sinkronisasi waktu node edge
        drift_detik = abs(time.time() - timestamp)
        if drift_detik > 5.0:
            logger.warning(
                f"[MQTT-Consumer] Drift waktu terdeteksi dari {gerbang_id}: "
                f"{drift_detik:.1f} detik. Cek sinkronisasi NTP node edge ini."
            )

        # 1. Simpan rincian hitungan mentah ke database
        try:
            db.simpan_hitungan_interval(
                gerbang_id=gerbang_id,
                timestamp_interval=time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(timestamp)
                ),
                rincian_per_lajur_arah_kelas=counter,
            )
        except Exception as e:
            logger.error(f"[MQTT-Consumer] ERROR menyimpan hitungan ke database: {e}")
            return

        # 2. Update occupancy kumulatif per kelas per gerbang
        for key, jumlah in counter.items():
            parts = key.split("_", 1)
            if len(parts) != 2:
                logger.warning(f"[MQTT-Consumer] Format key tidak valid, dilewati: '{key}'")
                continue
            arah, kelas = parts
            
            gerbang_lower = gerbang_id.lower()
            if "a" in gerbang_lower:
                if arah == "masuk":
                    kumulatif_gerbang_a_masuk[kelas] += jumlah
                elif arah == "keluar":
                    kumulatif_gerbang_a_keluar[kelas] += jumlah
            elif "b" in gerbang_lower:
                if arah == "masuk":
                    kumulatif_gerbang_b_masuk[kelas] += jumlah
                elif arah == "keluar":
                    kumulatif_gerbang_b_keluar[kelas] += jumlah

        # 3. Hitung estimasi occupancy menggunakan dual-gerbang
        try:
            occupancy_ruas = hitung_occupancy_ruas(
                kumulatif_gerbang_a_masuk,
                kumulatif_gerbang_b_keluar,
                kumulatif_gerbang_b_masuk,
                kumulatif_gerbang_a_keluar
            )
            jumlah_untuk_evaluasi = occupancy_ruas.total_per_kelas
            total_occupancy = sum(jumlah_untuk_evaluasi.values())
            metode_occupancy = occupancy_ruas.metode
            confidence_note = "Occupancy dihitung dari selisih kumulatif dual-gerbang."

            logger.info(
                f"[Occupancy] Estimasi ({metode_occupancy}): "
                f"{jumlah_untuk_evaluasi} | Total: {total_occupancy}"
            )
        except Exception as e:
            logger.error(f"[Occupancy] Error hitung occupancy: {e}")
            return

        kecepatan_rata2_kmh = payload.get("kecepatan_rata2_kmh")
        
        # 4. Jalankan sistem pakar berdasarkan occupancy estimasi
        try:
            hasil = evaluasi(
                jumlah_per_kelas=jumlah_untuk_evaluasi,
                kapasitas_meter_lajur=kapasitas,
                panjang_kendaraan=panjang_kendaraan,
                ambang_lancar=ambang_lancar,
                ambang_padat=ambang_padat,
                kecepatan_rata2_kmh=kecepatan_rata2_kmh,
                ambang_kecepatan_lambat_kmh=ambang_kecepatan
            )
        except ValueError as e:
            logger.error(f"[Sistem Pakar] ERROR: {e}")
            return

        logger.info(
            f"[Sistem Pakar] Occupancy estimasi: {total_occupancy} kendaraan | "
            f"Volume (Meter-Lajur): {hasil.volume_smp} | Kepadatan: {hasil.rasio_vc * 100:.2f}% | "
            f"LOS: {hasil.level_of_service} | Status: {hasil.status_label.upper()}"
        )
        logger.info(f"[Sistem Pakar] Rekomendasi: {hasil.teks_rekomendasi}")
        logger.info(f"[Sistem Pakar] Metode: {metode_occupancy} | {confidence_note}")

        # 4b. Evaluasi MKJI 1997 (paralel, tidak menggantikan sistem pakar lama)
        hasil_mkji = None
        try:
            interval_jam = interval_detik / 3600.0
            if interval_jam > 0:
                # Flow pada interval ini (dari gerbang yang melaporkan)
                flow_per_kelas = defaultdict(int)
                for key, jumlah in counter.items():
                    parts = key.split("_", 1)
                    if len(parts) == 2:
                        kelas = parts[1]
                        flow_per_kelas[kelas] += jumlah
                        
                jumlah_per_jam = {
                    kelas: jumlah / interval_jam
                    for kelas, jumlah in flow_per_kelas.items()
                }
                hasil_mkji = evaluasi_mkji(
                    jumlah_per_kelas_per_jam=jumlah_per_jam,
                    medan=config.get("mkji.medan", "gunung"),
                    fc_w=float(config.get("mkji.fc_w", 0.90)),
                    fc_sp=float(config.get("mkji.fc_sp", 1.00)),
                    fc_sf=float(config.get("mkji.fc_sf", 1.00)),
                    fc_cs=float(config.get("mkji.fc_cs", 1.00)),
                    emp=config.get("mkji.emp"),
                    ambang_lancar=float(config.get("mkji.ambang_lancar_vc", 0.54)),
                    ambang_padat=float(config.get("mkji.ambang_padat_vc", 0.90)),
                )
                logger.info(
                    f"[MKJI] Volume: {hasil_mkji.volume_smp_per_jam:.1f} smp/jam | "
                    f"Kapasitas: {hasil_mkji.kapasitas_smp_per_jam:.1f} smp/jam | "
                    f"V/C: {hasil_mkji.rasio_vc:.3f} | LOS: {hasil_mkji.level_of_service} | "
                    f"Status: {hasil_mkji.status_label.upper()}"
                )
        except ValueError as e:
            logger.error(f"[MKJI] ERROR: {e}")

        # 5. Simpan status ke database
        try:
            db.simpan_status_ruas(id_ruas, hasil, total_occupancy, hasil_mkji=hasil_mkji)
        except Exception as e:
            logger.error(f"[MQTT-Consumer] ERROR menyimpan status ke database: {e}")

    return on_connect, on_message


def jalankan():
    # Muat config dan setup logging sebelum apapun
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/config.yaml"
    config = load_config(config_path)
    setup_logging(
        level_str=config.get("logging.level", "INFO"),
        log_file_path=config.get("logging.file_path", "data/logs/sistem.log"),
    )

    logger.info("=" * 70)
    logger.info("SERVER CONSUMER - Sitinjau Lauik Traffic System")
    logger.info("=" * 70)

    db = Database(config)
    db.hubungkan()

    # Pulihkan state occupancy dari DB sebelum mulai terima pesan baru
    recover_occupancy_dari_db(db)

    # Jadwalkan reset harian kumulatif occupancy setiap pukul 00:00 (Tahap 1)
    t_reset = threading.Timer(_hitung_detik_ke_tengah_malam(), _jadwalkan_reset_harian)
    t_reset.daemon = True  # daemon thread — otomatis berhenti saat proses utama berhenti
    t_reset.start()
    logger.info("[Reset Harian] Scheduler reset occupancy aktif.")

    on_connect, on_message = buat_handler_pesan(config, db)

    client = mqtt.Client(
        client_id="server_consumer",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.on_connect = on_connect
    client.on_message = on_message

    host = config.get("mqtt.broker_host", "localhost")
    port = config.get("mqtt.broker_port", 1883)

    logger.info(f"Menghubungkan ke broker MQTT {host}:{port}...")
    client.connect(host, port, keepalive=60)

    logger.info("Server berjalan. Menunggu data dari edge... (Ctrl+C untuk berhenti)")

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Server dihentikan.")
    finally:
        db.tutup()


if __name__ == "__main__":
    jalankan()

# =====================================================================
# CATATAN PENGEMBANGAN LANJUTAN (di luar skop prototipe 1 kamera ini):
# - Saat Gerbang B sudah aktif, logika occupancy HARUS diubah: bukan lagi
#   flow_x_traveltime, tapi estimasi_occupancy_flow_in_minus_out() dari
#   occupancy_estimator.py — perubahan ini TANPA mengubah logika evaluasi()
#   karena interface EstimasiOccupancy.jumlah_per_kelas tidak berubah.
# - Untuk skala banyak gerbang: pertimbangkan Kafka/RabbitMQ sebagai
#   pengganti MQTT agar ada message ordering dan replay capability.
# =====================================================================
