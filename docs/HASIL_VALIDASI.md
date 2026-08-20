# Hasil Validasi Sistem — untuk Naskah Paper

> Dokumen ini dikumpulkan dari hasil evaluasi kuantitatif sistem.
> Isi tabel di bawah setelah menjalankan:
> - `scripts/evaluasi_deteksi.py` (precision/recall/mAP)
> - `scripts/hitung_akurasi.py` (MAPE hitungan agregat)

---

## 1. Precision/Recall/mAP Deteksi (level frame)

Evaluasi menggunakan `model.val()` dari Ultralytics YOLO, standar COCO-style mAP.
Dataset: frame-frame representatif dari kamera Sitinjau Lauik yang dilabel manual.

| Model | mAP@0.5 | mAP@0.5:0.95 | Precision | Recall |
|---|---|---|---|---|
| YOLOv8s baseline (COCO) | ... | ... | ... | ... |
| YOLOv8s fine-tuned (Sitinjau Lauik) | ... | ... | ... | ... |
| YOLO11s fine-tuned (Sitinjau Lauik, opsional) | ... | ... | ... | ... |

### Per Kelas — YOLOv8s baseline

| Kelas | AP@0.5 | AP@0.5:0.95 |
|---|---|---|
| motor | ... | ... |
| mobil | ... | ... |
| bus | ... | ... |
| truk | ... | ... |

### Per Kelas — YOLOv8s fine-tuned

| Kelas | AP@0.5 | AP@0.5:0.95 |
|---|---|---|
| motor | ... | ... |
| mobil | ... | ... |
| bus | ... | ... |
| truk | ... | ... |

---

## 2. MAPE Hitungan Agregat (level counting line)

Evaluasi menggunakan `scripts/hitung_akurasi.py`. Bandingkan hitungan sistem
dengan hitungan manual surveyor pada periode waktu yang sama.

| Kelas | MAPE Sebelum Fine-tuning | MAPE Sesudah Fine-tuning | Target Akademis |
|---|---|---|---|
| Motor | ...% | ...% | ≤10% |
| Mobil | ...% | ...% | ≤15% |
| Bus | ...% | ...% | ≤20% |
| Truk | ...% | ...% | ≤20% |
| **Total** | ...% | ...% | ≤15% |

---

## 3. Validasi V/C Ratio MKJI vs Survei Manual

Bandingkan V/C ratio yang dihitung sistem dengan V/C ratio hasil perhitungan
manual menggunakan data volume surveyor pada periode yang sama.

| Tanggal | Jam | V/C Sistem (MKJI) | V/C Manual | Selisih |
|---|---|---|---|---|
| ... | ... | ... | ... | ...% |

---

## 4. Kondisi Validasi

| Parameter | Nilai |
|---|---|
| Jumlah frame dilabel (precision/recall) | ... |
| Periode survei manual (MAPE) | ... |
| Kamera yang digunakan saat survei | Gerbang A |
| Status kalibrasi pixel_per_meter | [ ] Belum / [ ] Sudah (... px/m) |
| Model baseline | YOLOv8s (COCO pretrained) |
| Model fine-tuned | Menunggu dataset lokal |

---

## 5. Catatan Metodologi

- **MKJI 1997**: V/C ratio dihitung menggunakan EMP medan gunung sesuai
  Tabel 5-5 MKJI. Kapasitas dasar C0 = 2100 smp/jam (jalan 2/2 UD, medan gunung).
  Faktor koreksi: FCw=0.90 (lebar jalur 3-3.5m), FCsp=FCsf=FCcs=1.00.
  **WAJIB divalidasi dengan survei lapangan sebelum klaim akademis.**

- **EMP bus dan truk**: Nilai 3.25 (bus) dan 5.0 (truk) adalah titik tengah
  rentang MKJI untuk medan gunung. Belum divalidasi dengan survei lapangan
  Sitinjau Lauik. Nilai ini harus disesuaikan berdasarkan data riil.

- **pixel_per_meter**: Nilai 25.0 adalah placeholder. Kecepatan dan LOS hybrid
  tidak valid sampai kalibrasi lapangan dilakukan dengan `kalibrasi_garis.py --kalibrasi-meter`.

---

## 6. Referensi

- MKJI 1997, Direktorat Jenderal Bina Marga, Tabel 5-2 dan 5-5
- Studi Universitas Andalas 2024: kecepatan rata-rata Sitinjau Lauik 37.7-45.4 km/jam
- Blueprint Perbaikan v4 (docs/BLUEPRINT_PERBAIKAN_v4.md)
