"""
fine_tune.py
=============
Script untuk fine-tuning model YOLOv8 dengan data lokal Sitinjau Lauik.

Kapan perlu dijalankan?
  Jalankan scripts/hitung_akurasi.py terlebih dahulu. Jika MAPE > 20%
  untuk kelas motor (kelas paling dominan), fine-tuning diperlukan.

Persiapan sebelum fine-tuning:
  1. Kumpulkan minimal 500-1000 gambar dari kamera Sitinjau Lauik
  2. Beri label menggunakan Roboflow atau LabelImg
  3. Export ke format YOLO v8 (*.txt per gambar)
  4. Atur struktur folder sesuai yang dijelaskan di bawah

Cara menjalankan:
  python scripts/fine_tune.py
  python scripts/fine_tune.py --model yolov8n.pt --epochs 50   # quick test
  python scripts/fine_tune.py --model yolov8n.pt --epochs 100  # full training

Referensi:
  docs/VALIDASI_AKURASI.md bagian 6 — Panduan Fine-Tuning YOLOv8
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Struktur folder yang diharapkan:
DATASET_DIR = ROOT / "data" / "fine_tuning"
DATASET_YAML = DATASET_DIR / "data.yaml"

DATASET_YAML_TEMPLATE = """\
# data.yaml — konfigurasi dataset YOLO untuk fine-tuning Sitinjau Lauik
# Digenerate otomatis oleh scripts/fine_tune.py

path: {dataset_path}
train: images/train
val: images/val
test: images/test

# Jumlah kelas (sesuai coco_class_mapping di config.yaml)
nc: 4

# Nama kelas — urutan HARUS konsisten dengan label di file .txt
names:
  0: mobil
  1: motor
  2: bus
  3: truk
"""


def cek_dataset():
    """Validasi struktur folder dataset sebelum mulai training."""
    masalah = []

    if not DATASET_DIR.exists():
        masalah.append(f"Folder dataset tidak ada: {DATASET_DIR}")
        return masalah

    for split in ["train", "val"]:
        img_dir = DATASET_DIR / "images" / split
        lbl_dir = DATASET_DIR / "labels" / split

        if not img_dir.exists():
            masalah.append(f"Folder images/{split} tidak ada: {img_dir}")
        else:
            n_img = len(list(img_dir.glob("*.jpg"))) + len(list(img_dir.glob("*.png")))
            if n_img == 0:
                masalah.append(f"Tidak ada gambar di {img_dir}")
            else:
                print(f"  ✅ {split}: {n_img} gambar")

        if not lbl_dir.exists():
            masalah.append(f"Folder labels/{split} tidak ada: {lbl_dir}")

    return masalah


def buat_data_yaml():
    """Buat file data.yaml jika belum ada."""
    if DATASET_YAML.exists():
        print(f"[INFO] data.yaml sudah ada: {DATASET_YAML}")
        return

    DATASET_YAML.parent.mkdir(parents=True, exist_ok=True)
    konten = DATASET_YAML_TEMPLATE.format(dataset_path=str(DATASET_DIR).replace("\\", "/"))
    DATASET_YAML.write_text(konten, encoding="utf-8")
    print(f"[INFO] data.yaml dibuat: {DATASET_YAML}")


def main():
    parser = argparse.ArgumentParser(
        description="Fine-tuning YOLOv8 untuk deteksi kendaraan Sitinjau Lauik.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model",
        type=str,
        default="models/yolov8n.pt",
        help="Path ke model pretrained sebagai starting point (default: models/yolov8n.pt)",
    )
    parser.add_argument(
        "--epochs", type=int, default=100,
        help="Jumlah epoch training (default: 100, quick test: 20)",
    )
    parser.add_argument(
        "--batch", type=int, default=16,
        help="Batch size (kurangi jika VRAM tidak cukup, default: 16)",
    )
    parser.add_argument(
        "--imgsz", type=int, default=640,
        help="Ukuran gambar training (default: 640)",
    )
    parser.add_argument(
        "--device", type=str, default="cuda",
        help="Device: 'cuda' untuk GPU, 'cpu' untuk CPU (default: cuda)",
    )
    parser.add_argument(
        "--nama-run", type=str, default="sitinjau_lauik_v1",
        help="Nama folder output di models/ (default: sitinjau_lauik_v1)",
    )
    parser.add_argument(
        "--cek-saja", action="store_true",
        help="Hanya cek struktur dataset tanpa mulai training",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("FINE-TUNING YOLOv8 — Sitinjau Lauik")
    print("=" * 70)
    print()

    # Cek dataset
    print("[1/3] Memeriksa struktur dataset...")
    masalah = cek_dataset()

    if masalah:
        print()
        print("❌ Dataset belum siap:")
        for m in masalah:
            print(f"   - {m}")
        print()
        print("Panduan persiapan dataset:")
        print(f"  1. Buat folder: {DATASET_DIR}")
        print("  2. Struktur folder:")
        print("       data/fine_tuning/")
        print("         images/train/   (80% gambar, *.jpg atau *.png)")
        print("         images/val/     (15% gambar)")
        print("         images/test/    (5% gambar)")
        print("         labels/train/   (file *.txt per gambar, format YOLO)")
        print("         labels/val/")
        print("         labels/test/")
        print()
        print("  3. Tool labeling: Roboflow (online) atau LabelImg (offline)")
        print("  4. Format label YOLO: satu baris per objek →")
        print("     <class_id> <x_center> <y_center> <width> <height>")
        print("     Class IDs: 0=mobil, 1=motor, 2=bus, 3=truk")
        print()
        print("  Referensi lengkap: docs/VALIDASI_AKURASI.md bagian 6")
        if not args.cek_saja:
            sys.exit(1)

    if args.cek_saja:
        print()
        print("[INFO] Mode --cek-saja: tidak memulai training.")
        return

    # Buat data.yaml
    print()
    print("[2/3] Menyiapkan data.yaml...")
    buat_data_yaml()

    # Cek apakah ultralytics tersedia
    try:
        from ultralytics import YOLO
    except ImportError:
        print()
        print("[ERROR] Package 'ultralytics' tidak terinstall.")
        print("Install dengan: pip install ultralytics")
        sys.exit(1)

    # Cek model pretrained ada
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"[ERROR] File model tidak ditemukan: {model_path}")
        print(f"Download YOLOv8: python -c \"from ultralytics import YOLO; YOLO('yolov8n.pt')\"")
        sys.exit(1)

    # Mulai fine-tuning
    print()
    print("[3/3] Memulai fine-tuning...")
    print(f"  Model    : {args.model}")
    print(f"  Dataset  : {DATASET_YAML}")
    print(f"  Epochs   : {args.epochs}")
    print(f"  Batch    : {args.batch}")
    print(f"  Image sz : {args.imgsz}")
    print(f"  Device   : {args.device}")
    print(f"  Output   : models/{args.nama_run}/")
    print()

    model = YOLO(str(model_path))

    results = model.train(
        data=str(DATASET_YAML),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project="models",
        name=args.nama_run,
        patience=20,          # early stopping jika tidak ada perbaikan 20 epoch
        augment=True,         # data augmentation (flip, mosaic, dll)
        degrees=5.0,          # rotasi kecil — variasi sudut kamera
        hsv_v=0.4,            # variasi kecerahan — penting untuk kondisi kabut/cerah Sitinjau Lauik
        hsv_h=0.015,          # variasi hue kecil
        hsv_s=0.7,            # variasi saturasi — kondisi hujan/cerah
        fliplr=0.5,           # flip horizontal (lajur kiri-kanan)
        mosaic=0.5,           # mosaic augmentation
        verbose=True,
    )

    model_terbaik = Path(results.save_dir) / "weights" / "best.pt"
    print()
    print("=" * 70)
    print("Fine-tuning selesai!")
    print(f"Model terbaik tersimpan di: {model_terbaik}")
    print()
    print("Langkah selanjutnya:")
    print("  1. Update config.yaml:")
    print(f"       model.weights_path: \"{model_terbaik}\"")
    print("       model.confidence_threshold: 0.40  # naikkan sedikit untuk model fine-tuned")
    print("  2. Jalankan validasi ulang:")
    print("       python scripts/hitung_akurasi.py --dari-db ...")
    print("=" * 70)


if __name__ == "__main__":
    main()
