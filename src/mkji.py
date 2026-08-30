"""
mkji.py
=======
Implementasi perhitungan Level of Service (LOS) sesuai MKJI 1997
(Manual Kapasitas Jalan Indonesia) untuk jalan 2-lajur tak terbagi
(2/2 UD) di medan gunung — sesuai karakteristik ruas Sitinjau Lauik
(gradien 8-12%).

Formula kapasitas:
    C = C0 x FCw x FCsp x FCsf x FCcs

Dimana:
    C0   = kapasitas dasar (smp/jam), dari Tabel 5-2 MKJI 1997
           berdasarkan tipe jalan dan medan
    FCw  = faktor koreksi lebar jalur efektif
    FCsp = faktor koreksi pemisahan arah (untuk jalan tak terbagi)
    FCsf = faktor koreksi hambatan samping
    FCcs = faktor koreksi ukuran kota

Volume dikonversi ke satuan mobil penumpang (smp) memakai EMP
(Ekuivalen Mobil Penumpang) per kelas kendaraan, khusus medan gunung.

Referensi: MKJI 1997, Direktorat Jenderal Bina Marga, Tabel 5-2 dan
5-5. Lihat docs/METODOLOGI_PERHITUNGAN.md untuk detail tabel referensi dan
catatan validasi lapangan yang WAJIB dilakukan sebelum klaim akademis.
Modul ini adalah METRIK PEMBANDING, bukan status operasional utama.
"""

from dataclasses import dataclass
from typing import Dict, Optional


# ---------------------------------------------------------------------
# Nilai EMP (Ekuivalen Mobil Penumpang) — medan GUNUNG (MKJI Tabel 5-5)
# ---------------------------------------------------------------------
# PENTING: nilai bus/truk di sini adalah TITIK TENGAH rentang MKJI untuk
# medan gunung (3.0-3.5 untuk bus, 4.0-6.0 untuk truk besar). WAJIB
# divalidasi/disesuaikan dengan survei lapangan aktual — lihat
# docs/METODOLOGI_PERHITUNGAN.md Bagian B untuk rentang lengkap dan prosedur
# validasi. Jangan mengklaim nilai ini final tanpa survei.
EMP_GUNUNG: Dict[str, float] = {
    "motor": 0.4,
    "mobil": 1.0,
    "bus": 3.25,
    "truk": 5.0,
}

# Kapasitas dasar C0 (smp/jam, TOTAL 2 ARAH) — jalan 2/2 UD, MKJI 1997 Tabel 5-2
# PENTING: Nilai C0 untuk jalan 2/2 UD adalah 2900 smp/jam, tidak tergantung medan.
# Pengaruh medan diakomodasi melalui faktor penyesuaian (FCw, FCsp, FCsf, FCcs).
C0_2_2_UD = 2900.0


@dataclass
class HasilMKJI:
    volume_smp_per_jam: float
    kapasitas_smp_per_jam: float
    rasio_vc: float
    level_of_service: str
    status_label: str


def hitung_volume_smp(
    jumlah_per_kelas_per_jam: Dict[str, float],
    emp: Dict[str, float] = None,
) -> float:
    """
    Konversi volume kendaraan/jam per kelas menjadi smp/jam
    menggunakan EMP.

    Args:
        jumlah_per_kelas_per_jam: kendaraan/jam per kelas, mis.
            {"motor": 450, "mobil": 200, "bus": 10, "truk": 30}
        emp: mapping EMP per kelas (default: EMP_GUNUNG)
    """
    emp = emp or EMP_GUNUNG
    return sum(
        jumlah * emp.get(kelas, 1.0)
        for kelas, jumlah in jumlah_per_kelas_per_jam.items()
    )


def hitung_kapasitas_mkji(
    fc_w: float = 0.90,
    fc_sp: float = 1.00,
    fc_sf: float = 1.00,
    fc_cs: float = 1.00,
) -> float:
    """
    C = C0 x FCw x FCsp x FCsf x FCcs (smp/jam, total 2 arah).

    Menggunakan C0 = 2900 smp/jam untuk jalan 2/2 UD (Tabel 5-2 MKJI).
    Nilai default fc_w=0.90 mengasumsikan lebar jalur efektif
    3.0-3.5m (lihat docs/METODOLOGI_PERHITUNGAN.md). fc_sp=1.00 untuk jalan
    tak terbagi tanpa pemisah median. Sesuaikan berdasar kondisi
    aktual ruas dan hasil survei.
    """
    return C0_2_2_UD * fc_w * fc_sp * fc_sf * fc_cs


def tentukan_los_mkji(rasio_vc: float) -> str:
    """LOS A-F berdasarkan rasio V/C, sesuai standar resmi MKJI 1997."""
    if rasio_vc <= 0.20:
        return "A"
    elif rasio_vc <= 0.44:
        return "B"
    elif rasio_vc <= 0.75:
        return "C"
    elif rasio_vc <= 0.84:
        return "D"
    elif rasio_vc <= 1.00:
        return "E"
    else:
        return "F"


def klasifikasi_status_mkji(rasio_vc: float, ambang_lancar: float = 0.44, ambang_padat: float = 0.84) -> str:
    """
    Status operasional sederhana dari rasio V/C.
    Ambang default sesuai MKJI 1997:
    (0.44 = batas LOS B untuk lancar, 0.84 = batas LOS D untuk padat).
    """
    if rasio_vc <= ambang_lancar:
        return "lancar"
    elif rasio_vc <= ambang_padat:
        return "padat"
    else:
        return "macet"


def evaluasi_mkji(
    jumlah_per_kelas_per_jam: Dict[str, float],
    fc_w: float = 0.90,
    fc_sp: float = 1.00,
    fc_sf: float = 1.00,
    fc_cs: float = 1.00,
    emp: Dict[str, float] = None,
    ambang_lancar: float = 0.44,
    ambang_padat: float = 0.84,
) -> HasilMKJI:
    """Fungsi utama: volume -> smp/jam -> V/C -> LOS -> status, sesuai MKJI 1997."""
    volume_smp = hitung_volume_smp(jumlah_per_kelas_per_jam, emp=emp)
    kapasitas = hitung_kapasitas_mkji(fc_w, fc_sp, fc_sf, fc_cs)

    if kapasitas <= 0:
        raise ValueError("Kapasitas MKJI harus > 0. Periksa parameter fc_w/fc_sp/fc_sf/fc_cs.")

    rasio_vc = volume_smp / kapasitas
    los = tentukan_los_mkji(rasio_vc)
    status = klasifikasi_status_mkji(rasio_vc, ambang_lancar, ambang_padat)

    return HasilMKJI(
        volume_smp_per_jam=round(volume_smp, 2),
        kapasitas_smp_per_jam=round(kapasitas, 2),
        rasio_vc=round(rasio_vc, 4),
        level_of_service=los,
        status_label=status,
    )
