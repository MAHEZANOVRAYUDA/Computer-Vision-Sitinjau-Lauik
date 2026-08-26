"""
test_sistem_pakar.py
=====================
Unit tests untuk modul sistem_pakar.py dan occupancy_estimator.py.

Menjalankan:
    python -m pytest tests/test_sistem_pakar.py -v

Test ini dirancang bisa berjalan TANPA database, tanpa koneksi MQTT,
tanpa GPU/YOLO — murni test fungsi-fungsi Python saja.

Coverage:
  1. hitung_kapasitas_volumetrik_ruas() — validasi formula dari data dosen
  2. hitung_volume_meter_lajur() — konversi kendaraan → meter-lajur
  3. tentukan_level_of_service() — klasifikasi A-F
  4. klasifikasi_status() — lancar/padat/macet
  5. klasifikasi_status_hybrid() — override kecepatan rendah → macet
  6. evaluasi() — fungsi utama end-to-end
  7. occupancy_estimator: flow × waktu tempuh
  8. occupancy_estimator: flow in minus out
  9. hitung_flow_per_menit() — konversi counter interval ke flow rate
 10. Edge cases & error cases
"""

import pytest

from src.sistem_pakar import (
    hitung_kapasitas_volumetrik_ruas,
    hitung_volume_meter_lajur,
    tentukan_level_of_service,
    klasifikasi_status,
    klasifikasi_status_hybrid,
    buat_rekomendasi,
    evaluasi,
    HasilKlasifikasi,
)
from src.occupancy_estimator import (
    estimasi_occupancy_flow_x_traveltime,
    hitung_occupancy_ruas,
    hitung_flow_per_menit,
    KECEPATAN_DASAR_KMH,
    FAKTOR_KECEPATAN_PER_KELAS,
)


# =========================================================================
# 1. hitung_kapasitas_volumetrik_ruas — sesuai data dosen
# =========================================================================

class TestHitungKapasitasVolumetrikRuas:
    """
    KVR = (panjang × pct_sempit × kapasitas_sempit) + (panjang × pct_lebar × kapasitas_lebar)
        = (16500 × 0.65 × 2) + (16500 × 0.35 × 6)
        = 21450 + 34650 = 56100
    """

    def test_data_dosen_menghasilkan_56100(self):
        """Test utama: formula dengan data dosen harus menghasilkan tepat 56100."""
        hasil = hitung_kapasitas_volumetrik_ruas(
            panjang_meter=16500,
            pct_segmen_sempit=0.65,
            pct_segmen_lebar=0.35,
        )
        assert hasil == 56100.0, f"KVR harus 56100, dapat {hasil}"

    def test_proporsi_harus_sama_dengan_1(self):
        """pct_sempit + pct_lebar ≠ 1.0 harus raise ValueError."""
        with pytest.raises(ValueError, match="harus = 1.0"):
            hitung_kapasitas_volumetrik_ruas(
                panjang_meter=16500,
                pct_segmen_sempit=0.60,  # 0.60 + 0.35 = 0.95 ≠ 1.0
                pct_segmen_lebar=0.35,
            )

    def test_panjang_nol_raise_error(self):
        """panjang_meter = 0 harus raise ValueError."""
        with pytest.raises(ValueError, match="panjang_meter harus > 0"):
            hitung_kapasitas_volumetrik_ruas(
                panjang_meter=0,
                pct_segmen_sempit=0.65,
                pct_segmen_lebar=0.35,
            )

    def test_panjang_negatif_raise_error(self):
        """panjang_meter negatif harus raise ValueError."""
        with pytest.raises(ValueError):
            hitung_kapasitas_volumetrik_ruas(
                panjang_meter=-100,
                pct_segmen_sempit=0.65,
                pct_segmen_lebar=0.35,
            )

    def test_custom_kapasitas_lateral(self):
        """Test dengan kapasitas lateral custom."""
        hasil = hitung_kapasitas_volumetrik_ruas(
            panjang_meter=10000,
            pct_segmen_sempit=0.5,
            pct_segmen_lebar=0.5,
            kapasitas_lateral_sempit=2.0,
            kapasitas_lateral_lebar=4.0,
        )
        # (10000 × 0.5 × 2) + (10000 × 0.5 × 4) = 10000 + 20000 = 30000
        assert hasil == 30000.0

    def test_toleransi_floating_point(self):
        """Penjumlahan floating point 0.1+0.9=1.0 tidak selalu persis — harus toleran."""
        hasil = hitung_kapasitas_volumetrik_ruas(
            panjang_meter=16500,
            pct_segmen_sempit=0.1 + 0.9 * 0.7222222,  # floating point trick
            pct_segmen_lebar=0.9 * 0.2777778,
        )
        # Tidak crash = PASS (ini test toleransi, bukan nilai spesifik)
        assert hasil > 0


# =========================================================================
# 2. hitung_volume_meter_lajur
# =========================================================================

class TestHitungVolumeMeterLajur:
    PANJANG_DEFAULT = {"motor": 2.5, "mobil": 6.0, "bus": 14.0, "truk": 12.0}

    def test_semua_kelas_nol(self):
        hasil = hitung_volume_meter_lajur(
            {"motor": 0, "mobil": 0, "bus": 0, "truk": 0},
            self.PANJANG_DEFAULT,
        )
        assert hasil == 0.0

    def test_hanya_mobil(self):
        """10 mobil × 6.0 m = 60.0 meter-lajur."""
        hasil = hitung_volume_meter_lajur({"mobil": 10}, self.PANJANG_DEFAULT)
        assert hasil == 60.0

    def test_campuran_kendaraan(self):
        """50 motor + 20 mobil + 2 bus + 5 truk."""
        hasil = hitung_volume_meter_lajur(
            {"motor": 50, "mobil": 20, "bus": 2, "truk": 5},
            self.PANJANG_DEFAULT,
        )
        # 50×2.5 + 20×6 + 2×14 + 5×12 = 125 + 120 + 28 + 60 = 333
        assert hasil == 333.0

    def test_kelas_tidak_dikenal_diabaikan(self):
        """Kelas kendaraan tidak dikenal → koefisien 0 → tidak menambah volume."""
        hasil = hitung_volume_meter_lajur({"angkot": 100}, self.PANJANG_DEFAULT)
        assert hasil == 0.0


# =========================================================================
# 3. tentukan_level_of_service
# =========================================================================

class TestTentukanLevelOfService:
    def test_los_a(self):
        assert tentukan_level_of_service(0) == "A"
        assert tentukan_level_of_service(20) == "A"

    def test_los_b(self):
        assert tentukan_level_of_service(20.01) == "B"
        assert tentukan_level_of_service(44) == "B"

    def test_los_c(self):
        assert tentukan_level_of_service(44.01) == "C"
        assert tentukan_level_of_service(75) == "C"

    def test_los_d(self):
        assert tentukan_level_of_service(75.01) == "D"
        assert tentukan_level_of_service(84) == "D"

    def test_los_e(self):
        assert tentukan_level_of_service(84.01) == "E"
        assert tentukan_level_of_service(100) == "E"

    def test_los_f(self):
        assert tentukan_level_of_service(100.01) == "F"
        assert tentukan_level_of_service(110) == "F"


# =========================================================================
# 4. klasifikasi_status
# =========================================================================

class TestKlasifikasiStatus:
    def test_lancar(self):
        assert klasifikasi_status(0) == "lancar"
        assert klasifikasi_status(44) == "lancar"

    def test_padat(self):
        assert klasifikasi_status(44.01) == "padat"
        assert klasifikasi_status(84) == "padat"

    def test_macet(self):
        assert klasifikasi_status(84.01) == "macet"
        assert klasifikasi_status(100) == "macet"

    def test_custom_ambang(self):
        assert klasifikasi_status(60, ambang_lancar=70, ambang_padat=90) == "lancar"
        assert klasifikasi_status(80, ambang_lancar=70, ambang_padat=90) == "padat"
        assert klasifikasi_status(95, ambang_lancar=70, ambang_padat=90) == "macet"


# =========================================================================
# 5. klasifikasi_status_hybrid
# =========================================================================

class TestKlasifikasiStatusHybrid:
    def test_tanpa_kecepatan_sama_dengan_volume_only(self):
        """Jika kecepatan None, harus identik dengan klasifikasi_status biasa."""
        for pct in [10, 44, 75, 90]:
            assert klasifikasi_status_hybrid(pct, kecepatan_rata2_kmh=None) == \
                   klasifikasi_status(pct)

    def test_kecepatan_lambat_override_ke_macet(self):
        """Kecepatan < 15 km/jam → macet, meski volume rendah (event-driven bottleneck)."""
        # Volume hanya 5% (jauh dari macet), tapi kecepatan 5 km/jam (berhenti total)
        status = klasifikasi_status_hybrid(5.0, kecepatan_rata2_kmh=5.0)
        assert status == "macet", \
            "Kecepatan sangat rendah harus override ke macet terlepas dari volume"

    def test_kecepatan_tepat_di_ambang_tidak_override(self):
        """Kecepatan tepat di ambang (15 km/jam) = tidak override."""
        # Volume 5% = lancar, kecepatan tepat 15 = tidak override
        status = klasifikasi_status_hybrid(5.0, kecepatan_rata2_kmh=15.0)
        assert status == "lancar", \
            "Kecepatan tepat di ambang seharusnya tidak override ke macet"

    def test_kecepatan_normal_tidak_mengubah_status_volume(self):
        """Kecepatan normal (misalnya 40 km/jam) → ikut status volume."""
        assert klasifikasi_status_hybrid(10.0, kecepatan_rata2_kmh=40.0) == "lancar"
        assert klasifikasi_status_hybrid(60.0, kecepatan_rata2_kmh=40.0) == "padat"
        assert klasifikasi_status_hybrid(90.0, kecepatan_rata2_kmh=40.0) == "macet"

    def test_custom_ambang_kecepatan(self):
        """Test dengan ambang kecepatan custom."""
        # Kecepatan 20 km/jam, ambang 30 → harus override ke macet
        status = klasifikasi_status_hybrid(
            5.0, kecepatan_rata2_kmh=20.0, ambang_kecepatan_lambat_kmh=30.0
        )
        assert status == "macet"


# =========================================================================
# 6. evaluasi() — fungsi utama end-to-end
# =========================================================================

class TestEvaluasi:
    PANJANG_KDR = {"motor": 2.5, "mobil": 6.0, "bus": 14.0, "truk": 12.0}
    KAPASITAS = 56100.0

    def test_kapasitas_benar_74mobil_25bus_5truk_harus_lancar(self):
        """
        Skenario dari blueprint: 74 mobil + 25 bus + 5 truk.
        Volume = 74×6 + 25×14 + 5×12 = 444 + 350 + 60 = 854
        Rasio = 854 / 56100 = 0.01522 = 1.52% → JAUH di bawah ambang LANCAR (50%)
        Sebelum fix kapasitas, angka ini mungkin tampil sebagai "macet"
        karena kapasitas yang dipakai jauh lebih kecil dari 56100.
        """
        hasil = evaluasi(
            jumlah_per_kelas={"motor": 0, "mobil": 74, "bus": 25, "truk": 5},
            kapasitas_meter_lajur=self.KAPASITAS,
            panjang_kendaraan=self.PANJANG_KDR,
        )
        assert hasil.status_label == "lancar", \
            f"Dengan kapasitas benar (56100), 74 mobil+25 bus+5 truk harus LANCAR, dapat: {hasil.status_label}"
        assert hasil.rasio_vc < 0.05, \
            f"rasio_vc harus di bawah 5%, dapat: {hasil.rasio_vc:.4f}"

    def test_jam_puncak_354_kendaraan_lancar(self):
        """
        Skenario jam puncak dari kalkulasi kalibrasi blueprint:
        ~354 kendaraan (rata-rata mobil) = 3.78% kapasitas → LANCAR.
        """
        hasil = evaluasi(
            jumlah_per_kelas={"mobil": 354},
            kapasitas_meter_lajur=self.KAPASITAS,
            panjang_kendaraan=self.PANJANG_KDR,
        )
        assert hasil.status_label == "lancar"
        pct = hasil.rasio_vc * 100
        assert pct < 5.0, f"Jam puncak normal harus < 5% kepadatan, dapat: {pct:.2f}%"

    def test_kapasitas_nol_raise_value_error(self):
        with pytest.raises(ValueError, match="kapasitas_meter_lajur harus lebih besar dari 0"):
            evaluasi({"mobil": 100}, kapasitas_meter_lajur=0, panjang_kendaraan=self.PANJANG_KDR)

    def test_kapasitas_negatif_raise_value_error(self):
        with pytest.raises(ValueError):
            evaluasi({"mobil": 100}, kapasitas_meter_lajur=-1, panjang_kendaraan=self.PANJANG_KDR)

    def test_skenario_sangat_padat(self):
        """Skenario ekstrem: jalan penuh kendaraan."""
        # 9500 mobil (lebih dari kapasitas penuh)
        hasil = evaluasi(
            jumlah_per_kelas={"mobil": 9500},
            kapasitas_meter_lajur=self.KAPASITAS,
            panjang_kendaraan=self.PANJANG_KDR,
        )
        # 9500 × 6 = 57000 / 56100 = 101.60% → MACET
        assert hasil.status_label == "macet"
        assert hasil.level_of_service == "F"

    def test_hasil_dataclass_fields_lengkap(self):
        """Pastikan semua field HasilKlasifikasi terisi."""
        hasil = evaluasi(
            jumlah_per_kelas={"mobil": 100},
            kapasitas_meter_lajur=self.KAPASITAS,
            panjang_kendaraan=self.PANJANG_KDR,
        )
        assert isinstance(hasil, HasilKlasifikasi)
        assert isinstance(hasil.volume_smp, float)
        assert isinstance(hasil.rasio_vc, float)
        assert hasil.level_of_service in {"A", "B", "C", "D", "E", "F"}
        assert hasil.status_label in {"lancar", "padat", "macet"}
        assert isinstance(hasil.teks_rekomendasi, str)
        assert len(hasil.teks_rekomendasi) > 0

    def test_dengan_kecepatan_lambat_override(self):
        """
        Skenario truk mogok di tikungan Panorama: volume rendah tapi
        kecepatan nyaris nol → harus override ke MACET.
        """
        hasil = evaluasi(
            jumlah_per_kelas={"mobil": 50},   # volume sangat rendah
            kapasitas_meter_lajur=self.KAPASITAS,
            panjang_kendaraan=self.PANJANG_KDR,
            kecepatan_rata2_kmh=3.0,  # hampir berhenti total
        )
        assert hasil.status_label == "macet", \
            "Kecepatan 3 km/jam harus override status ke MACET"


# =========================================================================
# 7. occupancy_estimator: flow × waktu tempuh
# =========================================================================

class TestEstimasiOccupancyFlowXTraveltime:
    PANJANG_KM = 16.5

    def test_jam_puncak_menghasilkan_sekitar_354_mobil(self):
        """
        Dari kalkulasi blueprint:
        Flow = 15 mobil/menit, waktu tempuh = 16.5/42 × 60 = 23.57 menit
        Occupancy ≈ 15 × 23.57 = ~354 kendaraan
        """
        flow = {"mobil": 15.0}  # 15 mobil per menit (900/jam — jam puncak)
        hasil = estimasi_occupancy_flow_x_traveltime(flow, self.PANJANG_KM)

        assert hasil.metode == "flow_x_traveltime"
        assert hasil.jumlah_per_kelas["mobil"] > 300
        assert hasil.jumlah_per_kelas["mobil"] < 400
        assert hasil.total == hasil.jumlah_per_kelas["mobil"]

    def test_truk_lebih_lambat_occupancy_lebih_tinggi(self):
        """
        Truk lebih lambat (faktor 0.75) → waktu tempuh lebih lama
        → occupancy estimasi lebih tinggi untuk flow yang sama.
        """
        flow_sama = 5.0  # 5 kendaraan per menit
        hasil_mobil = estimasi_occupancy_flow_x_traveltime(
            {"mobil": flow_sama}, self.PANJANG_KM
        )
        hasil_truk = estimasi_occupancy_flow_x_traveltime(
            {"truk": flow_sama}, self.PANJANG_KM
        )
        assert hasil_truk.jumlah_per_kelas.get("truk", 0) > hasil_mobil.jumlah_per_kelas.get("mobil", 0), \
            "Truk lebih lambat → occupancy truk harus lebih tinggi dari mobil untuk flow yang sama"

    def test_flow_nol_menghasilkan_occupancy_nol(self):
        hasil = estimasi_occupancy_flow_x_traveltime({"mobil": 0.0}, self.PANJANG_KM)
        assert hasil.jumlah_per_kelas.get("mobil", 0) == 0
        assert hasil.total == 0

    def test_confidence_note_berisi_info_1_kamera(self):
        hasil = estimasi_occupancy_flow_x_traveltime({"mobil": 10.0}, self.PANJANG_KM)
        assert "Gerbang A" in hasil.confidence_note
        assert "1 kamera" in hasil.confidence_note

    def test_semua_kelas_kendaraan(self):
        """Test dengan semua 4 kelas kendaraan sekaligus."""
        flow = {"motor": 20.0, "mobil": 10.0, "bus": 2.0, "truk": 1.0}
        hasil = estimasi_occupancy_flow_x_traveltime(flow, self.PANJANG_KM)
        assert set(hasil.jumlah_per_kelas.keys()) == {"motor", "mobil", "bus", "truk"}
        assert hasil.total == sum(hasil.jumlah_per_kelas.values())


# =========================================================================
# 8. occupancy_estimator: flow in minus out
# =========================================================================

class TestEstimasiOccupancyFlowInMinusOut:
    def test_masuk_lebih_banyak_dari_keluar(self):
        """masuk 100 mobil, keluar 30 mobil: occupancy = 100 - 30 = 70 mobil."""
        hasil = hitung_occupancy_ruas(
            {"mobil": 100, "motor": 50},  # Gerbang A masuk
            {"mobil": 30, "motor": 10},   # Gerbang B keluar (arah A ke B)
            {},                            # Gerbang B masuk (arah B ke A, kosong)
            {}                             # Gerbang A keluar (arah B ke A, kosong)
        )
        assert hasil.metode == "selisih_kumulatif_dual_gerbang"
        assert hasil.jumlah_per_kelas["mobil"] == 70   # 100 - 30
        assert hasil.jumlah_per_kelas["motor"] == 40   # 50 - 10
        total_expected = 70 + 40
        assert hasil.total_per_kelas["mobil"] + hasil.total_per_kelas["motor"] == total_expected

    def test_keluar_lebih_banyak_di_clamp_ke_nol(self):
        """Jika keluar > masuk (anomali data), hasil harus clamp ke 0."""
        hasil = hitung_occupancy_ruas(
            {"mobil": 10},   # Gerbang A masuk
            {"mobil": 50},   # Gerbang B keluar > masuk → anomali → clamp ke 0
            {},
            {}
        )
        assert hasil.total_per_kelas["mobil"] == 0  # clamp ke 0

    def test_kelas_hanya_ada_di_masuk(self):
        """Kelas yang ada di masuk tapi tidak ada di keluar."""
        hasil = hitung_occupancy_ruas(
            {"motor": 100, "truk": 20},  # Gerbang A masuk
            {"motor": 40},               # Gerbang B keluar (truk tidak ada → 0 keluar)
            {},
            {}
        )
        assert hasil.total_per_kelas["motor"] == 60   # 100 - 40
        assert hasil.total_per_kelas["truk"] == 20    # 20 - 0 = 20 (tidak ada truk keluar)

    def test_confidence_note_berisi_multi_kamera(self):
        hasil = hitung_occupancy_ruas({"mobil": 10}, {"mobil": 5}, {}, {})
        assert "multi-kamera" in hasil.confidence_note.lower() or \
               "Gerbang B" in hasil.confidence_note


# =========================================================================
# 9. hitung_flow_per_menit
# =========================================================================

class TestHitungFlowPerMenit:
    def test_konversi_counter_20_detik_ke_per_menit(self):
        """Counter 20 detik: 10 mobil masuk → 10/20×60 = 30 mobil/menit."""
        counter = {"masuk_mobil": 10, "keluar_mobil": 5}
        flow = hitung_flow_per_menit(counter, durasi_interval_detik=20.0)

        assert "mobil" in flow
        assert abs(flow["mobil"] - 30.0) < 0.01
        assert "keluar" not in str(flow)  # keluar tidak masuk ke flow estimasi

    def test_hanya_menghitung_arah_masuk(self):
        """Hanya counter 'masuk' yang dipakai untuk flow estimasi."""
        counter = {"masuk_motor": 12, "keluar_motor": 8, "masuk_mobil": 3}
        flow = hitung_flow_per_menit(counter, durasi_interval_detik=60.0)

        assert "motor" in flow
        assert "mobil" in flow
        # Flow motor = 12/menit (bukan 12-8=4 atau 12+8=20)
        assert abs(flow["motor"] - 12.0) < 0.01
        assert abs(flow["mobil"] - 3.0) < 0.01

    def test_counter_kosong(self):
        flow = hitung_flow_per_menit({}, durasi_interval_detik=20.0)
        assert flow == {}

    def test_key_format_tidak_valid_diabaikan(self):
        """Key dengan format salah diabaikan tanpa crash."""
        counter = {"masuk_motor": 5, "invalid_key_format": 10, "formatbaru": 3}
        flow = hitung_flow_per_menit(counter, durasi_interval_detik=60.0)
        assert "motor" in flow
        # key invalid tidak masuk
        assert len(flow) == 1


# =========================================================================
# 10. Skenario integrasi end-to-end
# =========================================================================

class TestSkenarioEndToEnd:
    """
    Skenario realistic: data dari edge → estimasi occupancy → evaluasi.
    Mensimulasikan alur mqtt_consumer.py tanpa perlu MQTT, DB, atau GPU.
    """

    PANJANG_KDR = {"motor": 2.5, "mobil": 6.0, "bus": 14.0, "truk": 12.0}
    KAPASITAS = 56100.0

    def test_skenario_hari_normal_jam_puncak(self):
        """
        Edge kirim snapshot: 15 mobil masuk per interval 20 detik.
        → flow = 15/(20/60) = 45 mobil/menit
        → occupancy ≈ 45 × 23.57 = ~1060 mobil di ruas
        → volume = 1060 × 6 = 6360 meter-lajur
        → 6360 / 56100 = 11.3% → LANCAR (LOS A-B)

        Catatan: angka ini lebih tinggi dari 354 skenario blueprint karena
        flow per menit lebih tinggi (45 vs 15). Namun tetap LANCAR.
        """
        counter = {"masuk_mobil": 15, "keluar_mobil": 3}
        interval_detik = 20.0

        flow = hitung_flow_per_menit(counter, interval_detik)
        estimasi = estimasi_occupancy_flow_x_traveltime(flow, panjang_ruas_km=16.5)
        hasil = evaluasi(
            jumlah_per_kelas=estimasi.jumlah_per_kelas,
            kapasitas_meter_lajur=self.KAPASITAS,
            panjang_kendaraan=self.PANJANG_KDR,
        )

        assert hasil.status_label in {"lancar", "padat"}, \
            f"Jam puncak normal seharusnya tidak MACET, dapat: {hasil.status_label} ({hasil.rasio_vc*100:.1f}%)"

    def test_skenario_truk_mogok_event_driven(self):
        """
        Skenario bottleneck: 1 truk mogok di Panorama 1.
        Volume kendaraan rendah tapi kecepatan turun drastis.
        Sistem harus mendeteksi MACET melalui variabel kecepatan.
        """
        counter = {"masuk_mobil": 2, "keluar_mobil": 1}  # volume sangat rendah
        interval_detik = 20.0

        flow = hitung_flow_per_menit(counter, interval_detik)
        estimasi = estimasi_occupancy_flow_x_traveltime(flow, panjang_ruas_km=16.5)
        hasil = evaluasi(
            jumlah_per_kelas=estimasi.jumlah_per_kelas,
            kapasitas_meter_lajur=self.KAPASITAS,
            panjang_kendaraan=self.PANJANG_KDR,
            kecepatan_rata2_kmh=3.0,  # hampir berhenti akibat truk mogok
        )

        assert hasil.status_label == "macet", \
            "Kecepatan sangat rendah harus override ke MACET meski volume rendah"
