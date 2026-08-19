"""
test_counting_line.py
======================
Unit test untuk modul counting_line.py - ini logika PALING KRITIKAL
di seluruh sistem karena menentukan akurasi penghitungan kendaraan.

Cara menjalankan:
    pytest tests/test_counting_line.py -v
"""

from src.counting_line import GarisVirtual, PelacakLintasGaris


def buat_garis_horizontal_sederhana():
    """Garis horizontal dari (0, 400) ke (900, 400) - kendaraan lewat dari atas ke bawah atau sebaliknya."""
    return GarisVirtual(
        lajur_id="lajur_test",
        arah="masuk",
        titik_1=(0, 400),
        titik_2=(900, 400),
        toleransi_piksel=8,
    )


def test_objek_belum_melewati_garis_tidak_terhitung():
    """Objek yang tetap di satu sisi garis (tidak pernah menyeberang) tidak boleh terhitung."""
    garis = buat_garis_horizontal_sederhana()
    pelacak = PelacakLintasGaris([garis])

    # Track ID 1 bergerak dari y=100 ke y=200 ke y=300 - semua di atas garis (y=400), belum menyeberang
    assert pelacak.proses_deteksi(1, 450, 100) == []
    assert pelacak.proses_deteksi(1, 450, 200) == []
    events = pelacak.proses_deteksi(1, 450, 300)
    assert events == []


def test_objek_melewati_garis_terhitung_sekali():
    """Objek yang menyeberang garis dari atas ke bawah harus terhitung TEPAT SATU KALI."""
    garis = buat_garis_horizontal_sederhana()
    pelacak = PelacakLintasGaris([garis])

    pelacak.proses_deteksi(1, 450, 350)  # di atas garis (sisi 1)
    events = pelacak.proses_deteksi(1, 450, 450)  # sekarang di bawah garis (sisi 2) -> menyeberang!

    assert len(events) == 1
    assert events[0]["lajur_id"] == "lajur_test"
    assert events[0]["arah"] == "masuk"
    assert events[0]["track_id"] == 1


def test_objek_tidak_dihitung_dua_kali_walau_bolak_balik():
    """
    Ini test PALING PENTING - mensimulasikan objek yang terdeteksi
    'gemetar' di sekitar garis selama beberapa frame (noise deteksi).
    Track ID yang sama TIDAK BOLEH dihitung lebih dari sekali untuk garis yang sama.
    """
    garis = buat_garis_horizontal_sederhana()
    pelacak = PelacakLintasGaris([garis])

    pelacak.proses_deteksi(1, 450, 350)  # sisi atas
    events_1 = pelacak.proses_deteksi(1, 450, 450)  # menyeberang ke bawah -> HARUS terhitung
    events_2 = pelacak.proses_deteksi(1, 450, 350)  # balik lagi ke atas -> TIDAK BOLEH terhitung lagi
    events_3 = pelacak.proses_deteksi(1, 450, 450)  # balik lagi ke bawah -> TIDAK BOLEH terhitung lagi

    total_terhitung = len(events_1) + len(events_2) + len(events_3)
    assert total_terhitung == 1, (
        f"Objek dengan track_id sama seharusnya hanya terhitung 1 kali, "
        f"tapi terhitung {total_terhitung} kali (indikasi bug double-counting)"
    )


def test_dua_track_id_berbeda_dihitung_terpisah():
    """Dua kendaraan berbeda (track_id berbeda) yang sama-sama menyeberang harus dihitung masing-masing."""
    garis = buat_garis_horizontal_sederhana()
    pelacak = PelacakLintasGaris([garis])

    pelacak.proses_deteksi(1, 450, 350)
    pelacak.proses_deteksi(2, 300, 350)

    events_1 = pelacak.proses_deteksi(1, 450, 450)
    events_2 = pelacak.proses_deteksi(2, 300, 450)

    assert len(events_1) == 1
    assert len(events_2) == 1
    assert events_1[0]["track_id"] == 1
    assert events_2[0]["track_id"] == 2


def test_bersihkan_track_hilang_menghapus_state():
    """Setelah track_id dibersihkan (kendaraan keluar frame), state-nya harus hilang dari memory."""
    garis = buat_garis_horizontal_sederhana()
    pelacak = PelacakLintasGaris([garis])

    pelacak.proses_deteksi(1, 450, 350)
    assert (1, "lajur_test") in pelacak._sisi_terakhir

    pelacak.bersihkan_track_hilang(track_id_aktif=[])  # track 1 tidak lagi aktif

    assert (1, "lajur_test") not in pelacak._sisi_terakhir


def test_dua_garis_independen_tidak_saling_pengaruh():
    """Dua lajur berbeda (garis berbeda) harus independen - lewat 1 garis tidak menghitung garis lainnya."""
    garis_kiri = GarisVirtual("lajur_kiri", "masuk", (0, 400), (400, 400), 8)
    garis_kanan = GarisVirtual("lajur_kanan", "keluar", (500, 400), (900, 400), 8)
    pelacak = PelacakLintasGaris([garis_kiri, garis_kanan])

    # Objek hanya bergerak di area lajur kiri (x < 400)
    pelacak.proses_deteksi(1, 200, 350)
    events = pelacak.proses_deteksi(1, 200, 450)

    # Hanya event dari lajur_kiri yang boleh muncul, bukan lajur_kanan
    assert len(events) == 1
    assert events[0]["lajur_id"] == "lajur_kiri"


# =======================================================================
# Test tambahan: kasus edge yang lebih kompleks
# =======================================================================

def test_garis_diagonal_terdeteksi_benar():
    """
    Garis diagonal (bukan horizontal/vertikal) harus bekerja dengan benar.
    Penting karena kamera lapangan jarang memasang garis lurus sempurna.

    Garis dari (0, 400) ke (900, 0) - diagonal kanan-atas.
    Kendaraan bergerak dari (200, 100) ke (200, 500):
    - Di (200, 100): sisi_titik = positif (di atas garis)
    - Di (200, 500): sisi_titik = negatif (di bawah garis)
    -> Menyeberang garis -> harus terhitung
    """
    garis = GarisVirtual(
        lajur_id="lajur_diagonal",
        arah="masuk",
        titik_1=(0, 400),
        titik_2=(900, 0),
        toleransi_piksel=8,
    )
    pelacak = PelacakLintasGaris([garis])

    # x=200: garis di y ≈ 311 (interpolasi linear dari (0,400)-(900,0))
    # Objek bergerak dari y=100 (di atas garis) ke y=500 (di bawah garis)
    pelacak.proses_deteksi(1, 200, 100)   # Jelas di atas garis diagonal
    events = pelacak.proses_deteksi(1, 200, 500)  # Jelas di bawah garis diagonal

    assert len(events) == 1, "Garis diagonal harus mendeteksi penyeberangan"
    assert events[0]["lajur_id"] == "lajur_diagonal"



def test_skenario_uturn_hanya_terhitung_sekali():
    """
    Simulasi kendaraan yang berbalik arah (U-turn) setelah melewati garis.

    Skenario:
    1. Motor melewati garis (masuk) -> terhitung 1x
    2. Motor berbalik melewati garis lagi (keluar) -> TIDAK terhitung lagi
       (karena _sudah_dihitung = True untuk track_id ini di garis ini)

    Ini adalah trade-off desain yang disengaja: akurasi counting lebih penting
    dari melacak gerakan bolak-balik. Kendaraan U-turn adalah edge case langka.
    """
    garis = GarisVirtual("lajur_test", "masuk", (0, 400), (900, 400), 8)
    pelacak = PelacakLintasGaris([garis])

    # Frame 1: kendaraan di atas garis
    pelacak.proses_deteksi(1, 450, 350)
    # Frame 2: kendaraan melewati garis -> dihitung 1x
    events_pertama = pelacak.proses_deteksi(1, 450, 450)
    # Frame 3: kendaraan berbalik ke atas garis lagi
    events_balik = pelacak.proses_deteksi(1, 450, 350)
    # Frame 4: kendaraan menyeberang lagi ke bawah
    events_kedua = pelacak.proses_deteksi(1, 450, 450)

    total = len(events_pertama) + len(events_balik) + len(events_kedua)
    assert total == 1, (
        f"Kendaraan U-turn hanya boleh terhitung 1x, tapi terhitung {total}x"
    )


def test_objek_di_luar_rentang_segmen_tidak_terhitung():
    """
    Objek yang berada secara matematis 'di sisi yang sama' tapi berada JAUH
    di luar batas fisik segmen garis tidak boleh terhitung.

    Contoh: garis dari (100, 400) ke (500, 400).
    Objek di (800, 399) yang berpindah ke (800, 401) — secara matematik
    menyeberangi GARIS TAK TERHINGGA yang melalui titik garis, tapi objek
    ini ada di x=800 yang jauh di luar segmen [100..500].
    """
    garis = GarisVirtual("lajur_test", "masuk", (100, 400), (500, 400), 8)
    pelacak = PelacakLintasGaris([garis])

    pelacak.proses_deteksi(1, 800, 399)  # Jauh di luar segmen, di atas
    events = pelacak.proses_deteksi(1, 800, 401)  # Jauh di luar segmen, di bawah

    assert len(events) == 0, (
        "Objek di luar rentang segmen fisik tidak boleh terhitung "
        "meski menyeberangi garis tak terhingga"
    )


def test_tidak_ada_memory_leak_setelah_banyak_track_hilang():
    """
    Simulasi skenario jangka panjang: 1000 kendaraan datang dan pergi.
    Setelah semua track dibersihkan, dictionary state harus kosong.

    Mencegah memory leak di sistem 24/7 yang bisa berjalan berhari-hari.
    """
    garis = GarisVirtual("lajur_test", "masuk", (0, 400), (900, 400), 8)
    pelacak = PelacakLintasGaris([garis])

    # Simulasi 1000 kendaraan lewat
    for tid in range(1000):
        pelacak.proses_deteksi(tid, 450, 350)  # sebelum garis
        pelacak.proses_deteksi(tid, 450, 450)  # lewat garis

    # Sekarang semua track pergi (tidak ada yang aktif)
    pelacak.bersihkan_track_hilang(track_id_aktif=[])

    # State internal harus kosong sempurna
    assert len(pelacak._sisi_terakhir) == 0, (
        f"Memory leak: _sisi_terakhir masih punya {len(pelacak._sisi_terakhir)} entries"
    )
    assert len(pelacak._sudah_dihitung) == 0, (
        f"Memory leak: _sudah_dihitung masih punya {len(pelacak._sudah_dihitung)} entries"
    )


def test_bersihkan_hanya_track_yang_hilang_bukan_semua():
    """
    bersihkan_track_hilang() harus HANYA menghapus track yang tidak ada
    di track_id_aktif, bukan menghapus track yang masih aktif.
    """
    garis = GarisVirtual("lajur_test", "masuk", (0, 400), (900, 400), 8)
    pelacak = PelacakLintasGaris([garis])

    # Track 1 dan 2 muncul
    pelacak.proses_deteksi(1, 450, 350)
    pelacak.proses_deteksi(2, 450, 350)

    # Track 1 hilang, track 2 masih aktif
    pelacak.bersihkan_track_hilang(track_id_aktif=[2])

    # State track 1 harus hilang
    assert (1, "lajur_test") not in pelacak._sisi_terakhir
    # State track 2 harus TETAP ada
    assert (2, "lajur_test") in pelacak._sisi_terakhir

