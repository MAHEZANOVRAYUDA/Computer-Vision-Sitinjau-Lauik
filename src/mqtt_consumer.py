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
from datetime import datetime
from collections import defaultdict
from typing import Optional
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


def identifikasi_gerbang(gerbang_id) -> Optional[str]:
    """
    Pemetaan ID gerbang ke bucket occupancy A atau B.

    Jangan memakai `"a" in gerbang_id`: string "gerbang_b" mengandung huruf a.
    """
    if not gerbang_id:
        return None
    gl = str(gerbang_id).strip().lower()
    if gl in {"a", "gerbang_a"} or gl.endswith("/gerbang_a") or gl.endswith(":gerbang_a"):
        return "a"
    if gl.endswith("gerbang_a") and "gerbang_b" not in gl:
        return "a"
    if gl in {"b", "gerbang_b"} or gl.endswith("gerbang_b"):
        return "b"
    return None


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
        _naik = self.config.get("sistem_pakar.ambang_kecepatan_naik_kmh")
        _turun = self.config.get("sistem_pakar.ambang_kecepatan_turun_kmh")
        self.ambang_kecepatan_naik = float(_naik) if _naik is not None else None
        self.ambang_kecepatan_turun = float(_turun) if _turun is not None else None
        self.interval_detik = float(self.config.get("agregasi.interval_detik", 20))
        
        # State Occupancy & Thread Safety
        self.state_lock = threading.Lock()
        self.kumulatif_a_masuk = defaultdict(int)
        self.kumulatif_a_keluar = defaultdict(int)
        self.kumulatif_b_masuk = defaultdict(int)
        self.kumulatif_b_keluar = defaultdict(int)
        
        self.last_seen = {}
        self.status_gerbang = {}
        
    def _set_status(self, gerbang_id: str, status: str):
        if self.status_gerbang.get(gerbang_id) != status:
            self.status_gerbang[gerbang_id] = status
            try:
                self.db.update_status_gerbang(gerbang_id, status)
                logger.info(f"[Status Kamera] {gerbang_id} berubah menjadi {status.upper()}")
            except Exception as e:
                logger.error(f"[DB] Gagal update status gerbang: {e}")

    def _watchdog_loop(self):
        heartbeat_file = Path("data/logs/heartbeat_consumer.txt")
        heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                heartbeat_file.write_text(str(int(time.time())))
            except Exception:
                pass
            time.sleep(10)
            now = time.time()
            with self.state_lock:
                for gerbang_id, last_ts in list(self.last_seen.items()):
                    if now - last_ts > 60 and self.status_gerbang.get(gerbang_id) == "aktif":
                        self._set_status(gerbang_id, "offline")

    def start(self):
        logger.info("=" * 70)
        logger.info("SERVER CONSUMER - Sitinjau Lauik Traffic System (Production Mode)")
        logger.info("=" * 70)
        
        self.db.hubungkan()
        self.recover_state()
        self.jadwalkan_reset()
        
        t_watchdog = threading.Thread(target=self._watchdog_loop, daemon=True)
        t_watchdog.start()
        
        # MQTT Client
        self.client = mqtt.Client(client_id="server_consumer", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
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

    def _akumulasi_counter(self, gerbang_id, counter: dict):
        """Update kumulatif masuk/keluar per gerbang. Thread-safety: panggil di dalam state_lock."""
        gate = identifikasi_gerbang(gerbang_id)
        if gate is None:
            logger.warning(f"[Occupancy] gerbang_id tidak dikenali: {gerbang_id!r}")
            return
        for key, jumlah in (counter or {}).items():
            parts = str(key).split("_", 1)
            if len(parts) != 2:
                continue
            arah, kelas = parts
            if gate == "a":
                if arah == "masuk":
                    self.kumulatif_a_masuk[kelas] += jumlah
                elif arah == "keluar":
                    self.kumulatif_a_keluar[kelas] += jumlah
            elif gate == "b":
                if arah == "masuk":
                    self.kumulatif_b_masuk[kelas] += jumlah
                elif arah == "keluar":
                    self.kumulatif_b_keluar[kelas] += jumlah

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            topik_agregasi = f"{self.topic_prefix}/+/agregasi"
            topik_status = f"{self.topic_prefix}/+/status"
            topik_command = f"{self.topic_prefix}/command/reset"
            self.client.subscribe([(topik_agregasi, 1), (topik_status, 1), (topik_command, 1)])
            logger.info(f"[MQTT] Berlangganan topik agregasi, status, command")
        else:
            logger.error(f"[MQTT] Gagal terhubung: {reason_code}")

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        if topic == f"{self.topic_prefix}/command/reset":
            logger.info("[MQTT] Menerima perintah reset manual.")
            self.lakukan_reset_harian()
            return
            
        if topic.endswith("/status"):
            parts = topic.split("/")
            if len(parts) >= 3:
                gerbang_id = parts[1]
                try:
                    payload = json.loads(msg.payload.decode())
                    status = payload.get("status", "offline")
                    with self.state_lock:
                        self.last_seen[gerbang_id] = time.time()
                        self._set_status(gerbang_id, "aktif" if status == "online" else "offline")
                except Exception:
                    pass
            return
            
        try:
            payload = json.loads(msg.payload.decode())
        except Exception as e:
            logger.warning(f"[MQTT] Payload error: {e}")
            return
            
        gerbang_id = payload.get("gerbang_id")
        counter = payload.get("counter", {})
        ts = payload.get("timestamp", time.time())
        
        if gerbang_id:
            with self.state_lock:
                self.last_seen[gerbang_id] = time.time()
                self._set_status(gerbang_id, "aktif")
        
        # Deteksi drift
        if abs(time.time() - ts) > 5.0:
            logger.warning(f"[Clock Drift] {gerbang_id} drift {abs(time.time() - ts):.1f}s.")
            
        try:
            self.db.simpan_hitungan_interval(
                gerbang_id,
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
                counter,
                arah_topografi_map=payload.get("arah_topografi_map"),
            )
        except Exception as e:
            logger.error(f"[DB] Gagal simpan hitungan: {e}")
            return
            
        with self.state_lock:
            self._akumulasi_counter(gerbang_id, counter)
            try:
                occ = hitung_occupancy_ruas(self.kumulatif_a_masuk, self.kumulatif_b_keluar, self.kumulatif_b_masuk, self.kumulatif_a_keluar)
                jumlah_eval = occ.jumlah_per_kelas
            except Exception as e:
                logger.error(f"[Occupancy] Error: {e}")
                return

        total_occ = sum(jumlah_eval.values())
        kecepatan = payload.get("kecepatan_rata2_kmh")
        kecepatan_naik = payload.get("kecepatan_naik_kmh")
        kecepatan_turun = payload.get("kecepatan_turun_kmh")
        
        try:
            hasil = evaluasi(
                jumlah_eval,
                self.kapasitas,
                self.panjang_kendaraan,
                self.ambang_lancar,
                self.ambang_padat,
                None,
                None,
                kecepatan,
                self.ambang_kecepatan,
                kecepatan_naik,
                kecepatan_turun,
                self.ambang_kecepatan_naik,
                self.ambang_kecepatan_turun,
            )
        except Exception as e:
            logger.error(f"[Pakar] Error: {e}")
            return
            
        logger.info(f"[Pakar] Status: {hasil.status_label.upper()} | Kepadatan: {hasil.rasio_vc*100:.1f}%")
        
        # MKJI 1997
        hasil_mkji = None
        try:
            # Menggunakan rolling average 15 menit dari database untuk menstabilkan perhitungan MKJI
            riwayat_15_menit = self.db.ambil_hitungan_terbaru(menit_terakhir=15)
            
            flow_15m = defaultdict(int)
            for row in riwayat_15_menit:
                # Hanya hitung yang 'masuk' agar tidak double-counting (masuk dan keluar)
                if row.get("arah") == "masuk":
                    kelas = row.get("jenis_kendaraan")
                    if kelas:
                        flow_15m[kelas] += int(row.get("total") or 0)
            
            # Konversi dari 15 menit ke per jam (* 4)
            flow_jam = {k: v * 4.0 for k, v in flow_15m.items()}
            
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
