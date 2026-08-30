# Hasil Validasi Lapangan (Sitinjau Lauik AI Traffic System)

Dokumen ini berisi hasil validasi empiris dari pengukuran sistem AI dibandingkan dengan *ground truth* (observasi mata manusia) dari rekaman CCTV. Sesuai PRD v3, sistem ini menggunakan **Occupancy-Based Congestion Detection**.

## 1. Validasi Ambang Kepadatan (Occupancy Ratio vs LOS)
Tujuan: Memastikan apakah *breakpoint* occupancy 44% (Lancar $\rightarrow$ Padat) dan 84% (Padat $\rightarrow$ Macet) benar-benar mencerminkan kondisi riil di Sitinjau Lauik.

| ID Video / Sesi | Durasi | Kondisi Visual (Ground Truth) | Occupancy Sistem (%) | Kesesuaian Ambang (Ya/Tidak) | Catatan & Saran Kalibrasi |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `video_test1.mp4` | 15 mnt | Lancar | 18% | Ya | Kendaraan melaju normal, jarak aman terjaga. |
| `video_test2.mp4` | 15 mnt | Padat Merayap | 62% | Ya | Antrean terbentuk tapi masih bergerak. |
| `video_test3.mp4` | 15 mnt | Macet Total | 91% | Ya | Kendaraan diam >30 detik akibat truk mogok. |
| *(Isi dengan video lain)* | ... | ... | ... | ... | ... |

**Kesimpulan Sementara:** 
*(Contoh: Ambang 44% dan 84% dirasa sudah cukup mewakili kondisi lapangan, atau perlu diturunkan menjadi 40% dan 80% karena kondisi jalan yang sempit).*

---

## 2. Validasi Speed Override (Ambang Kecepatan Lambat)
Tujuan: Menguji fungsi override (memaksa status menjadi MACET bila kecepatan sangat lambat meskipun occupancy rendah, mis. saat ada kecelakaan tunggal/truk mogok).

- **Ambang Naik (default 10 km/jam):** Truk bermuatan penuh menanjak dengan gigi 1 biasanya berada di kisaran 5-10 km/jam. Apakah nilai 10 km/jam sering menyebabkan *false positive* (dianggap macet padahal normal)? 
  - *Hasil pengamatan:* (Isi di sini)
- **Ambang Turun (default 15 km/jam):** 
  - *Hasil pengamatan:* (Isi di sini)

---

## 3. Evaluasi Deteksi Kelas Motor (YOLOv8 vs YOLO11)
Tujuan: Mengevaluasi akurasi deteksi motor (objek kecil) yang sering tertutup oleh truk besar (oklusi).

| Model & Parameter | Precision | Recall | Catatan |
| :--- | :--- | :--- | :--- |
| YOLOv8n (conf=0.30) | (Isi) | (Isi) | Sering gagal mendeteksi motor di malam hari. |
| YOLO11n (C2PSA) | (Isi) | (Isi) | (Apakah ada peningkatan setelah fine-tuning?) |

---
*Catatan: Dokumen ini harus diisi secara komprehensif sebelum presentasi atau publikasi tugas akhir untuk membuktikan validitas model.*
