"""
sistem_pakar.py
================
Implementasi sistem pakar rule-based (IF-THEN) sesuai Blueprint 5
di dokumen final. Modul ini SENGAJA dipisah dari kode server/database
supaya bisa diuji secara independen (lihat tests/test_sistem_pakar.py)
dan gampang dikalibrasi ulang setelah ada data survei MKJI riil.

Changelog v2 (Blueprint Perbaikan):
- Tambah hitung_kapasitas_volumetrik_ruas(): menghitung KVR dari parameter
  dasar ruas (panjang, komposisi segmen) — tidak lagi hardcode angka 56100.
- Tambah klasifikasi_status_hybrid(): versi hybrid yang mempertimbangkan
  kecepatan rata-rata sebagai variabel kedua, sesuai data lapangan bahwa
  kemacetan Sitinjau Lauik bersifat event-driven (bottleneck kecepatan),
  bukan semata kepadatan volumetrik.
- Semua fungsi lama TIDAK DIUBAH — backward compatible dengan test existing.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class HasilKlasifikasi:
    volume_smp: float
    rasio_vc: float
    level_of_service: str
    status_label: str
    teks_rekomendasi: str


# ---------------------------------------------------------------------------
# Fungsi baru Tahap 1: Kapasitas Volumetrik Ruas (KVR)
# ---------------------------------------------------------------------------

def hitung_kapasitas_volumetrik_ruas(
    panjang_meter: float,
    pct_segmen_sempit: float,
    pct_segmen_lebar: float,
    kapasitas_lateral_sempit: float = 2.0,
    kapasitas_lateral_lebar: float = 6.0,
) -> float:
    """
    Menghitung Kapasitas Volumetrik Ruas (KVR) dalam satuan yang sama
    dengan output hitung_volume_meter_lajur() (jumlah × panjang-efektif).

    Formula berdasarkan kajian dosen:
        KVR = (panjang × pct_sempit × kapasitas_lateral_sempit)
            + (panjang × pct_lebar  × kapasitas_lateral_lebar)

    Contoh (data Sitinjau Lauik dari dosen):
        panjang_meter         = 16500
        pct_segmen_sempit     = 0.65  (65% jalan hanya muat 2 kendaraan)
        pct_segmen_lebar      = 0.35  (35% jalan muat 6 kendaraan)
        kapasitas_lateral_sempit = 2
        kapasitas_lateral_lebar  = 6
        → KVR = (16500 × 0.65 × 2) + (16500 × 0.35 × 6)
               = 21450 + 34650 = 56100

    Catatan istilah: satuan "meter-lajur" adalah representasi kapasitas
    volumetrik statis (pendekatan sederhana, bukan istilah baku MKJI/lane-km).
    Konsisten dipakai di seluruh modul — tidak perlu diubah, cukup
    didokumentasikan di README agar tidak disalahpahami saat presentasi.
    """
    total_pct = pct_segmen_sempit + pct_segmen_lebar
    if abs(total_pct - 1.0) > 1e-6:
        raise ValueError(
            f"pct_segmen_sempit + pct_segmen_lebar harus = 1.0, saat ini = {total_pct:.6f}. "
            "Periksa config.yaml bagian ruas_jalan."
        )
    if panjang_meter <= 0:
        raise ValueError(
            f"panjang_meter harus > 0, saat ini = {panjang_meter}. "
            "Periksa config.yaml bagian ruas_jalan.panjang_meter."
        )
    return (
        panjang_meter * pct_segmen_sempit * kapasitas_lateral_sempit
        + panjang_meter * pct_segmen_lebar * kapasitas_lateral_lebar
    )


# ---------------------------------------------------------------------------
# Fungsi-fungsi inti (TIDAK DIUBAH — backward compatible)
# ---------------------------------------------------------------------------

def hitung_volume_meter_lajur(jumlah_per_kelas: Dict[str, int], panjang_kendaraan: Dict[str, float]) -> float:
    """
    Mengonversi jumlah kendaraan mentah per kelas menjadi volume
    dalam satuan meter-lajur berdasarkan panjang kendaraan.

    Contoh:
        jumlah_per_kelas = {"motor": 50, "mobil": 20, "bus": 2, "truk": 5}
        panjang_kendaraan = {"motor": 2.5, "mobil": 6.0, "bus": 14.0, "truk": 12.0}
        -> volume_meter_lajur = 50*2.5 + 20*6.0 + 2*14.0 + 5*12.0
    """
    total = 0.0
    for kelas, jumlah in jumlah_per_kelas.items():
        koefisien = panjang_kendaraan.get(kelas, 0.0)
        total += jumlah * koefisien
    return total


def tentukan_level_of_service(persentase_kepadatan: float) -> str:
    """
    Menentukan Level of Service (LOS) A-F berdasarkan persentase kepadatan.
    Nilai diselaraskan dengan standar resmi MKJI 1997.
    """
    if persentase_kepadatan <= 20.0:
        return "A"
    elif persentase_kepadatan <= 44.0:
        return "B"
    elif persentase_kepadatan <= 75.0:
        return "C"
    elif persentase_kepadatan <= 84.0:
        return "D"
    elif persentase_kepadatan <= 100.0:
        return "E"
    else:
        return "F"


def klasifikasi_status(
    persentase_kepadatan: float,
    ambang_lancar: float = 44.0,
    ambang_padat: float = 84.0,
) -> str:
    """Menentukan status lancar/padat/macet berdasarkan persentase kepadatan meter-lajur."""
    if persentase_kepadatan <= ambang_lancar:
        return "lancar"
    elif persentase_kepadatan <= ambang_padat:
        return "padat"
    else:
        return "macet"


def klasifikasi_status_hybrid(
    persentase_kepadatan: float,
    kecepatan_rata2_kmh: Optional[float] = None,
    ambang_lancar: float = 44.0,
    ambang_padat: float = 84.0,
    ambang_kecepatan_lambat_kmh: float = 15.0,
) -> str:
    """
    Versi hybrid dari klasifikasi_status() yang mempertimbangkan kecepatan
    rata-rata kendaraan sebagai variabel kedua.

    Jika kecepatan_rata2_kmh tidak tersedia (belum ada tracking kecepatan
    di kamera), fallback ke klasifikasi_status() murni berbasis volume.

    Rasional (dari data lapangan Sitinjau Lauik):
    - Kemacetan riil di Sitinjau Lauik bersifat event-driven: bottleneck di
      tikungan sempit (radius ~15-16m) atau kendaraan mogok/kelebihan muatan.
    - Ini tercermin dari PENURUNAN KECEPATAN, bukan semata volume tinggi.
    - Jalan bisa padat kendaraan (volume tinggi) tapi tetap lancar mengalir.
    - Sebaliknya: sedikit kendaraan tapi macet total akibat 1 truk mogok
      (volume rendah, kecepatan nyaris nol → harus override ke "macet").

    Kalkulasi kecepatan dari kamera: diimplementasikan di counting_line.py
    (estimasi kecepatan dari bounding box antar-frame) — belum aktif di
    prototipe 1 kamera ini, tapi fungsi ini sudah siap menerimanya.

    Args:
        persentase_kepadatan: output dari (volume_meter_lajur/kapasitas) × 100
        kecepatan_rata2_kmh: kecepatan rata-rata terukur dari kamera (opsional)
        ambang_lancar: threshold % untuk status lancar (default 50%)
        ambang_padat: threshold % untuk status padat (default 75%)
        ambang_kecepatan_lambat_kmh: kecepatan di bawah ini = override ke macet
                                     (default 15 km/jam — setara antrean berat)
    """
    status_volume = klasifikasi_status(persentase_kepadatan, ambang_lancar, ambang_padat)

    if kecepatan_rata2_kmh is None or kecepatan_rata2_kmh <= 0.0:
        return status_volume  # fallback: belum ada data kecepatan valid

    if kecepatan_rata2_kmh < ambang_kecepatan_lambat_kmh:
        # Kecepatan sangat rendah = indikasi macet TERLEPAS dari volume
        return "macet"

    return status_volume


def buat_rekomendasi(
    status: str, laju_masuk: float = None, laju_keluar: float = None
) -> str:
    """
    Membuat teks rekomendasi sesuai flowchart Blueprint 5.
    laju_masuk dan laju_keluar bersifat opsional - jika tidak diberikan
    (mis. untuk prototipe awal yang belum melacak tren), hanya status
    dasar yang dikembalikan tanpa prediksi eskalasi.
    """
    if status == "lancar":
        return "Lalu lintas lancar."
    elif status == "macet":
        return "Kemacetan terdeteksi. Disarankan mencari jalur alternatif."
    else:  # padat
        if laju_masuk is not None and laju_keluar is not None and laju_masuk > laju_keluar:
            return "Kepadatan meningkat, diperkirakan macet dalam beberapa menit. Disarankan cari jalur alternatif."
        return "Kepadatan sedang, lalu lintas masih tersendat-sendat."


def evaluasi(
    jumlah_per_kelas: Dict[str, int],
    kapasitas_meter_lajur: float,
    panjang_kendaraan: Dict[str, float],
    ambang_lancar: float = 44.0,
    ambang_padat: float = 84.0,
    laju_masuk: float = None,
    laju_keluar: float = None,
    kecepatan_rata2_kmh: Optional[float] = None,
    ambang_kecepatan_lambat_kmh: float = 15.0,
) -> HasilKlasifikasi:
    """
    Fungsi utama yang dipanggil dari luar modul ini.
    Menggabungkan semua langkah: hitung meter-lajur -> persentase kepadatan -> LOS -> status -> rekomendasi.

    Jika kecepatan_rata2_kmh diberikan, status diklasifikasikan menggunakan
    klasifikasi_status_hybrid() yang mempertimbangkan kecepatan sebagai
    variabel kedua (lebih akurat untuk kondisi Sitinjau Lauik).
    """
    volume_meter_lajur = hitung_volume_meter_lajur(jumlah_per_kelas, panjang_kendaraan)

    if kapasitas_meter_lajur <= 0:
        raise ValueError(
            "kapasitas_meter_lajur harus lebih besar dari 0. "
            "Periksa nilai di config.yaml bagian sistem_pakar.kapasitas_meter_lajur"
        )

    persentase_kepadatan = (volume_meter_lajur / kapasitas_meter_lajur) * 100.0
    los = tentukan_level_of_service(persentase_kepadatan)

    # Gunakan hybrid jika ada data kecepatan, fallback ke volume-only
    status = klasifikasi_status_hybrid(
        persentase_kepadatan,
        kecepatan_rata2_kmh=kecepatan_rata2_kmh,
        ambang_lancar=ambang_lancar,
        ambang_padat=ambang_padat,
        ambang_kecepatan_lambat_kmh=ambang_kecepatan_lambat_kmh,
    )

    rekomendasi = buat_rekomendasi(status, laju_masuk, laju_keluar)

    # Catatan: kita mem-passing volume_meter_lajur ke properti volume_smp
    # dan (persentase_kepadatan / 100) ke properti rasio_vc
    # agar tidak merusak struktur database saat ini.
    return HasilKlasifikasi(
        volume_smp=round(volume_meter_lajur, 2),
        rasio_vc=round(persentase_kepadatan / 100.0, 4),
        level_of_service=los,
        status_label=status,
        teks_rekomendasi=rekomendasi,
    )
