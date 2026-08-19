# Parameter MKJI — Sitinjau Lauik Traffic System

> [!IMPORTANT]
> Dokumen ini adalah panduan untuk **memvalidasi dan memperbarui parameter MKJI** yang digunakan sistem pakar. Nilai di `config/config.yaml` bersifat **sementara** dan harus digantikan hasil survei lapangan sebelum digunakan untuk klaim akademis atau kebijakan publik.

---

## 1. Kapasitas Dasar Ruas Jalan

### Nilai Saat Ini (Prototipe)
```yaml
# config/config.yaml
sistem_pakar:
  kapasitas_dasar_smp_per_jam: 1500
```

**Mengapa 1500 bermasalah:** Nilai 1500 SMP/jam adalah kapasitas tipikal **jalan arteri datar** 2-lajur di perkotaan. Sitinjau Lauik adalah jalan pegunungan dengan karakteristik sangat berbeda.

---

### Referensi MKJI 1997 untuk Jalan 2-Lajur Tak Terbagi (2/2 UD)

| Kondisi | Kapasitas Dasar (total 2 arah) | Per Arah |
|---|---|---|
| Datar, lebar 6m | 2.900 smp/jam | ~1.450 smp/jam |
| Bukit, lebar 6m | 2.500 smp/jam | ~1.250 smp/jam |
| Gunung, lebar 6m | 2.100 smp/jam | ~1.050 smp/jam |

*Sumber: MKJI 1997, Tabel 5-2, halaman 5-6*

**Faktor Koreksi yang Relevan untuk Sitinjau Lauik:**

| Faktor | Nilai | Koefisien MKJI |
|---|---|---|
| Lebar jalur (FCw) | 3.0–3.5m per lajur | 0.87–1.00 |
| Hambatan samping (FFVsf) | Rendah (jalan luar kota) | ~1.00 |
| Ukuran kota (FFVcs) | — (jalan rural) | 1.00 |

**Estimasi kapasitas yang lebih realistis:**
```
C = C₀ × FCw × FCsp × FCsf
C ≈ 2100 × 0.90 × 1.00 × 1.00 = 1890 smp/jam (total 2 arah)
Per arah ≈ 945 smp/jam
```

> [!WARNING]
> Ini masih **estimasi kasar**. Nilai yang benar harus diperoleh dari **survei lalu lintas lapangan** dengan menghitung volume kendaraan aktual menggunakan metode MKJI.

---

## 2. Nilai EMP (Ekuivalen Mobil Penumpang)

### Nilai Saat Ini
```yaml
emp_smp:
  motor: 0.4
  mobil: 1.0
  bus: 1.8
  truk: 1.9
```

### Referensi MKJI 1997 untuk Jalan 2-Lajur (Tabel 5-5)

| Jenis Kendaraan | Datar | Bukit | Gunung |
|---|---|---|---|
| Sepeda motor (MC) | 0.4 | 0.4 | 0.4 |
| Mobil penumpang (LV) | 1.0 | 1.0 | 1.0 |
| Bus kecil/sedang (MHV) | 1.2–1.8 | 1.8–2.4 | 3.0–3.5 |
| Bus besar / Truk besar (LB/LT) | 1.5–2.0 | 2.5–3.5 | 4.0–6.0 |

*Sumber: MKJI 1997, Tabel 5-5*

### Implikasi untuk Sitinjau Lauik

Sitinjau Lauik memiliki **gradien 8–12%** yang termasuk kategori **Gunung** dalam MKJI. Nilai EMP truk yang benar kemungkinan berada di rentang **4.0–5.5**, bukan 1.9 yang saat ini digunakan.

**Dampak underestimasi EMP:**
- Volume SMP dihitung terlalu rendah untuk ruas dengan banyak truk/bus
- Rasio V/C yang dihasilkan lebih kecil dari kondisi nyata
- Sistem bisa melaporkan "lancar" padahal kondisi jalan sudah overloaded akibat truk besar

> [!CAUTION]
> Menggunakan EMP yang tidak tepat dapat menyebabkan sistem **meremehkan kemacetan secara signifikan** terutama saat lalu lintas didominasi truk dan bus berat yang sering melintas di Sitinjau Lauik.

---

## 3. Ambang Batas V/C Ratio (LOS)

### Nilai Saat Ini
```yaml
ambang_batas:
  lancar_maks_vc: 0.54   # LOS A-B
  padat_maks_vc: 0.90    # LOS C-E
  # > 0.90 = macet (LOS F)
```

### Referensi MKJI — Level of Service (LOS)

| LOS | Rasio V/C | Deskripsi Kondisi |
|---|---|---|
| **A** | ≤ 0.35 | Arus bebas, kecepatan tinggi |
| **B** | 0.35–0.54 | Arus stabil, sedikit hambatan |
| **C** | 0.54–0.60 | Arus stabil, masih dapat diterima |
| **D** | 0.60–0.80 | Arus mendekati tidak stabil |
| **E** | 0.80–0.90 | Tidak stabil, antrian mulai |
| **F** | > 0.90 | Breakdown, kemacetan penuh |

Nilai ambang batas yang digunakan saat ini (**0.54** dan **0.90**) sudah sesuai standar MKJI.

---

## 4. Prosedur Validasi Lapangan

### Langkah 1 — Survei Volume Lalu Lintas Manual
1. Tentukan 2 titik pengamatan: Gerbang A dan Gerbang B
2. Hitung kendaraan secara manual selama **1 jam peak** (pagi: 07:00–09:00, sore: 16:00–18:00)
3. Catat per kategori: motor, mobil, bus, truk
4. Lakukan minimal **3 hari** pengamatan (hari kerja + akhir pekan)

### Langkah 2 — Hitung Kapasitas Riil
Gunakan rumus MKJI:
```
C = C₀ × FCw × FCsp × FCsf × FCcs
```
Dimana:
- **C₀** = Kapasitas dasar dari tabel MKJI (sesuai tipe jalan & medan)
- **FCw** = Faktor koreksi lebar jalur
- **FCsp** = Faktor koreksi pemisahan arah
- **FCsf** = Faktor koreksi hambatan samping
- **FCcs** = Faktor koreksi ukuran kota

### Langkah 3 — Update Konfigurasi
Setelah mendapat nilai dari survei, update `config/config.yaml`:
```yaml
sistem_pakar:
  # Nilai tervalidasi dari survei MKJI, tanggal: [isi tanggal survei]
  # Surveyor: [nama tim/institusi]
  kapasitas_dasar_smp_per_jam: [nilai_dari_survei]

emp_smp:
  motor: 0.4       # Tetap (MKJI semua medan)
  mobil: 1.0       # Tetap (referensi)
  bus:   [nilai]   # Sesuai gradien lapangan
  truk:  [nilai]   # Sesuai gradien lapangan
```

### Langkah 4 — Validasi Silang dengan Sistem
1. Jalankan sistem bersamaan dengan penghitung manual selama 30 menit
2. Bandingkan rasio V/C yang dihitung sistem vs. dihitung manual
3. Toleransi yang dapat diterima: **±15%**
4. Jika akurasi < 85%, lakukan fine-tuning model YOLO (lihat `VALIDASI_AKURASI.md`)

---

## 5. Ringkasan Nilai yang Perlu Diperbarui

| Parameter | Nilai Sekarang | Nilai Rekomendasi | Prioritas |
|---|---|---|---|
| `kapasitas_dasar_smp_per_jam` | 1500 | ~900–1050 (survei) | 🔴 Kritis |
| `emp_smp.bus` | 1.8 | 3.0–3.5 (gunung) | 🟡 Penting |
| `emp_smp.truk` | 1.9 | 4.0–5.5 (gunung) | 🟡 Penting |
| `emp_smp.motor` | 0.4 | 0.4 (sudah benar) | ✅ OK |
| `emp_smp.mobil` | 1.0 | 1.0 (sudah benar) | ✅ OK |
| `ambang_lancar_maks_vc` | 0.54 | 0.54 (sudah sesuai MKJI) | ✅ OK |
| `ambang_padat_maks_vc` | 0.90 | 0.90 (sudah sesuai MKJI) | ✅ OK |
