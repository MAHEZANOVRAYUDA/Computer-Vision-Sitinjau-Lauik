import pytest
from src.sistem_pakar import evaluasi
from src.mkji import evaluasi_mkji

class TestPerbandinganMetodologi:
    """
    Skenario test ini membandingkan hasil evaluasi Occupancy-Based (Sistem Pakar)
    dengan hasil V/C MKJI 1997 menggunakan data sintetis yang sama.
    """

    def test_perbandingan_hasil_lancar(self):
        # 1. Dataset sintetis: Kondisi sepi
        jumlah_kendaraan = {
            "motor": 10,
            "mobil": 5,
            "bus": 0,
            "truk": 1
        }
        
        # Ekstrapolasi 15 menit ke 1 jam untuk MKJI
        jumlah_per_jam = {k: v * 4 for k, v in jumlah_kendaraan.items()}

        # 2. Parameter Occupancy
        kapasitas_meter_lajur = 56100.0
        panjang_kendaraan = {"motor": 2.5, "mobil": 6.0, "bus": 14.0, "truk": 12.0}
        
        # 3. Evaluasi Occupancy-Based
        hasil_occupancy = evaluasi(
            jumlah_per_kelas=jumlah_kendaraan,
            kapasitas_meter_lajur=kapasitas_meter_lajur,
            panjang_kendaraan=panjang_kendaraan,
            ambang_lancar=44.0,
            ambang_padat=84.0
        )
        
        # 4. Evaluasi MKJI 1997
        hasil_mkji = evaluasi_mkji(
            jumlah_per_kelas_per_jam=jumlah_per_jam,
            fc_w=0.90,
            fc_sp=1.00,
            fc_sf=1.00,
            fc_cs=1.00,
            ambang_lancar=0.44,
            ambang_padat=0.84
        )

        # 5. Assert (Keduanya harus menghasilkan LANCAR)
        assert hasil_occupancy.status_label == "lancar"
        assert hasil_mkji.status_label == "lancar"
        
        # Menunjukkan bahwa angka rasio berbeda karena metodologi berbeda
        print(f"\n[Occupancy] Rasio Kepadatan: {hasil_occupancy.rasio_vc:.4f}")
        print(f"[MKJI] Rasio V/C: {hasil_mkji.rasio_vc:.4f}")
        assert hasil_occupancy.rasio_vc != hasil_mkji.rasio_vc

    def test_perbandingan_hasil_macet(self):
        # 1. Dataset sintetis: Kondisi padat merayap
        jumlah_kendaraan = {
            "motor": 8000,
            "mobil": 5000,
            "bus": 50,
            "truk": 100
        }
        
        jumlah_per_jam = {k: v * 4 for k, v in jumlah_kendaraan.items()}

        kapasitas_meter_lajur = 56100.0
        panjang_kendaraan = {"motor": 2.5, "mobil": 6.0, "bus": 14.0, "truk": 12.0}
        
        hasil_occupancy = evaluasi(
            jumlah_per_kelas=jumlah_kendaraan,
            kapasitas_meter_lajur=kapasitas_meter_lajur,
            panjang_kendaraan=panjang_kendaraan,
            ambang_lancar=44.0,
            ambang_padat=84.0
        )
        
        hasil_mkji = evaluasi_mkji(
            jumlah_per_kelas_per_jam=jumlah_per_jam,
            fc_w=0.90,
            fc_sp=1.00,
            fc_sf=1.00,
            fc_cs=1.00,
            ambang_lancar=0.44,
            ambang_padat=0.84
        )

        # Keduanya dipastikan akan mengembalikan status macet karena volume meledak
        assert hasil_occupancy.status_label == "macet"
        assert hasil_mkji.status_label == "macet"

    def test_perbedaan_sensitivitas_metodologi(self):
        """
        Skenario dimana satu metodologi bisa padat tapi yang lain lancar/macet.
        Ini membuktikan bahwa kedua metrik mengukur hal yang berbeda
        (kepadatan ruang fisik vs laju arus kendaraan).
        """
        # Skenario: jumlah motor sangat tinggi, mobil sedikit
        jumlah_kendaraan = {
            "motor": 1000, # Butuh sedikit space (2.5m) tapi EMP (0.4) lumayan besar kalau dikali banyak
            "mobil": 10,
            "bus": 0,
            "truk": 0
        }
        
        jumlah_per_jam = {k: v * 4 for k, v in jumlah_kendaraan.items()}
        
        kapasitas_meter_lajur = 56100.0
        panjang_kendaraan = {"motor": 2.5, "mobil": 6.0, "bus": 14.0, "truk": 12.0}

        hasil_occupancy = evaluasi(
            jumlah_per_kelas=jumlah_kendaraan,
            kapasitas_meter_lajur=kapasitas_meter_lajur,
            panjang_kendaraan=panjang_kendaraan,
            ambang_lancar=44.0,
            ambang_padat=84.0
        )
        
        hasil_mkji = evaluasi_mkji(
            jumlah_per_kelas_per_jam=jumlah_per_jam,
            fc_w=0.90,
            fc_sp=1.00,
            fc_sf=1.00,
            fc_cs=1.00,
            ambang_lancar=0.44,
            ambang_padat=0.84
        )

        # Occupancy mungkin melihat ini masih wajar (2500 m / 56100 m = ~4.4%) -> Lancar
        # MKJI melihat arus/jam (1000 * 4 = 4000 motor/jam) -> EMP motor 0.4 -> 1600 smp/jam.
        # MKJI kapasitas: 2900 * 0.9 = 2610.
        # 1600 / 2610 = 0.61 -> Padat (LOS C)
        assert hasil_occupancy.status_label == "lancar"
        assert hasil_mkji.status_label == "padat"
