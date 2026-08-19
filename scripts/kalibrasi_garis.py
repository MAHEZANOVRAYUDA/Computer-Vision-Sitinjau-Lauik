"""
kalibrasi_garis.py
===================
Script BANTUAN untuk menentukan koordinat garis virtual (counting line)
secara visual, tanpa perlu menebak-nebak angka piksel secara manual.

CARA PAKAI:
1. Jalankan: python scripts/kalibrasi_garis.py
2. Sebuah jendela akan muncul menampilkan frame pertama dari sumber video
   yang dikonfigurasi di config/config.yaml
3. Klik 4 titik dengan urutan:
   - Titik 1 & 2: garis untuk LAJUR KIRI (arah masuk)
   - Titik 3 & 4: garis untuk LAJUR KANAN (arah keluar)
4. Setelah 4 titik diklik, koordinat akan dicetak ke terminal dalam
   format YAML siap-tempel untuk config/config.yaml
5. Tekan 'r' untuk reset dan mengulang klik, 'q' untuk keluar

CATATAN PENTING:
Jalankan script ini SETIAP KALI posisi/sudut kamera berubah,
karena garis virtual sangat bergantung pada sudut pandang kamera.
"""

import sys
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


def main():
    global frame_asli, titik_diklik

    config = load_config("config/config.yaml")
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
