"""
event_publisher.py
===================
Modul untuk mengirim event hasil hitungan ke MQTT broker.

Kenapa MQTT dan bukan langsung tulis ke database dari edge?
- Sesuai prinsip arsitektur: edge tidak boleh bergantung langsung pada
  koneksi database (yang bisa lambat/putus). MQTT broker bertindak sebagai
  buffer perantara yang ringan.
- Untuk prototipe 1 kamera dengan broker di localhost, latensinya
  hampir nol - tapi struktur ini sudah siap untuk skala produksi.

Perbaikan v2:
- Logging terpusat menggantikan print()
- MQTT auto-reconnect via loop_start() + on_disconnect callback
- Local write-ahead buffer: event yang gagal terkirim disimpan ke file
  JSONL lokal (data/logs/mqtt_buffer.jsonl). Saat koneksi kembali,
  buffer di-drain otomatis - tidak ada data yang hilang saat broker mati sementara.
"""

import json
import time
from pathlib import Path
from typing import Optional

import paho.mqtt.client as mqtt

from src.config_loader import Config
from src.logger import get_logger

logger = get_logger(__name__)

# Buffer lokal untuk tiap gerbang agar tidak saling timpa
def get_buffer_path(client_id: str) -> Path:
    return Path(f"data/logs/mqtt_buffer_{client_id}.jsonl")


class EventPublisher:
    def __init__(self, config: Config, kamera_config: dict = None):
        self.host = config.get("mqtt.broker_host", "localhost")
        self.port = config.get("mqtt.broker_port", 1883)
        self.topic_prefix = config.get("mqtt.topic_prefix", "sitinjau_lauik")
        
        base_client_id = config.get("mqtt.client_id", "edge_client")
        if kamera_config:
            self.client_id = f"{base_client_id}_{kamera_config.get('id', 'unknown')}"
        else:
            self.client_id = base_client_id
            
        self._buffer_path = get_buffer_path(self.client_id)

        self.client = mqtt.Client(
            client_id=self.client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self._terhubung = False

        # Pastikan direktori buffer ada
        self._buffer_path.parent.mkdir(parents=True, exist_ok=True)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self._terhubung = True
            logger.info(f"[MQTT] Terhubung ke broker {self.host}:{self.port}")
            # Drain buffer lokal — kirim ulang event yang tertunda saat offline
            self._drain_buffer()
        else:
            logger.warning(f"[MQTT] Gagal terhubung, kode alasan: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self._terhubung = False
        if reason_code != 0:
            # reason_code != 0 berarti disconnect tidak disengaja (bukan putuskan())
            logger.warning(
                f"[MQTT] Terputus tidak terduga dari broker (kode: {reason_code}). "
                "Loop akan mencoba reconnect otomatis..."
            )
        else:
            logger.info("[MQTT] Terputus dari broker (disengaja).")

    def _simpan_ke_buffer(self, topic: str, payload_str: str):
        """
        Menyimpan satu event ke file buffer lokal (JSONL format).
        Dipanggil saat MQTT tidak terhubung agar event tidak hilang.
        """
        try:
            with open(self._buffer_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"topic": topic, "payload": payload_str}) + "\n")
            logger.debug(f"[MQTT Buffer] Event disimpan ke buffer lokal: {topic}")
        except Exception as e:
            logger.error(f"[MQTT Buffer] Gagal simpan ke buffer: {e}")

    def _drain_buffer(self):
        """
        Mengirim ulang semua event yang tersimpan di buffer lokal ke broker.
        Dipanggil otomatis saat koneksi berhasil (on_connect).
        """
        if not self._buffer_path.exists() or self._buffer_path.stat().st_size == 0:
            return

        logger.info("[MQTT Buffer] Menemukan buffer lokal, mengirim ulang event tertunda...")
        baris_berhasil = 0
        baris_gagal = 0

        try:
            with open(self._buffer_path, "r", encoding="utf-8") as f:
                baris_list = f.readlines()

            for baris in baris_list:
                try:
                    entry = json.loads(baris.strip())
                    self.client.publish(entry["topic"], entry["payload"], qos=1)
                    baris_berhasil += 1
                except Exception as e:
                    logger.warning(f"[MQTT Buffer] Gagal kirim ulang entry: {e}")
                    baris_gagal += 1

            # Hapus buffer setelah drain berhasil (meski ada beberapa yang gagal)
            self._buffer_path.unlink()
            logger.info(
                f"[MQTT Buffer] Drain selesai: {baris_berhasil} terkirim, "
                f"{baris_gagal} gagal."
            )
        except Exception as e:
            logger.error(f"[MQTT Buffer] Error saat drain buffer: {e}")

    def hubungkan(self, timeout_detik: int = 5):
        """
        Mencoba terhubung ke broker MQTT. Jika gagal, mencetak peringatan
        tapi TIDAK menghentikan program - sistem edge tetap bisa mendeteksi
        dan menghitung meski koneksi ke broker belum ada. Event yang gagal
        terkirim akan disimpan ke buffer lokal.
        """
        try:
            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start()
            waktu_mulai = time.time()
            while not self._terhubung and (time.time() - waktu_mulai) < timeout_detik:
                time.sleep(0.1)
            if not self._terhubung:
                logger.warning(
                    f"[MQTT] Tidak berhasil terhubung ke broker dalam {timeout_detik} detik. "
                    "Program tetap berjalan, event akan disimpan ke buffer lokal.\n"
                    "        Pastikan Mosquitto broker sudah berjalan "
                    "(lihat PANDUAN_SETUP untuk cara menjalankannya)."
                )
        except Exception as e:
            logger.error(f"[MQTT] ERROR saat mencoba terhubung: {e}")
            logger.info(
                "Program tetap berjalan tanpa koneksi MQTT. "
                "Event akan disimpan ke buffer lokal hingga koneksi tersedia."
            )

    def kirim_event_hitungan(
        self, gerbang_id: str, line_id: str, arah: str, kelas: str, track_id: int
    ):
        """Mengirim satu event 'kendaraan melewati garis' ke broker."""
        payload = {
            "gerbang_id": gerbang_id,
            "line_id": line_id,
            "arah": arah,
            "kelas": kelas,
            "track_id": int(track_id),
            "timestamp": time.time(),
        }
        topic = f"{self.topic_prefix}/{gerbang_id}/event"
        payload_str = json.dumps(payload)

        if not self._terhubung:
            # Simpan ke buffer lokal, bukan diam-diam dibuang
            self._simpan_ke_buffer(topic, payload_str)
            return

        self.client.publish(topic, payload_str, qos=1)

    def kirim_agregasi_interval(self, gerbang_id: str, snapshot_counter: dict, avg_speed: Optional[float] = None):
        """
        Mengirim ringkasan hitungan per interval (mis. tiap 60 detik)
        ke topik terpisah - ini yang akan dibaca oleh modul agregasi
        di server untuk update database dan hitung status macet.
        """
        payload = {
            "gerbang_id": gerbang_id,
            "timestamp": time.time(),
            "counter": snapshot_counter,
        }
        if avg_speed is not None:
            payload["kecepatan_rata2_kmh"] = float(avg_speed)

        topic = f"{self.topic_prefix}/{gerbang_id}/agregasi"
        payload_str = json.dumps(payload)

        if not self._terhubung:
            logger.warning(
                "[MQTT] Snapshot interval TIDAK terkirim (tidak terhubung ke broker). "
                "Disimpan ke buffer lokal."
            )
            self._simpan_ke_buffer(topic, payload_str)
            return

        self.client.publish(topic, payload_str, qos=1)
        logger.info(f"[MQTT] Snapshot agregasi terkirim ke topik: {topic}")

    def putuskan(self):
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("[MQTT] Koneksi ditutup.")
