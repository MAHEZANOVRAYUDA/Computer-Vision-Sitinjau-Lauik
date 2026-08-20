"""
test_event_publisher.py
========================
Unit test untuk modul event_publisher.py.

Fokus pengujian:
1. Event tersimpan ke buffer lokal saat MQTT tidak terhubung
2. Buffer di-drain otomatis saat koneksi kembali (on_connect)
3. Event terkirim normal saat terhubung
4. Buffer tidak crash jika file tidak ada / rusak

Cara menjalankan:
    pytest tests/test_event_publisher.py -v
"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.config_loader import Config
from src.event_publisher import EventPublisher


def buat_publisher_mock(tmp_path: Path):
    """
    Helper: buat EventPublisher dengan:
    - MQTT client di-mock (tidak butuh broker nyata)
    - Buffer path diarahkan ke direktori temporer test
    """
    from src.config_loader import Config
    config = Config({
        "mqtt": {
            "broker_host": "localhost",
            "broker_port": 1883,
            "topic_prefix": "test_sitinjau",
            "client_id": "test_edge",
        }
    })

    buffer_path = tmp_path / "mqtt_buffer.jsonl"

    # Patch _BUFFER_PATH di module event_publisher
    with patch("event_publisher._BUFFER_PATH", buffer_path):
        import src.event_publisher as ep_module
        # Juga patch psycopg2 jika ikut terimport
        with patch("paho.mqtt.client.Client") as MockMQTTClient:
            mock_client = MagicMock()
            MockMQTTClient.return_value = mock_client

            from src.event_publisher import EventPublisher
            pub = EventPublisher(config)
            pub.client = mock_client

    return pub, buffer_path


class TestBufferLokal:

    def test_event_disimpan_ke_buffer_saat_tidak_terhubung(self, tmp_path):
        """
        Saat _terhubung=False, kirim_event_hitungan() harus menyimpan event
        ke file buffer lokal, bukan mengirim ke MQTT atau membuangnya.
        """
        buffer_path = tmp_path / "test_buffer.jsonl"

        from src.config_loader import Config
        config = Config({"mqtt": {"broker_host": "localhost", "broker_port": 1883,
                                  "topic_prefix": "sitinjau", "client_id": "test"}})
        from src.event_publisher import EventPublisher
        pub = EventPublisher(config)
        pub._buffer_path = buffer_path
        pub._terhubung = False  # Simulasi: tidak terhubung

        pub.kirim_event_hitungan(
            gerbang_id="gerbang_a",
            line_id="lajur_kiri",
            arah="masuk",
            kelas="motor",
            track_id=42,
        )

        assert buffer_path.exists(), "Buffer file harus dibuat saat tidak terhubung"
        baris = buffer_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(baris) == 1, "Harus ada tepat 1 baris di buffer"

        entry = json.loads(baris[0])
        assert "topic" in entry
        assert "payload" in entry
        payload = json.loads(entry["payload"])
        assert payload["gerbang_id"] == "gerbang_a"
        assert payload["kelas"] == "motor"

    def test_agregasi_disimpan_ke_buffer_saat_tidak_terhubung(self, tmp_path):
        """kirim_agregasi_interval() juga harus buffer saat offline."""
        buffer_path = tmp_path / "test_buffer2.jsonl"

        from src.config_loader import Config
        config = Config({"mqtt": {"broker_host": "localhost", "broker_port": 1883,
                                  "topic_prefix": "sitinjau", "client_id": "test"}})
        from src.event_publisher import EventPublisher
        pub = EventPublisher(config)
        pub._buffer_path = buffer_path
        pub._terhubung = False

        pub.kirim_agregasi_interval("gerbang_a", {"masuk_motor": 10, "keluar_mobil": 5})

        assert buffer_path.exists()
        baris = buffer_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(baris) == 1
        entry = json.loads(baris[0])
        payload = json.loads(entry["payload"])
        assert payload["counter"]["masuk_motor"] == 10

    def test_banyak_event_tertambah_di_buffer(self, tmp_path):
        """Beberapa event saat offline harus menumpuk di buffer (append mode)."""
        buffer_path = tmp_path / "test_multi.jsonl"

        from src.config_loader import Config
        config = Config({"mqtt": {"broker_host": "localhost", "broker_port": 1883,
                                  "topic_prefix": "sitinjau", "client_id": "test"}})
        from src.event_publisher import EventPublisher
        pub = EventPublisher(config)
        pub._buffer_path = buffer_path
        pub._terhubung = False

        for i in range(5):
            pub.kirim_event_hitungan("gerbang_a", "lajur_kiri", "masuk", "motor", i)

        baris = buffer_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(baris) == 5


class TestDrainBuffer:

    def test_drain_mengirim_semua_buffer_dan_hapus_file(self, tmp_path):
        """
        Saat _drain_buffer() dipanggil dan MQTT terhubung,
        semua entry di buffer harus dikirim dan file buffer dihapus.
        """
        buffer_path = tmp_path / "drain_test.jsonl"

        # Siapkan buffer dengan 3 entry
        entries = [
            {"topic": "sitinjau/gerbang_a/event", "payload": json.dumps({"test": i})}
            for i in range(3)
        ]
        buffer_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        from src.config_loader import Config
        config = Config({"mqtt": {"broker_host": "localhost", "broker_port": 1883,
                                  "topic_prefix": "sitinjau", "client_id": "test"}})
        from src.event_publisher import EventPublisher
        pub = EventPublisher(config)
        pub._buffer_path = buffer_path
        pub._terhubung = True

        # Mock MQTT client publish
        mock_client = MagicMock()
        pub.client = mock_client

        pub._drain_buffer()

        # Harus publish 3 kali
        assert mock_client.publish.call_count == 3
        # Buffer file harus dihapus setelah drain
        assert not buffer_path.exists(), "Buffer file harus dihapus setelah berhasil drain"

    def test_drain_tidak_crash_jika_buffer_kosong(self, tmp_path):
        """_drain_buffer() tidak boleh crash jika file buffer tidak ada atau kosong."""
        buffer_path = tmp_path / "nonexistent.jsonl"

        from src.config_loader import Config
        config = Config({"mqtt": {"broker_host": "localhost", "broker_port": 1883,
                                  "topic_prefix": "sitinjau", "client_id": "test"}})
        from src.event_publisher import EventPublisher
        pub = EventPublisher(config)
        pub._buffer_path = buffer_path
        pub._terhubung = True
        pub.client = MagicMock()

        # Tidak boleh raise exception
        pub._drain_buffer()


class TestKirimNormal:

    def test_event_dikirim_via_mqtt_saat_terhubung(self):
        """Saat terhubung, event harus langsung di-publish via MQTT."""
        from src.config_loader import Config
        config = Config({"mqtt": {"broker_host": "localhost", "broker_port": 1883,
                                  "topic_prefix": "sitinjau", "client_id": "test"}})
        from src.event_publisher import EventPublisher
        pub = EventPublisher(config)
        pub._terhubung = True
        mock_client = MagicMock()
        pub.client = mock_client

        pub.kirim_event_hitungan("gerbang_a", "lajur_kiri", "masuk", "motor", 99)

        assert mock_client.publish.call_count == 1
        args = mock_client.publish.call_args
        topic = args[0][0]
        payload_str = args[0][1]
        assert "gerbang_a" in topic
        payload = json.loads(payload_str)
        assert payload["kelas"] == "motor"
        assert payload["track_id"] == 99
