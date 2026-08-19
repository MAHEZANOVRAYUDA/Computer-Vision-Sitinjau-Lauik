"""
occupancy_estimator.py
=======================
Estimasi jumlah kendaraan yang sedang berada di ruas jalan
(occupancy ruas = kendaraan yang sudah masuk tapi belum keluar).

Dirancang 2 mode — dipilih otomatis berdasarkan jumlah kamera aktif:
  - mode "flow_x_traveltime": dipakai saat hanya 1 kamera aktif (prototipe
    saat ini). Estimasi: flow masuk rata-rata × estimasi waktu tempuh.
  - mode "flow_in_minus_out": dipakai saat kamera Gerbang B (atau node
    keluar) sudah aktif. Occupancy riil = akumulasi masuk − akumulasi keluar.

Mengapa butuh modul terpisah ini?
  Sebelum modul ini ada, mqtt_consumer.py meng-pass occupancy_kumulatif
  (akumulasi masuk − keluar di gerbang yang SAMA) langsung ke evaluasi().
  Ini bukan occupancy ruas sesungguhnya karena:
  1. Kendaraan yang "keluar" di gerbang A (balik arah) bukan berarti
     sudah melewati seluruh ruas 16.5 km.
  2. Angka ini terus naik sepanjang hari → tidak pernah reset → evaluasi()
     akan selalu menunjukkan "macet" setelah beberapa jam meski kondisi
     aktual lancar.

Solusi modul ini: gunakan flow masuk × waktu tempuh estimasi sebagai
proxy occupancy hingga Gerbang B aktif.

Referensi data lapangan (Studi Universitas Andalas):
  - Kecepatan rata-rata: 37.7–45.4 km/jam (rata-rata ~42 km/jam)
  - Headway rata-rata: 1.72–1.93 detik
  - Panjang ruas: 16.5 km → waktu tempuh estimasi ~23.6 menit
"""

from dataclasses import dataclass
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Konstanta kalibrasi — dari studi lapangan Universitas Andalas
# ---------------------------------------------------------------------------

# Kecepatan dasar rata-rata kendaraan (km/jam), dari rata-rata studi Unand
KECEPATAN_DASAR_KMH = 42.0

# Faktor koreksi kecepatan per kelas kendaraan (relatif terhadap kecepatan dasar).
# Truk/bus lebih lambat karena tanjakan panjang di Sitinjau Lauik.
# Motor lebih bebas manuver → cenderung lebih cepat dari rata-rata.
FAKTOR_KECEPATAN_PER_KELAS: Dict[str, float] = {
    "motor": 1.05,   # ~44.1 km/jam
    "mobil": 1.00,   # ~42.0 km/jam
    "bus":   0.85,   # ~35.7 km/jam
    "truk":  0.75,   # ~31.5 km/jam
}


# ---------------------------------------------------------------------------
# Dataclass hasil estimasi
# ---------------------------------------------------------------------------

@dataclass
class EstimasiOccupancy:
    """
    Hasil estimasi occupancy ruas jalan.

    Attributes:
        jumlah_per_kelas: dict {kelas_kendaraan: jumlah_estimasi}
                          yang aman di-pass langsung ke evaluasi()
        total: total semua kelas
        metode: "flow_x_traveltime" atau "flow_in_minus_out"
        confidence_note: teks transparansi metodologi untuk ditampilkan
                         di dashboard (sesuai rekomendasi blueprint)
    """
    jumlah_per_kelas: Dict[str, int]
    total: int
    metode: str
    confidence_note: str


# ---------------------------------------------------------------------------
# Mode 1: flow × waktu tempuh (1 kamera aktif — prototipe saat ini)
# ---------------------------------------------------------------------------

def estimasi_occupancy_flow_x_traveltime(
    flow_masuk_per_menit: Dict[str, float],
    panjang_ruas_km: float,
    kecepatan_dasar_kmh: float = KECEPATAN_DASAR_KMH,
) -> EstimasiOccupancy:
    """
    Estimasi occupancy dari flow masuk (1 kamera) × estimasi waktu tempuh.

    Formula:
        Occupancy_kelas ≈ flow_masuk_per_menit[kelas] × waktu_tempuh_menit[kelas]

    Waktu tempuh dibedakan per kelas karena truk/bus jauh lebih lambat
    di tanjakan panjang Sitinjau Lauik:
        waktu_tempuh_menit[kelas] = (panjang_ruas / (kecepatan_dasar × faktor)) × 60

    Args:
        flow_masuk_per_menit: rata-rata kendaraan/menit per kelas
                              yang melewati garis hitung di Gerbang A
        panjang_ruas_km: panjang ruas jalan yang dipantau (km)
        kecepatan_dasar_kmh: kecepatan referensi (default dari studi Unand)

    Returns:
        EstimasiOccupancy dengan metode="flow_x_traveltime"

    Contoh (jam puncak, semua mobil):
        flow = {"mobil": 15/min} (900 kend/jam)
        panjang = 16.5 km
        waktu_tempuh = 16.5/42 × 60 = 23.57 menit
        occupancy ≈ 15 × 23.57 = ~354 kendaraan → 3.78% kapasitas → LANCAR
    """
    hasil: Dict[str, int] = {}
    for kelas, flow_per_menit in flow_masuk_per_menit.items():
        faktor = FAKTOR_KECEPATAN_PER_KELAS.get(kelas, 1.0)
        kecepatan_efektif = kecepatan_dasar_kmh * faktor
        if kecepatan_efektif <= 0:
            continue
        waktu_tempuh_menit = (panjang_ruas_km / kecepatan_efektif) * 60.0
        hasil[kelas] = max(0, round(flow_per_menit * waktu_tempuh_menit))

    total = sum(hasil.values())
    return EstimasiOccupancy(
        jumlah_per_kelas=hasil,
        total=total,
        metode="flow_x_traveltime",
        confidence_note=(
            "Estimasi berbasis 1 kamera (Gerbang A) — occupancy dihitung dari "
            f"flow masuk × estimasi waktu tempuh (~{panjang_ruas_km/kecepatan_dasar_kmh*60:.0f} menit). "
            "Akurasi meningkat setelah kamera Gerbang B aktif."
        ),
    )


@dataclass
class OccupancyRuas:
    arah_a_ke_b: Dict[str, int]   # occupancy kendaraan yang sedang menuju Solok
    arah_b_ke_a: Dict[str, int]   # occupancy kendaraan yang sedang menuju Padang
    total_per_kelas: Dict[str, int]
    metode: str = "selisih_kumulatif_dual_gerbang"


def hitung_occupancy_ruas(
    kumulatif_gerbang_a_masuk: Dict[str, int],   # kendaraan masuk ruas dari Gerbang A (menuju Solok)
    kumulatif_gerbang_b_keluar: Dict[str, int],  # kendaraan yang sudah keluar ruas di Gerbang B (arah sama)
    kumulatif_gerbang_b_masuk: Dict[str, int],   # kendaraan masuk ruas dari Gerbang B (menuju Padang)
    kumulatif_gerbang_a_keluar: Dict[str, int],  # kendaraan yang sudah keluar ruas di Gerbang A (arah sama)
) -> OccupancyRuas:
    """
    Occupancy riil dihitung sebagai selisih kumulatif kendaraan yang MASUK
    ruas di satu gerbang dan yang sudah KELUAR ruas di gerbang seberang,
    untuk arah perjalanan yang sama.

    Ini menggantikan pendekatan estimasi 'flow x waktu tempuh' pada
    prototipe 1-kamera sebelumnya - sekarang dihitung langsung dari data
    aktual dua titik pengukuran, bukan estimasi.
    """
    arah_a_ke_b = {}
    arah_b_ke_a = {}
    semua_kelas = set(kumulatif_gerbang_a_masuk) | set(kumulatif_gerbang_b_masuk)

    for kelas in semua_kelas:
        masuk_a = kumulatif_gerbang_a_masuk.get(kelas, 0)
        keluar_b = kumulatif_gerbang_b_keluar.get(kelas, 0)
        arah_a_ke_b[kelas] = max(0, masuk_a - keluar_b)

        masuk_b = kumulatif_gerbang_b_masuk.get(kelas, 0)
        keluar_a = kumulatif_gerbang_a_keluar.get(kelas, 0)
        arah_b_ke_a[kelas] = max(0, masuk_b - keluar_a)

    total = {
        kelas: arah_a_ke_b.get(kelas, 0) + arah_b_ke_a.get(kelas, 0)
        for kelas in semua_kelas
    }

    return OccupancyRuas(
        arah_a_ke_b=arah_a_ke_b,
        arah_b_ke_a=arah_b_ke_a,
        total_per_kelas=total,
    )


# ---------------------------------------------------------------------------
# Helper: hitung flow per menit dari counter interval
# ---------------------------------------------------------------------------

def hitung_flow_per_menit(
    counter_interval: Dict[str, int],
    durasi_interval_detik: float,
) -> Dict[str, float]:
    """
    Mengonversi counter mentah satu interval (mis. 20 detik)
    menjadi flow per menit per kelas kendaraan.

    counter_interval format: {"masuk_motor": 5, "masuk_mobil": 3, ...}

    Hanya menghitung kendaraan arah MASUK (bukan keluar),
    karena ini yang dipakai untuk estimasi occupancy ruas.

    Args:
        counter_interval: snapshot counter dari EventPublisher/detector
        durasi_interval_detik: durasi agregasi (mis. 20 atau 60 detik)

    Returns:
        {kelas: flow_per_menit} — mis. {"motor": 15.0, "mobil": 9.0}
    """
    flow: Dict[str, float] = {}
    durasi_menit = durasi_interval_detik / 60.0

    for key, jumlah in counter_interval.items():
        parts = key.split("_", 1)
        if len(parts) != 2:
            continue
        arah, kelas = parts
        if arah == "masuk" and jumlah > 0:
            flow[kelas] = flow.get(kelas, 0.0) + (jumlah / durasi_menit)

    return flow
