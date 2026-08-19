"""
test_database.py
=================
Unit test untuk modul database.py.

Fokus pengujian:
1. Validasi format key di simpan_hitungan_interval() — key invalid dilewati, tidak crash
2. SQL parameterisasi make_interval() benar (tidak ada interpolasi string berbahaya)
3. ambil_occupancy_hari_ini() menghitung net occupancy dengan benar

Strategi mocking:
- `_ensure_connected()` di-bypass dengan langsung set `db._conn` yang sudah terhubung
- Cursor di-mock sebagai context manager yang kompatibel dengan `@contextmanager _cursor()`

Cara menjalankan:
    pytest tests/test_database.py -v
"""

import logging
from unittest.mock import MagicMock, patch, call, PropertyMock

import pytest

from src.database import Database, _ARAH_VALID


# -----------------------------------------------------------------------
# Fixture: Database dengan koneksi mock
# -----------------------------------------------------------------------

def buat_db_mock():
    """
    Membuat instance Database dengan _conn yang sudah di-mock.
    
    Kunci: mock _ensure_connected() agar tidak melakukan SELECT 1 ekstra,
    sehingga execute.call_count hanya menghitung query bisnis yang kita uji.
    """
    from src.config_loader import Config
    config = Config({
        "database": {
            "host": "localhost", "port": 5432,
            "name": "test_db", "user": "test", "password": "test",
        }
    })
    db = Database(config)

    # Setup mock connection
    mock_conn = MagicMock()
    mock_conn.closed = False

    # Mock cursor sebagai context manager (kompatibel dengan psycopg2 cursor)
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    db._conn = mock_conn

    return db, mock_conn, mock_cursor


# -----------------------------------------------------------------------
# Tes: simpan_hitungan_interval()
# -----------------------------------------------------------------------

class TestSimpanHitunganInterval:

    def test_key_valid_diinsert(self):
        """Key format 'masuk_motor' yang valid harus menghasilkan INSERT ke DB."""
        db, mock_conn, mock_cursor = buat_db_mock()

        # Patch _ensure_connected supaya tidak melakukan SELECT 1
        with patch.object(db, '_ensure_connected'):
            db.simpan_hitungan_interval(
                gerbang_id="gerbang_a",
                timestamp_interval="2024-01-01 08:00:00",
                rincian_per_lajur_arah_kelas={"masuk_motor": 10, "keluar_mobil": 5},
            )

        # Harus ada 2 INSERT (1 per key valid)
        assert mock_cursor.execute.call_count == 2

    def test_key_jumlah_nol_dilewati(self):
        """Key dengan jumlah=0 tidak boleh menghasilkan INSERT."""
        db, mock_conn, mock_cursor = buat_db_mock()

        with patch.object(db, '_ensure_connected'):
            db.simpan_hitungan_interval(
                gerbang_id="gerbang_a",
                timestamp_interval="2024-01-01 08:00:00",
                rincian_per_lajur_arah_kelas={"masuk_motor": 0, "keluar_mobil": 0},
            )

        assert mock_cursor.execute.call_count == 0

    def test_key_tanpa_underscore_pair_tidak_crash(self, caplog):
        """
        Key 'kunci_tanpa_format_benar_xyz' akan di-split menjadi ('kunci', 'tanpa_format_benar_xyz').
        'kunci' bukan arah valid -> log WARNING dan di-skip, tidak crash.
        """
        db, mock_conn, mock_cursor = buat_db_mock()

        with patch.object(db, '_ensure_connected'), \
             caplog.at_level(logging.WARNING):
            db.simpan_hitungan_interval(
                gerbang_id="gerbang_a",
                timestamp_interval="2024-01-01 08:00:00",
                rincian_per_lajur_arah_kelas={"kunci_tanpa_format_benar_xyz": 5},
            )

        # Tidak ada INSERT
        assert mock_cursor.execute.call_count == 0
        # Harus ada log warning tentang arah tidak dikenal
        assert any(
            "arah tidak dikenal" in r.message.lower() or "format key tidak valid" in r.message.lower()
            for r in caplog.records
        )

    def test_key_arah_tidak_valid_dilewati(self, caplog):
        """Key dengan arah bukan 'masuk'/'keluar' harus di-skip dengan warning."""
        db, mock_conn, mock_cursor = buat_db_mock()

        with patch.object(db, '_ensure_connected'), \
             caplog.at_level(logging.WARNING):
            db.simpan_hitungan_interval(
                gerbang_id="gerbang_a",
                timestamp_interval="2024-01-01 08:00:00",
                rincian_per_lajur_arah_kelas={"lewat_motor": 8},
            )

        assert mock_cursor.execute.call_count == 0
        assert any("arah tidak dikenal" in r.message.lower() for r in caplog.records)

    def test_campuran_key_valid_dan_invalid(self):
        """Campuran key valid dan invalid: hanya yang valid yang diinsert."""
        db, mock_conn, mock_cursor = buat_db_mock()

        with patch.object(db, '_ensure_connected'):
            db.simpan_hitungan_interval(
                gerbang_id="gerbang_a",
                timestamp_interval="2024-01-01 08:00:00",
                rincian_per_lajur_arah_kelas={
                    "masuk_motor": 10,   # valid
                    "salah_kelas": 3,    # arah "salah" tidak valid
                    "keluar_truk": 2,    # valid
                    "lewat_bus": 1,      # arah "lewat" tidak valid
                },
            )

        # Hanya 2 key valid: masuk_motor dan keluar_truk
        assert mock_cursor.execute.call_count == 2


# -----------------------------------------------------------------------
# Tes: Konstanta _ARAH_VALID
# -----------------------------------------------------------------------

def test_arah_valid_berisi_masuk_dan_keluar():
    """Konstanta validasi arah harus tepat berisi 'masuk' dan 'keluar'."""
    assert "masuk" in _ARAH_VALID
    assert "keluar" in _ARAH_VALID
    assert len(_ARAH_VALID) == 2


# -----------------------------------------------------------------------
# Tes: ambil_hitungan_terbaru() — verifikasi SQL menggunakan make_interval
# -----------------------------------------------------------------------

class TestAmbilHitunganTerbaru:

    def test_sql_menggunakan_make_interval(self):
        """
        Memverifikasi bahwa query SQL menggunakan make_interval(mins => %s).
        Ini adalah test regresi untuk Bug #2 (SQL INTERVAL parameterisasi).
        """
        db, mock_conn, mock_cursor = buat_db_mock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db, '_ensure_connected'):
            db.ambil_hitungan_terbaru(menit_terakhir=5)

        # Hanya 1 execute (query SELECT utama)
        assert mock_cursor.execute.call_count == 1
        sql_dieksekusi = mock_cursor.execute.call_args[0][0]

        assert "make_interval" in sql_dieksekusi, (
            f"SQL harus menggunakan make_interval(). SQL aktual: {sql_dieksekusi}"
        )
        assert "INTERVAL '%s" not in sql_dieksekusi, (
            "SQL tidak boleh menggunakan format INTERVAL '%s minutes' yang tidak aman."
        )

    def test_parameter_dikirim_sebagai_integer(self):
        """Parameter menit_terakhir harus dikirim sebagai integer ke psycopg2."""
        db, mock_conn, mock_cursor = buat_db_mock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db, '_ensure_connected'):
            db.ambil_hitungan_terbaru(menit_terakhir=10)

        params = mock_cursor.execute.call_args[0][1]
        assert params == (10,)
        assert isinstance(params[0], int)


# -----------------------------------------------------------------------
# Tes: ambil_riwayat_status() — verifikasi SQL
# -----------------------------------------------------------------------

class TestAmbilRiwayatStatus:

    def test_sql_menggunakan_make_interval_hours(self):
        """Regresi test: ambil_riwayat_status() harus pakai make_interval(hours => %s)."""
        db, mock_conn, mock_cursor = buat_db_mock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db, '_ensure_connected'):
            db.ambil_riwayat_status(jam_terakhir=24)

        sql_dieksekusi = mock_cursor.execute.call_args[0][0]
        assert "make_interval" in sql_dieksekusi
        assert "INTERVAL '%s" not in sql_dieksekusi


# -----------------------------------------------------------------------
# Tes: ambil_occupancy_hari_ini()
# -----------------------------------------------------------------------

class TestAmbilOccupancyHariIni:

    def test_hitung_net_occupancy_benar(self):
        """Net occupancy = masuk - keluar per kelas, tidak boleh negatif."""
        db, mock_conn, mock_cursor = buat_db_mock()
        mock_cursor.fetchall.return_value = [
            {"arah": "masuk",  "jenis_kendaraan": "motor", "total": 50},
            {"arah": "keluar", "jenis_kendaraan": "motor", "total": 30},
            {"arah": "masuk",  "jenis_kendaraan": "mobil", "total": 20},
        ]

        with patch.object(db, '_ensure_connected'):
            hasil = db.ambil_occupancy_hari_ini()

        assert hasil["motor"] == 20
        assert hasil["mobil"] == 20

    def test_occupancy_tidak_negatif_jika_keluar_lebih_besar(self):
        """Jika keluar > masuk (error data), occupancy harus di-clamp ke 0."""
        db, mock_conn, mock_cursor = buat_db_mock()
        mock_cursor.fetchall.return_value = [
            {"arah": "masuk",  "jenis_kendaraan": "motor", "total": 10},
            {"arah": "keluar", "jenis_kendaraan": "motor", "total": 50},
        ]

        with patch.object(db, '_ensure_connected'):
            hasil = db.ambil_occupancy_hari_ini()

        assert hasil.get("motor", 0) == 0

    def test_kosong_jika_tidak_ada_data(self):
        """Jika database kosong, kembalikan dict kosong tanpa error."""
        db, mock_conn, mock_cursor = buat_db_mock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db, '_ensure_connected'):
            hasil = db.ambil_occupancy_hari_ini()

        assert hasil == {}
