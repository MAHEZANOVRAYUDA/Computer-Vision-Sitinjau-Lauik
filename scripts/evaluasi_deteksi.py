"""
evaluasi_deteksi.py
====================
Evaluasi precision/recall/F1/mAP@0.5 model deteksi terhadap ground
truth berlabel manual, di level DETEKSI OBJEK PER FRAME (bukan
hitungan agregat seperti hitung_akurasi.py).

Melengkapi hitung_akurasi.py: script itu mengukur akurasi HITUNGAN
akhir (setelah tracking+counting line), script ini mengukur akurasi
DETEKSI mentah model YOLO — dua metrik berbeda yang KEDUANYA
dibutuhkan untuk paper Scopus (standar evaluasi computer vision).

Memakai fitur validasi bawaan Ultralytics YOLO (model.val()) yang
sudah mengimplementasikan mAP standar COCO-style.

Cara pakai:
    # Evaluasi dengan model fine-tuned:
    python scripts/evaluasi_deteksi.py \\
        --model models/sitinjau_lauik_v1/weights/best.pt \\
        --data data/fine_tuning/data.yaml

    # Evaluasi model baseline COCO:
    python scripts/evaluasi_deteksi.py \\
        --model models/yolov8s.pt \\
        --data data/fine_tuning/data.yaml \\
        --split val

    # Simpan output ke file:
    python scripts/evaluasi_deteksi.py \\
        --model models/yolov8s.pt \\
        --data data/fine_tuning/data.yaml \\
        > data/logs/eval_deteksi_sebelum.txt

Prasyarat:
    - Dataset fine-tuning sudah disiapkan di data/fine_tuning/
    - data.yaml berisi path ke split 'val' atau 'test' yang berlabel
    - Minimal 100-200 frame representatif dari kamera Sitinjau Lauik
      yang dilabel manual (format YOLO: .txt per gambar)

Urutan evaluasi lengkap untuk paper:
    1. Evaluasi baseline (sebelum fine-tuning)
    2. Fine-tuning: python scripts/fine_tune.py ...
    3. Evaluasi sesudah fine-tuning
    4. Masukkan angka ke docs/HASIL_VALIDASI.md
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(
        description="Evaluasi precision/recall/mAP model deteksi kendaraan.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Path ke file model .pt (contoh: models/yolov8s.pt atau models/sitinjau_lauik_v1/weights/best.pt)"
    )
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Path ke data.yaml (harus punya split 'test' atau 'val' berlabel)"
    )
    parser.add_argument(
        "--split",
        type=str,
        default="test",
        choices=["val", "test"],
        help="Split dataset untuk evaluasi (default: test)"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cuda",
        choices=["cuda", "cpu"],
        help="Device inferensi (default: cuda)"
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Ukuran gambar untuk inferensi (default: 640)"
    )
    args = parser.parse_args()

    # Validasi paths
    model_path = Path(args.model)
    data_path = Path(args.data)

    if not model_path.exists():
        print(f"[ERROR] File model tidak ditemukan: {model_path}")
        sys.exit(1)

    if not data_path.exists():
        print(f"[ERROR] File data.yaml tidak ditemukan: {data_path}")
        print("Pastikan dataset sudah disiapkan di data/fine_tuning/")
        sys.exit(1)

    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] Package 'ultralytics' tidak terinstall.")
        print("Jalankan: pip install ultralytics")
        sys.exit(1)

    print("=" * 70)
    print("EVALUASI MODEL DETEKSI — Sitinjau Lauik Traffic System")
    print("=" * 70)
    print(f"Model  : {model_path}")
    print(f"Data   : {data_path}")
    print(f"Split  : {args.split}")
    print(f"Device : {args.device}")
    print(f"Imgsz  : {args.imgsz}")
    print("=" * 70)
    print()

    model = YOLO(str(model_path))

    try:
        hasil = model.val(
            data=str(data_path),
            split=args.split,
            device=args.device,
            imgsz=args.imgsz,
            verbose=False,
        )
    except Exception as e:
        print(f"[ERROR] Gagal menjalankan evaluasi: {e}")
        sys.exit(1)

    print("=" * 70)
    print(f"HASIL EVALUASI DETEKSI — split: {args.split}")
    print("=" * 70)
    print(f"mAP50     : {hasil.box.map50:.4f}   ({hasil.box.map50 * 100:.2f}%)")
    print(f"mAP50-95  : {hasil.box.map:.4f}   ({hasil.box.map * 100:.2f}%)")
    print(f"Precision : {hasil.box.mp:.4f}   ({hasil.box.mp * 100:.2f}%)")
    print(f"Recall    : {hasil.box.mr:.4f}   ({hasil.box.mr * 100:.2f}%)")
    print()
    print("Per kelas:")
    print(f"{'Kelas':<12} {'AP50':>8} {'AP50-95':>10}")
    print("-" * 32)
    for i, nama_kelas in hasil.names.items():
        try:
            print(f"  {nama_kelas:<10} {hasil.box.ap50[i]:>8.4f} {hasil.box.ap[i]:>10.4f}")
        except (IndexError, AttributeError):
            continue
    print("=" * 70)
    print()
    print("Simpan angka-angka ini untuk tabel hasil di naskah paper.")
    print("Format standar: Precision, Recall, mAP@0.5, mAP@0.5:0.95 per kelas.")
    print()
    print("Langkah berikutnya:")
    print("  1. Salin angka-angka di atas ke docs/HASIL_VALIDASI.md")
    print("  2. Bandingkan dengan baseline sebelum fine-tuning")
    print("  3. Jalankan hitung_akurasi.py untuk MAPE hitungan agregat")


if __name__ == "__main__":
    main()
