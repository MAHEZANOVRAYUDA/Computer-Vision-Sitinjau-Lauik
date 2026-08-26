"""
test_mkji.py
=============
Unit test untuk modul mkji.py — verifikasi implementasi MKJI 1997
mencakup semua fungsi inti: volume smp, kapasitas, LOS, dan evaluasi end-to-end.

Cara menjalankan:
    pytest tests/test_mkji.py -v
"""

import pytest
from src.mkji import (
    hitung_volume_smp,
    hitung_kapasitas_mkji,
    tentukan_los_mkji,
    klasifikasi_status_mkji,
    evaluasi_mkji,
    EMP_GUNUNG,
    C0_2_2_UD,
    HasilMKJI,
)


# -----------------------------------------------------------------------
# Test: hitung_volume_smp()
# -----------------------------------------------------------------------

class TestHitungVolumeSmp:

    def test_motor_saja(self):
        """Motor dengan EMP 0.4: 100 motor = 40 smp."""
        hasil = hitung_volume_smp({"motor": 100})
        assert abs(hasil - 40.0) < 0.01

    def test_mobil_saja(self):
        """Mobil dengan EMP 1.0: 100 mobil = 100 smp."""
        hasil = hitung_volume_smp({"mobil": 100})
        assert abs(hasil - 100.0) < 0.01

    def test_bus_saja(self):
        """Bus dengan EMP 3.25: 10 bus = 32.5 smp."""
        hasil = hitung_volume_smp({"bus": 10})
        assert abs(hasil - 32.5) < 0.01

    def test_truk_saja(self):
        """Truk dengan EMP 5.0: 10 truk = 50 smp."""
        hasil = hitung_volume_smp({"truk": 10})
        assert abs(hasil - 50.0) < 0.01

    def test_kombinasi_semua_kelas(self):
        """Kombinasi semua kelas kendaraan."""
        # 450 motor + 200 mobil + 10 bus + 30 truk
        # = 450*0.4 + 200*1.0 + 10*3.25 + 30*5.0
        # = 180 + 200 + 32.5 + 150 = 562.5
        hasil = hitung_volume_smp({
            "motor": 450,
            "mobil": 200,
            "bus": 10,
            "truk": 30,
        })
        assert abs(hasil - 562.5) < 0.01

    def test_volume_nol(self):
        """Tidak ada kendaraan = volume 0 smp."""
        hasil = hitung_volume_smp({"motor": 0, "mobil": 0})
        assert hasil == 0.0

    def test_kelas_tidak_dikenal_pakai_emp_default_1(self):
        """Kelas kendaraan tidak dikenal menggunakan EMP default 1.0."""
        hasil = hitung_volume_smp({"kendaraan_aneh": 50})
        assert abs(hasil - 50.0) < 0.01

    def test_emp_custom(self):
        """EMP kustom mengganti EMP default."""
        emp_custom = {"motor": 0.5, "mobil": 1.2}
        hasil = hitung_volume_smp({"motor": 100, "mobil": 50}, emp=emp_custom)
        # 100*0.5 + 50*1.2 = 50 + 60 = 110
        assert abs(hasil - 110.0) < 0.01


# -----------------------------------------------------------------------
# Test: hitung_kapasitas_mkji()
# -----------------------------------------------------------------------

class TestHitungKapasitasMkji:

    def test_kapasitas_default(self):
        """Kapasitas dasar 2/2 UD = 2900, default fc_w = 0.9 maka 2900*0.9 = 2610."""
        kapasitas = hitung_kapasitas_mkji()
        assert abs(kapasitas - 2610.0) < 0.01

    def test_kapasitas_dengan_semua_fc_1(self):
        """Semua faktor koreksi = 1.0, fc_w = 1.0: kapasitas = C0 penuh."""
        kapasitas = hitung_kapasitas_mkji(fc_w=1.0, fc_sp=1.0, fc_sf=1.0, fc_cs=1.0)
        assert abs(kapasitas - 2900.0) < 0.01

    def test_fc_mengurangi_kapasitas(self):
        """Faktor koreksi < 1 mengurangi kapasitas."""
        kapasitas_penuh = hitung_kapasitas_mkji(fc_w=1.0)
        kapasitas_dikurangi = hitung_kapasitas_mkji(fc_w=0.85)
        assert kapasitas_dikurangi < kapasitas_penuh


# -----------------------------------------------------------------------
# Test: tentukan_los_mkji()
# -----------------------------------------------------------------------

class TestTentukanLosMkji:

    def test_los_a_batas_bawah(self):
        assert tentukan_los_mkji(0.0) == "A"

    def test_los_a_batas_atas(self):
        assert tentukan_los_mkji(0.20) == "A"

    def test_los_b_batas_bawah(self):
        assert tentukan_los_mkji(0.21) == "B"

    def test_los_b_batas_atas(self):
        assert tentukan_los_mkji(0.44) == "B"

    def test_los_c_batas_bawah(self):
        assert tentukan_los_mkji(0.45) == "C"

    def test_los_c_batas_atas(self):
        assert tentukan_los_mkji(0.75) == "C"

    def test_los_d_batas_bawah(self):
        assert tentukan_los_mkji(0.76) == "D"

    def test_los_d_batas_atas(self):
        assert tentukan_los_mkji(0.84) == "D"

    def test_los_e_batas_bawah(self):
        assert tentukan_los_mkji(0.85) == "E"

    def test_los_e_batas_atas(self):
        assert tentukan_los_mkji(1.00) == "E"

    def test_los_f_batas_bawah(self):
        assert tentukan_los_mkji(1.01) == "F"

    def test_los_f_sangat_tinggi(self):
        assert tentukan_los_mkji(2.0) == "F"

    def test_semua_batas_tepat(self):
        """Verifikasi semua nilai batas tepat di MKJI 1997."""
        batas = {
            0.20: "A",
            0.44: "B",
            0.75: "C",
            0.84: "D",
            1.00: "E",
        }
        for rasio, los_expected in batas.items():
            assert tentukan_los_mkji(rasio) == los_expected, (
                f"V/C={rasio} seharusnya LOS {los_expected}, "
                f"dapat {tentukan_los_mkji(rasio)}"
            )


# -----------------------------------------------------------------------
# Test: klasifikasi_status_mkji()
# -----------------------------------------------------------------------

class TestKlasifikasiStatusMkji:

    def test_lancar(self):
        assert klasifikasi_status_mkji(0.3) == "lancar"

    def test_tepat_di_batas_lancar(self):
        assert klasifikasi_status_mkji(0.44) == "lancar"

    def test_padat(self):
        assert klasifikasi_status_mkji(0.70) == "padat"

    def test_tepat_di_batas_padat(self):
        assert klasifikasi_status_mkji(0.84) == "padat"

    def test_macet(self):
        assert klasifikasi_status_mkji(0.95) == "macet"

    def test_macet_ekstrem(self):
        assert klasifikasi_status_mkji(2.0) == "macet"


# -----------------------------------------------------------------------
# Test: evaluasi_mkji() — end-to-end
# -----------------------------------------------------------------------

class TestEvaluasiMkji:

    def test_hasil_bertipe_HasilMKJI(self):
        """Hasil evaluasi harus bertipe HasilMKJI."""
        hasil = evaluasi_mkji({"mobil": 100})
        assert isinstance(hasil, HasilMKJI)

    def test_volume_nol_los_a(self):
        """Volume 0 kendaraan = V/C mendekati 0 = LOS A = lancar."""
        hasil = evaluasi_mkji({"motor": 0, "mobil": 0})
        assert hasil.rasio_vc == 0.0
        assert hasil.level_of_service == "A"
        assert hasil.status_label == "lancar"

    def test_kapasitas_negatif_raises(self):
        """Jika FC negatif menyebabkan kapasitas <= 0, harus raise ValueError."""
        with pytest.raises(ValueError, match="Kapasitas"):
            evaluasi_mkji({"mobil": 100}, fc_w=-1.0)

    def test_rasio_vc_konsisten(self):
        """Cek bahwa rasio_vc = volume_smp / kapasitas."""
        hasil = evaluasi_mkji(
            {"motor": 1000, "mobil": 500},
            fc_w=0.90,
            fc_sp=1.0,
            fc_sf=1.0,
            fc_cs=1.0,
        )
        volume_expected = hitung_volume_smp({"motor": 1000, "mobil": 500})
        kapasitas_expected = hitung_kapasitas_mkji(0.90)
        vc_expected = volume_expected / kapasitas_expected
        assert abs(hasil.rasio_vc - round(vc_expected, 4)) < 0.0001

    def test_end_to_end_contoh_mkji(self):
        """
        Contoh kalkulasi manual:
        - 450 motor/jam, 200 mobil/jam, 10 bus/jam, 30 truk/jam
        - fc_w=0.90
        - Volume smp = 450*0.4 + 200*1.0 + 10*3.25 + 30*5.0 = 562.5 smp/jam
        - Kapasitas = 2900 * 0.9 = 2610 smp/jam
        - V/C = 562.5 / 2610 ≈ 0.2155 -> LOS B -> lancar
        """
        hasil = evaluasi_mkji(
            {"motor": 450, "mobil": 200, "bus": 10, "truk": 30},
            fc_w=0.90,
        )
        assert abs(hasil.volume_smp_per_jam - 562.5) < 0.01
        assert abs(hasil.kapasitas_smp_per_jam - 2610.0) < 0.01
        assert abs(hasil.rasio_vc - round(562.5 / 2610.0, 4)) < 0.0001
        assert hasil.level_of_service == "B"
        assert hasil.status_label == "lancar"

    def test_kondisi_macet(self):
        """Volume tinggi -> V/C > 1.0 -> LOS F -> macet."""
        # Volume sangat tinggi agar V/C > 1.0
        hasil = evaluasi_mkji(
            {"motor": 5000, "mobil": 3000, "bus": 50, "truk": 100},
        )
        assert hasil.rasio_vc > 1.0
        assert hasil.level_of_service == "F"
        assert hasil.status_label == "macet"

    def test_emp_gunung_default_dipakai(self):
        """Jika emp=None, harus menggunakan EMP_GUNUNG sebagai default."""
        hasil_default = evaluasi_mkji({"motor": 100}, emp=None)
        hasil_explicit = evaluasi_mkji({"motor": 100}, emp=EMP_GUNUNG)
        assert hasil_default.volume_smp_per_jam == hasil_explicit.volume_smp_per_jam
