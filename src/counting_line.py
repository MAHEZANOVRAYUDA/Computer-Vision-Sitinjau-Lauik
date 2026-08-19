"""
counting_line.py
=================
Modul inti untuk logika "virtual counting line" (garis hitung virtual).

Konsep:
- Setiap lajur punya 1 garis virtual (didefinisikan 2 titik di frame video).
- Setiap kendaraan yang dilacak (punya track_id dari ByteTrack) dipantau
  posisi titik tengahnya dari frame ke frame.
- Ketika titik tengah kendaraan berpindah dari satu sisi garis ke sisi
  lainnya, DAN track_id tersebut belum pernah dihitung sebelumnya,
  maka dianggap "melewati garis" -> counter bertambah 1.

Kenapa perlu cek "belum pernah dihitung"?
- Karena video berjalan di banyak frame per detik, sebuah kendaraan bisa
  saja terdeteksi tepat di garis selama beberapa frame berturut-turut.
  Tanpa penanda "sudah dihitung", ia bisa ke-count berkali-kali.
  Ini adalah mitigasi risiko #1 di dokumen blueprint asli Anda
  (double counting) - kita implementasikan di level tracker+garis,
  bukan hanya mengandalkan tracker saja.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class GarisVirtual:
    """Representasi satu garis hitung virtual untuk satu lajur."""

    line_id: str
    arah: str  # "masuk" atau "keluar"
    titik_1: Tuple[float, float]
    titik_2: Tuple[float, float]
    toleransi_piksel: float = 8.0
    pixel_per_meter: float = 25.0

    def sisi_titik(self, x: float, y: float) -> float:
        """
        Menghitung di sisi mana sebuah titik (x, y) berada relatif
        terhadap garis ini, menggunakan cross product 2D.
        """
        x1, y1 = self.titik_1
        x2, y2 = self.titik_2
        return (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)

    def dalam_rentang_segmen(self, x: float, y: float, margin_piksel: float = 40.0) -> bool:
        """
        Cek apakah proyeksi titik (x, y) ke garis berada dalam rentang segmen
        titik_1-titik_2 (bukan garis tak terhingga).
        """
        x1, y1 = self.titik_1
        x2, y2 = self.titik_2

        dx, dy = x2 - x1, y2 - y1
        panjang_kuadrat = dx * dx + dy * dy

        if panjang_kuadrat == 0:
            jarak = ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
            return jarak <= margin_piksel

        t = ((x - x1) * dx + (y - y1) * dy) / panjang_kuadrat
        panjang_garis = panjang_kuadrat ** 0.5
        margin_t = margin_piksel / panjang_garis if panjang_garis > 0 else 0

        return -margin_t <= t <= 1 + margin_t


class PelacakLintasGaris:
    """
    Menyimpan state per track_id untuk mendeteksi kapan sebuah
    kendaraan melewati garis virtual, dan memastikan setiap
    track_id hanya dihitung SATU KALI per garis.
    """

    def __init__(self, daftar_garis: List[GarisVirtual]):
        self.daftar_garis = daftar_garis
        self._sisi_terakhir: Dict[Tuple[int, str], float] = {}
        self._sudah_dihitung: Dict[Tuple[int, str], bool] = {}
        # History track untuk estimasi kecepatan
        # Format: _track_history[track_id] = [(y_center, timestamp_detik), ...]
        self._track_history: Dict[int, List[Tuple[float, float]]] = {}

    def proses_deteksi(
        self, track_id: int, x_center: float, y_center: float
    ) -> List[Dict]:
        """
        Dipanggil setiap frame untuk setiap objek yang terlacak.
        """
        events = []
        waktu_sekarang = time.time()

        # Simpan riwayat pergerakan (maks 30 titik untuk hemat memori)
        if track_id not in self._track_history:
            self._track_history[track_id] = []
        self._track_history[track_id].append((y_center, waktu_sekarang))
        if len(self._track_history[track_id]) > 30:
            self._track_history[track_id].pop(0)

        for garis in self.daftar_garis:
            key = (track_id, garis.line_id)

            if self._sudah_dihitung.get(key, False):
                continue

            sisi_sekarang = garis.sisi_titik(x_center, y_center)

            if key not in self._sisi_terakhir:
                self._sisi_terakhir[key] = sisi_sekarang
                continue

            sisi_sebelumnya = self._sisi_terakhir[key]

            if sisi_sebelumnya * sisi_sekarang < 0 and garis.dalam_rentang_segmen(
                x_center, y_center
            ):
                # Objek berpindah sisi -> dianggap melewati garis
                
                # Hitung kecepatan
                speed_kmh = None
                hist = self._track_history[track_id]
                if len(hist) > 1:
                    y_lama, t_lama = hist[0]
                    y_baru, t_baru = hist[-1]
                    delta_t = t_baru - t_lama
                    pixel_dist = abs(y_baru - y_lama)
                    
                    if delta_t > 0 and garis.pixel_per_meter > 0:
                        speed_ms = (pixel_dist / garis.pixel_per_meter) / delta_t
                        speed_kmh = speed_ms * 3.6
                
                events.append(
                    {
                        "line_id": garis.line_id,
                        "arah": garis.arah,
                        "track_id": track_id,
                        "kecepatan_kmh": speed_kmh
                    }
                )
                self._sudah_dihitung[key] = True

            self._sisi_terakhir[key] = sisi_sekarang

        return events

    def bersihkan_track_hilang(self, track_id_aktif: List[int]):
        """
        Membersihkan state untuk track_id yang sudah tidak aktif
        """
        aktif_set = set(track_id_aktif)
        
        # Bersihkan sisi_terakhir & sudah_dihitung
        kunci_dihapus = [k for k in self._sisi_terakhir.keys() if k[0] not in aktif_set]
        for k in kunci_dihapus:
            self._sisi_terakhir.pop(k, None)
            self._sudah_dihitung.pop(k, None)
            
        # Bersihkan history
        track_hilang = [tid for tid in self._track_history.keys() if tid not in aktif_set]
        for tid in track_hilang:
            self._track_history.pop(tid, None)
