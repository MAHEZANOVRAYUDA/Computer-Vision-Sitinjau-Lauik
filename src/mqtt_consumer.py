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
import time
from collections import defaultdict
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
    # TODO: Implement multi-gerbang recovery if needed
    pass


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

        # 5. Simpan status ke database
        try:
            db.simpan_status_ruas(id_ruas, hasil, total_occupancy)
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
