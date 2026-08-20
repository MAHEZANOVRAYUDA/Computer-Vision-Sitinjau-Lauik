"""
database.py
============
Modul untuk operasi database PostgreSQL, dipakai oleh server
(mqtt_consumer.py dan api_server.py).

Perbaikan v2:
- SQL INTERVAL menggunakan make_interval() yang aman dari injection
- Validasi format key sebelum parse di simpan_hitungan_interval()
- Auto-reconnect: koneksi yang drop (setelah idle lama) di-reconnect otomatis
- Logging terpusat menggantikan print()
"""

import time
from contextlib import contextmanager
from typing import Dict, List, Optional

import psycopg2
import psycopg2.extras

from src.config_loader import Config
from src.logger import get_logger

logger = get_logger(__name__)

# Set arah yang valid untuk validasi key
_ARAH_VALID = {"masuk", "keluar"}


class Database:
    def __init__(self, config: Config):
        self.host = config.get("database.host", "localhost")
        self.port = config.get("database.port", 5432)
        self.name = config.get("database.name", "sitinjau_lauik_db")
        self.user = config.get("database.user", "postgres")
        self.password = config.get("database.password", "")
        self._conn: Optional[psycopg2.extensions.connection] = None

    def hubungkan(self):
        """Membuka koneksi ke database. Bisa dipanggil ulang untuk reconnect."""
        try:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
            self._conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.name,
                user=self.user,
                password=self.password,
                connect_timeout=10,
            )
            self._conn.autocommit = True
            logger.info(f"Terhubung ke database '{self.name}' di {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Gagal terhubung ke database: {e}")
            logger.error(
                "Pastikan PostgreSQL sudah berjalan dan database sudah dibuat "
                "(lihat scripts/setup_database.sql)."
            )
            raise

    def _ensure_connected(self):
        """
        Memastikan koneksi database aktif. Jika koneksi drop (setelah idle
        lama, atau jaringan putus sesaat), reconnect otomatis sebelum query.

        Ini mencegah error 'connection already closed' yang membutuhkan
        restart manual proses server.
        """
        try:
            if self._conn is None or self._conn.closed:
                logger.warning("Koneksi DB tidak ada/tertutup, mencoba reconnect...")
                self.hubungkan()
                return
            # Ping koneksi dengan query ringan
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
        except psycopg2.OperationalError:
            logger.warning("Koneksi DB terputus, mencoba reconnect...")
            self.hubungkan()
        except Exception as e:
            logger.error(f"Error saat cek koneksi DB: {e}")
            raise

    @contextmanager
    def _cursor(self):
        """
        Context manager untuk mendapatkan cursor dengan auto-reconnect.
        Menjamin cursor selalu ditutup setelah dipakai.
        """
        self._ensure_connected()
        cursor = self._conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    @contextmanager
    def _dict_cursor(self):
        """Context manager seperti _cursor() tapi mengembalikan RealDictCursor."""
        self._ensure_connected()
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cursor
        finally:
            cursor.close()

    def simpan_hitungan_interval(
        self,
        gerbang_id: str,
        timestamp_interval,
        rincian_per_lajur_arah_kelas: Dict[str, int],
    ):
        """
        Menyimpan hasil agregasi 1 interval ke tabel hitungan_kendaraan.
        rincian_per_lajur_arah_kelas contoh: {"masuk_motor": 12, "keluar_mobil": 5}

        Perbaikan: validasi format key sebelum parse untuk menghindari
        ValueError 'not enough values to unpack' jika format key tidak sesuai.
        """
        with self._cursor() as cursor:
            for key, jumlah in rincian_per_lajur_arah_kelas.items():
                if jumlah == 0:
                    continue

                # Validasi format key: harus "arah_kelas" dengan maxsplit=1
                parts = key.split("_", 1)
                if len(parts) != 2:
                    logger.warning(
                        f"Format key tidak valid (dilewati): '{key}'. "
                        "Diharapkan format 'arah_kelas' mis. 'masuk_motor'."
                    )
                    continue

                arah, kelas = parts
                if arah not in _ARAH_VALID:
                    logger.warning(
                        f"Arah tidak dikenal '{arah}' di key '{key}' (dilewati). "
                        f"Nilai valid: {_ARAH_VALID}"
                    )
                    continue

                cursor.execute(
                    """
                    INSERT INTO hitungan_kendaraan
                        (id_gerbang, timestamp_interval, lajur_id, arah, jenis_kendaraan, jumlah_terhitung)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (gerbang_id, timestamp_interval, "gabungan", arah, kelas, jumlah),
                )

    def ambil_hitungan_terbaru(self, menit_terakhir: int = 5) -> List[Dict]:
        """
        Mengambil hitungan_kendaraan dalam N menit terakhir.

        Perbaikan: menggunakan make_interval(mins => %s) sebagai ganti
        INTERVAL '%s minutes' yang tidak ter-parameterisasi dengan benar
        oleh psycopg2 dan berpotensi error atau injection.
        """
        with self._dict_cursor() as cursor:
            cursor.execute(
                """
                SELECT id_gerbang, arah, jenis_kendaraan, SUM(jumlah_terhitung) as total
                FROM hitungan_kendaraan
                WHERE timestamp_interval >= NOW() - make_interval(mins => %s)
                GROUP BY id_gerbang, arah, jenis_kendaraan
                """,
                (int(menit_terakhir),),
            )
            return cursor.fetchall()

    def simpan_status_ruas(self, id_ruas: int, hasil_klasifikasi, total_kendaraan_saat_ini: int, hasil_mkji=None):
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO status_ruas
                    (id_ruas, timestamp_hitung, total_kendaraan_saat_ini,
                     volume_smp, rasio_vc, level_of_service, status_label, teks_rekomendasi,
                     volume_smp_jam_mkji, kapasitas_smp_jam_mkji, rasio_vc_mkji,
                     level_of_service_mkji, status_label_mkji)
                VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    id_ruas,
                    total_kendaraan_saat_ini,
                    hasil_klasifikasi.volume_smp,
                    hasil_klasifikasi.rasio_vc,
                    hasil_klasifikasi.level_of_service,
                    hasil_klasifikasi.status_label,
                    hasil_klasifikasi.teks_rekomendasi,
                    hasil_mkji.volume_smp_per_jam if hasil_mkji else None,
                    hasil_mkji.kapasitas_smp_per_jam if hasil_mkji else None,
                    hasil_mkji.rasio_vc if hasil_mkji else None,
                    hasil_mkji.level_of_service if hasil_mkji else None,
                    hasil_mkji.status_label if hasil_mkji else None,
                ),
            )

    def ambil_status_terbaru(self) -> Optional[Dict]:
        with self._dict_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM status_ruas
                ORDER BY timestamp_hitung DESC
                LIMIT 1
                """
            )
            return cursor.fetchone()

    def ambil_riwayat_status(self, jam_terakhir: int = 24) -> List[Dict]:
        """
        Perbaikan: menggunakan make_interval(hours => %s) yang aman,
        identik dengan perbaikan di ambil_hitungan_terbaru().
        """
        with self._dict_cursor() as cursor:
            cursor.execute(
                """
                SELECT timestamp_hitung, total_kendaraan_saat_ini, rasio_vc, status_label
                FROM status_ruas
                WHERE timestamp_hitung >= NOW() - make_interval(hours => %s)
                ORDER BY timestamp_hitung ASC
                """,
                (int(jam_terakhir),),
            )
            return cursor.fetchall()

    def ambil_occupancy_hari_ini(self) -> Dict[str, int]:
        """
        Menghitung occupancy kumulatif hari ini dari database.
        Dipakai oleh mqtt_consumer.py saat startup untuk recovery state
        tanpa perlu restart dari nol.

        Return: dict {kelas: occupancy_net} mis. {"motor": 45, "mobil": 20}
        """
        with self._dict_cursor() as cursor:
            cursor.execute(
                """
                SELECT arah, jenis_kendaraan, SUM(jumlah_terhitung) as total
                FROM hitungan_kendaraan
                WHERE timestamp_interval >= CURRENT_DATE
                GROUP BY arah, jenis_kendaraan
                """
            )
            rows = cursor.fetchall()

        occupancy: Dict[str, int] = {}
        for row in rows:
            arah = row["arah"]
            kelas = row["jenis_kendaraan"]
            total = int(row["total"] or 0)

            if kelas not in occupancy:
                occupancy[kelas] = 0

            if arah == "masuk":
                occupancy[kelas] += total
            elif arah == "keluar":
                occupancy[kelas] = max(0, occupancy[kelas] - total)

        return occupancy

    def ambil_kumulatif_masuk_keluar_per_gerbang(self, sejak_jam: int = 24) -> dict:
        """
        Mengambil akumulasi mentah masuk/keluar per gerbang+kelas dalam
        N jam terakhir (bukan net) — untuk recovery state in-memory
        mqtt_consumer.py saat restart.

        Return: {
          "gerbang_a_masuk": {"motor": 120, "mobil": 45, ...},
          "gerbang_a_keluar": {...},
          "gerbang_b_masuk": {...},
          "gerbang_b_keluar": {...},
        }
        """
        with self._dict_cursor() as cursor:
            cursor.execute(
                """
                SELECT id_gerbang, arah, jenis_kendaraan, SUM(jumlah_terhitung) as total
                FROM hitungan_kendaraan
                WHERE timestamp_interval >= CURRENT_DATE
                GROUP BY id_gerbang, arah, jenis_kendaraan
                """,
            )
            rows = cursor.fetchall()

        hasil: Dict[str, Dict[str, int]] = {}
        for row in rows:
            gerbang = row["id_gerbang"]
            arah = row["arah"]
            kelas = row["jenis_kendaraan"]
            key = f"{gerbang}_{arah}"
            hasil.setdefault(key, {})[kelas] = int(row["total"] or 0)
        return hasil

    def ambil_status_gerbang(self) -> List[Dict]:
        """Mengambil daftar gerbang dan status perangkatnya dari tabel gerbang_kamera."""
        with self._dict_cursor() as cursor:
            cursor.execute(
                """
                SELECT id_gerbang, nama_gerbang, arah_menghadap, status_perangkat
                FROM gerbang_kamera
                ORDER BY id_gerbang
                """
            )
            return cursor.fetchall()

    def tutup(self):
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
            logger.info("Koneksi database ditutup.")
