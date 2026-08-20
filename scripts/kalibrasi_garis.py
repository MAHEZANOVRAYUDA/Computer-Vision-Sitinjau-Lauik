"""
kalibrasi_garis.py
===================
Script BANTUAN untuk menentukan koordinat garis virtual (counting line)
secara visual, tanpa perlu menebak-nebak angka piksel secara manual.

CARA PAKAI — Mode 1 (Kalibrasi Garis):
1. Jalankan: python scripts/kalibrasi_garis.py
2. Sebuah jendela akan muncul menampilkan frame pertama dari sumber video
   yang dikonfigurasi di config/config.yaml
3. Klik 4 titik dengan urutan:
   - Titik 1 & 2: garis untuk LAJUR KIRI (arah masuk)
   - Titik 3 & 4: garis untuk LAJUR KANAN (arah keluar)
4. Setelah 4 titik diklik, koordinat akan dicetak ke terminal dalam
   format YAML siap-tempel untuk config/config.yaml
5. Tekan 'r' untuk reset dan mengulang klik, 'q' untuk keluar

CARA PAKAI — Mode 2 (Kalibrasi pixel_per_meter):
1. Jalankan: python scripts/kalibrasi_garis.py --kalibrasi-meter
2. Sebuah jendela akan muncul menampilkan frame dari video/kamera
3. Klik 2 titik yang JARAK RIILNYA DIKETAHUI di lapangan
   (mis. jarak antar marka jalan 3m, atau lebar lajur 3-3.5m)
4. Input jarak riil dalam meter saat diminta
5. Script mencetak nilai pixel_per_meter untuk disalin ke config YAML

CATATAN PENTING:
Jalankan script ini SETIAP KALI posisi/sudut kamera berubah,
karena garis virtual dan pixel_per_meter sangat bergantung pada sudut pandang kamera.
"""

import sys
import argparse
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config_loader import load_config

titik_diklik = []
frame_asli = None


def callback_mouse(event, x, y, flags, param):
    global titik_diklik, frame_asli

    if event == cv2.EVENT_LBUTTONDOWN:
        titik_diklik.append((x, y))
        print(f"Titik ke-{len(titik_diklik)} diklik: ({x}, {y})")

        frame_tampil = frame_asli.copy()
        gambar_progres(frame_tampil)
        cv2.imshow("Kalibrasi Garis Virtual", frame_tampil)

        if len(titik_diklik) == 4:
            cetak_hasil_yaml()


def gambar_progres(frame):
    """Menggambar titik dan garis yang sudah diklik sejauh ini."""
    warna_titik = (0, 0, 255)
    for i, titik in enumerate(titik_diklik):
        cv2.circle(frame, titik, 6, warna_titik, -1)
        cv2.putText(
            frame, str(i + 1), (titik[0] + 10, titik[1]),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, warna_titik, 2,
        )

    if len(titik_diklik) >= 2:
        cv2.line(frame, titik_diklik[0], titik_diklik[1], (0, 255, 255), 2)
        cv2.putText(
            frame, "LAJUR KIRI (masuk)",
            (titik_diklik[0][0], titik_diklik[0][1] - 15),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2,
        )

    if len(titik_diklik) == 4:
        cv2.line(frame, titik_diklik[2], titik_diklik[3], (255, 0, 255), 2)
        cv2.putText(
            frame, "LAJUR KANAN (keluar)",
            (titik_diklik[2][0], titik_diklik[2][1] - 15),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2,
        )


def cetak_hasil_yaml():
    print("\n" + "=" * 70)
    print("KALIBRASI SELESAI - Salin bagian di bawah ini ke config/config.yaml")
    print("(ganti seluruh bagian 'lajur:' yang sudah ada)")
    print("=" * 70)
    print(f"""
lajur:
  - id: "lajur_kiri"
    arah_default: "masuk"
    garis:
      titik_1: [{titik_diklik[0][0]}, {titik_diklik[0][1]}]
      titik_2: [{titik_diklik[1][0]}, {titik_diklik[1][1]}]
    toleransi_piksel: 8

  - id: "lajur_kanan"
    arah_default: "keluar"
    garis:
      titik_1: [{titik_diklik[2][0]}, {titik_diklik[2][1]}]
      titik_2: [{titik_diklik[3][0]}, {titik_diklik[3][1]}]
    toleransi_piksel: 8
""")
    print("=" * 70)
    print("Tekan 'q' untuk keluar, atau 'r' untuk kalibrasi ulang.")


# -----------------------------------------------------------------------
# Mode 2: Kalibrasi pixel_per_meter
# -----------------------------------------------------------------------

titik_meter = []
frame_meter = None


def callback_mouse_meter(event, x, y, flags, param):
    global titik_meter, frame_meter

    if event == cv2.EVENT_LBUTTONDOWN and len(titik_meter) < 2:
        titik_meter.append((x, y))
        print(f"Titik ke-{len(titik_meter)} diklik: ({x}, {y})")

        frame_tampil = frame_meter.copy()
        for i, t in enumerate(titik_meter):
            cv2.circle(frame_tampil, t, 8, (0, 255, 0), -1)
            cv2.putText(
                frame_tampil, f"P{i+1}", (t[0] + 10, t[1]),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
            )
        if len(titik_meter) == 2:
            cv2.line(frame_tampil, titik_meter[0], titik_meter[1], (0, 255, 0), 2)

        cv2.imshow("Kalibrasi pixel_per_meter", frame_tampil)


def kalibrasi_pixel_per_meter(config):
    """
    Mode kalibrasi pixel_per_meter:
    User klik 2 titik yang jarak riilnya diketahui, input jarak meter,
    script menghitung pixel_per_meter = jarak_piksel / jarak_meter.

    Output dicetak ke terminal (TIDAK auto-write ke config — biarkan
    manusia yang commit angka final setelah verifikasi visual).
    """
    global titik_meter, frame_meter

    mode = config.get("video_source.mode", "file")
    width = config.get("video_source.process_width", 960)
    height = config.get("video_source.process_height", 540)

    if mode == "rtsp":
        source = config.get("video_source.rtsp_url")
    else:
        source = config.get("video_source.file_path")

    print(f"[INFO] Membuka sumber video ({mode}): {source}")
    cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        print("[ERROR] Tidak bisa membuka sumber video. Periksa config.yaml Anda.")
        return

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("[ERROR] Gagal membaca frame dari sumber video.")
        return

    frame_meter = cv2.resize(frame, (width, height))

    print("\n" + "=" * 70)
    print("MODE KALIBRASI pixel_per_meter")
    print("=" * 70)
    print("1. Klik 2 titik di frame yang JARAK RIILNYA DIKETAHUI")
    print("   Contoh: jarak antar marka jalan 3m, lebar lajur 3-3.5m,")
    print("   atau dua titik yang diukur dengan meteran saat survei lapangan.")
    print("2. Input jarak riil dalam meter saat diminta.")
    print("3. Salin hasil pixel_per_meter ke config YAML terkait.")
    print("Tekan 'q' untuk keluar.")
    print("=" * 70 + "\n")

    cv2.imshow("Kalibrasi pixel_per_meter", frame_meter)
    cv2.setMouseCallback("Kalibrasi pixel_per_meter", callback_mouse_meter)

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if len(titik_meter) == 2:
            # Hitung jarak piksel antara 2 titik
            x1, y1 = titik_meter[0]
            x2, y2 = titik_meter[1]
            jarak_piksel = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

            print(f"\nJarak piksel antara 2 titik: {jarak_piksel:.2f} piksel")
            try:
                jarak_meter_str = input("Masukkan jarak riil dalam meter (contoh: 3.0): ").strip()
                jarak_meter = float(jarak_meter_str)
                if jarak_meter <= 0:
                    raise ValueError("Jarak harus > 0")
            except ValueError as e:
                print(f"[ERROR] Input tidak valid: {e}")
                titik_meter = []
                continue

            pixel_per_meter = jarak_piksel / jarak_meter

            print("\n" + "=" * 70)
            print("HASIL KALIBRASI pixel_per_meter")
            print("=" * 70)
            print(f"  Jarak piksel : {jarak_piksel:.2f} px")
            print(f"  Jarak meter  : {jarak_meter:.2f} m")
            print(f"  pixel_per_meter = {pixel_per_meter:.4f}")
            print()
            print("Salin baris berikut ke config YAML kamera yang dikalibrasi:")
            print(f"  pixel_per_meter: {pixel_per_meter:.4f}")
            print()
            print("PENTING: Tanggal kalibrasi harus dicatat di komentar config!")
            print("=" * 70)

            # Reset untuk kalibrasi ulang jika perlu
            titik_meter = []
            print("\nKlik 2 titik baru untuk kalibrasi ulang, atau tekan 'q' untuk keluar.")

    cv2.destroyAllWindows()


def main():
    global frame_asli, titik_diklik

    parser = argparse.ArgumentParser(
        description="Kalibrasi garis virtual dan pixel_per_meter untuk kamera Sitinjau Lauik."
    )
    parser.add_argument(
        "--kalibrasi-meter",
        action="store_true",
        help="Mode kalibrasi pixel_per_meter (klik 2 titik dengan jarak riil yang diketahui)",
    )
    args = parser.parse_args()

    config = load_config("config/config.yaml")

    if args.kalibrasi_meter:
        kalibrasi_pixel_per_meter(config)
        return

    # Mode default: kalibrasi garis virtual
    mode = config.get("video_source.mode", "file")
    width = config.get("video_source.process_width", 960)
    height = config.get("video_source.process_height", 540)

    if mode == "rtsp":
        source = config.get("video_source.rtsp_url")
    else:
        source = config.get("video_source.file_path")

    print(f"[INFO] Membuka sumber video ({mode}): {source}")
    cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        print("[ERROR] Tidak bisa membuka sumber video. Periksa config.yaml Anda.")
        return

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("[ERROR] Gagal membaca frame dari sumber video.")
        return

    frame_asli = cv2.resize(frame, (width, height))

    print("\n" + "=" * 70)
    print("PETUNJUK KALIBRASI")
    print("=" * 70)
    print("Klik 4 titik pada jendela video dengan urutan:")
    print("  1 & 2 -> garis untuk LAJUR KIRI (kendaraan arah MASUK)")
    print("  3 & 4 -> garis untuk LAJUR KANAN (kendaraan arah KELUAR)")
    print("Tekan 'r' untuk reset, 'q' untuk keluar.")
    print("=" * 70 + "\n")
    print("TIP: Setelah kalibrasi garis, gunakan --kalibrasi-meter untuk")
    print("     menentukan pixel_per_meter yang akurat per kamera ini.")
    print("=" * 70 + "\n")

    cv2.imshow("Kalibrasi Garis Virtual", frame_asli)
    cv2.setMouseCallback("Kalibrasi Garis Virtual", callback_mouse)

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("r"):
            titik_diklik = []
            cv2.imshow("Kalibrasi Garis Virtual", frame_asli)
            print("[INFO] Direset. Silakan klik ulang 4 titik.")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
