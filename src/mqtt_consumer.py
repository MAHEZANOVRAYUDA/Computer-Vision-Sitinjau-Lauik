"""
mqtt_consumer.py
=================
Proses SERVER yang berjalan terpisah dari edge. Berlangganan topik MQTT, 
simpan hitungan ke DB, jalankan sistem pakar & MKJI, dan simpan status ke DB.

Perbaikan v3 (Production Hardening):
- Refactored ke OOP (Class-based) untuk mempermudah testing dan maintainability.
- Thread-safe: Mutex lock (threading.Lock) ditambahkan untuk melindungi mutasi state
  occupancy dari thread utama (on_message) dan background thread (scheduler Timer).
- Integrasi Connection Pooling dari database.py.
"""

import json
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Tambah root proyek ke sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import paho.mqtt.client as mqtt

from src.config_loader import load_config
from src.database import Database
from src.logger import setup_logging, get_logger
from src.mkji import evaluasi_mkji
from src.sistem_pakar import evaluasi
from src.occupancy_estimator import hitung_occupancy_ruas

logger = get_logger(__name__)


class MqttConsumerApp:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        setup_logging(
            level_str=self.config.get("logging.level", "INFO"),
            log_file_path=self.config.get("logging.file_path", "data/logs/sistem.log"),
        )
        
        self.db = Database(self.config)
        self.topic_prefix = self.config.get("mqtt.topic_prefix", "sitinjau_lauik")
        self.id_ruas = 1
        
        # Kapasitas & Parameter
        self.kapasitas = float(self.config.get("kapasitas_meter_lajur_computed") or self.config.get("sistem_pakar.kapasitas_meter_lajur", 56100))
        self.panjang_kendaraan = self.config.get("panjang_kendaraan", {})
        self.ambang_lancar = float(self.config.get("sistem_pakar.ambang_lancar", 44.0))
        self.ambang_padat = float(self.config.get("sistem_pakar.ambang_padat", 84.0))
        self.ambang_kecepatan = float(self.config.get("sistem_pakar.ambang_kecepatan_lambat_kmh", 15.0))
        self.interval_detik = float(self.config.get("agregasi.interval_detik", 20))
        
        # State Occupancy & Thread Safety
        self.state_lock = threading.Lock()
        self.kumulatif_a_masuk = defaultdict(int)
        self.kumulatif_a_keluar = defaultdict(int)
        self.kumulatif_b_masuk = defaultdict(int)
        self.kumulatif_b_keluar = defaultdict(int)
        
        # MQTT Client
        self.client = mqtt.Client(client_id="server_consumer", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
    def start(self):
        logger.info("=" * 70)
        logger.info("SERVER CONSUMER - Sitinjau Lauik Traffic System (Production Mode)")
        logger.info("=" * 70)
        
        self.db.hubungkan()
        self.recover_state()
        self.jadwalkan_reset()
        
        host = self.config.get("mqtt.broker_host", "localhost")
        port = self.config.get("mqtt.broker_port", 1883)
        logger.info(f"Menghubungkan ke broker MQTT {host}:{port}...")
        self.client.connect(host, port, keepalive=60)
        
        logger.info("Server berjalan. Menunggu data dari edge... (Ctrl+C untuk berhenti)")
        try:
            self.client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Server dihentikan.")
        finally:
            self.db.tutup()

    def recover_state(self):
        try:
            data = self.db.ambil_kumulatif_masuk_keluar_per_gerbang(sejak_jam=24)
            with self.state_lock:
                for k, v in data.get("gerbang_a_masuk", {}).items(): self.kumulatif_a_masuk[k] = v
                for k, v in data.get("gerbang_a_keluar", {}).items(): self.kumulatif_a_keluar[k] = v
                for k, v in data.get("gerbang_b_masuk", {}).items(): self.kumulatif_b_masuk[k] = v
                for k, v in data.get("gerbang_b_keluar", {}).items(): self.kumulatif_b_keluar[k] = v
            logger.info("[Recovery] State occupancy dipulihkan dari DB.")
        except Exception as e:
            logger.error(f"[Recovery] Gagal memulihkan dari DB: {e}")

    def jadwalkan_reset(self):
        sekarang = datetime.now()
        tengah_malam = sekarang.replace(hour=0, minute=0, second=0, microsecond=0)
        delta = (tengah_malam - sekarang).total_seconds()
        if delta <= 0: delta += 86400
        
        t = threading.Timer(delta, self.lakukan_reset_harian)
        t.daemon = True
        t.start()

    def lakukan_reset_harian(self):
        with self.state_lock:
            self.kumulatif_a_masuk.clear()
            self.kumulatif_a_keluar.clear()
            self.kumulatif_b_masuk.clear()
            self.kumulatif_b_keluar.clear()
        logger.info("[Reset Harian] Kumulatif occupancy di-reset ke 0.")
        self.jadwalkan_reset()

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            topik = f"{self.topic_prefix}/+/agregasi"
            self.client.subscribe(topik, qos=1)
            logger.info(f"[MQTT] Berlangganan topik: {topik}")
        else:
            logger.error(f"[MQTT] Gagal terhubung: {reason_code}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception as e:
            logger.warning(f"[MQTT] Payload error: {e}")
            return
            
        gerbang_id = payload.get("gerbang_id")
        counter = payload.get("counter", {})
        ts = payload.get("timestamp", time.time())
        
        # Deteksi drift
        if abs(time.time() - ts) > 5.0:
            logger.warning(f"[Clock Drift] {gerbang_id} drift {abs(time.time() - ts):.1f}s.")
            
        try:
            self.db.simpan_hitungan_interval(gerbang_id, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)), counter)
        except Exception as e:
            logger.error(f"[DB] Gagal simpan hitungan: {e}")
            return
            
        with self.state_lock:
            for key, jumlah in counter.items():
                parts = key.split("_", 1)
                if len(parts) == 2:
                    arah, kelas = parts
                    gl = gerbang_id.lower()
                    if "a" in gl:
                        if arah == "masuk": self.kumulatif_a_masuk[kelas] += jumlah
                        elif arah == "keluar": self.kumulatif_a_keluar[kelas] += jumlah
                    elif "b" in gl:
                        if arah == "masuk": self.kumulatif_b_masuk[kelas] += jumlah
                        elif arah == "keluar": self.kumulatif_b_keluar[kelas] += jumlah
            
            try:
                occ = hitung_occupancy_ruas(self.kumulatif_a_masuk, self.kumulatif_b_keluar, self.kumulatif_b_masuk, self.kumulatif_a_keluar)
                jumlah_eval = occ.total_per_kelas
            except Exception as e:
                logger.error(f"[Occupancy] Error: {e}")
                return

        total_occ = sum(jumlah_eval.values())
        kecepatan = payload.get("kecepatan_rata2_kmh")
        
        try:
            hasil = evaluasi(jumlah_eval, self.kapasitas, self.panjang_kendaraan, self.ambang_lancar, self.ambang_padat, None, None, kecepatan, self.ambang_kecepatan)
        except Exception as e:
            logger.error(f"[Pakar] Error: {e}")
            return
            
        logger.info(f"[Pakar] Status: {hasil.status_label.upper()} | Kepadatan: {hasil.rasio_vc*100:.1f}%")
        
        # MKJI 1997
        hasil_mkji = None
        try:
            interval_jam = self.interval_detik / 3600.0
            if interval_jam > 0:
                flow = defaultdict(int)
                for k, v in counter.items():
                    if len(k.split("_", 1)) == 2: flow[k.split("_", 1)[1]] += v
                flow_jam = {k: v / interval_jam for k, v in flow.items()}
                
                hasil_mkji = evaluasi_mkji(
                    flow_jam, 
                    fc_w=float(self.config.get("mkji.fc_w", 0.90)),
                    fc_sp=float(self.config.get("mkji.fc_sp", 1.00)),
                    fc_sf=float(self.config.get("mkji.fc_sf", 1.00)),
                    fc_cs=float(self.config.get("mkji.fc_cs", 1.00)),
                    ambang_lancar=float(self.config.get("mkji.ambang_lancar_vc", 0.44)),
                    ambang_padat=float(self.config.get("mkji.ambang_padat_vc", 0.84)),
                )
        except Exception as e:
            logger.error(f"[MKJI] Error: {e}")
            
        try:
            self.db.simpan_status_ruas(self.id_ruas, hasil, total_occ, hasil_mkji)
        except Exception as e:
            logger.error(f"[DB] Gagal simpan status: {e}")

if __name__ == "__main__":
    app = MqttConsumerApp(sys.argv[1] if len(sys.argv) > 1 else "config/config.yaml")
    app.start()
