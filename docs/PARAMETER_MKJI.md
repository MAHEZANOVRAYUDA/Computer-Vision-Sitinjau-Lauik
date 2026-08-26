# Parameter dan Acuan MKJI 1997

Dokumen ini berisi penjelasan ilmiah dan referensi resmi terkait parameter Manual Kapasitas Jalan Indonesia (MKJI) 1997 yang digunakan dalam perhitungan **Level of Service (LOS)** dan **Kapasitas Jalan** pada sistem Computer Vision Sitinjau Lauik.

> [!IMPORTANT]
> Sistem ini telah diperbarui untuk secara tegas mengikuti standar MKJI 1997 untuk jalan 2-lajur 2-arah tak terbagi (2/2 UD). Nilai `C0` dikoreksi menjadi konstan 2900 smp/jam, tidak lagi menggunakan variasi `C0` per medan (2900/2500/2100) yang salah kaprah pada prototipe awal.

## 1. Kapasitas Dasar ($C_0$)

Berdasarkan **Tabel 5-2 MKJI 1997 (Jalan 2/2 UD)**, kapasitas dasar ditetapkan secara konstan:

- **$C_0$ = 2900 smp/jam** (Total untuk 2 arah lalu lintas)

*Catatan: Pengaruh medan (Datar, Bukit, Gunung) pada jalan tipe 2/2 UD diakomodasi melalui faktor penyesuaian (terutama hambatan samping dan kecepatan bebas), BUKAN melalui penurunan kapasitas dasar secara langsung.*

## 2. Nilai EMP (Ekuivalen Mobil Penumpang)

Karena medan jalan Sitinjau Lauik termasuk dalam kategori **Gunung** (gradien > 8%), nilai konversi kendaraan ke satuan smp mengacu pada **Tabel 5-5 MKJI 1997 (EMP untuk Jalan 2/2 UD - Pegunungan)**.

Sistem menggunakan nilai berikut sebagai titik tengah rentang:
- **Motor (MC):** 0.4
- **Mobil (LV):** 1.0
- **Bus (HV - Penumpang):** 3.25 *(Rentang MKJI: 3.0 - 3.5)*
- **Truk (HV - Barang):** 5.0 *(Rentang MKJI: 4.0 - 6.0)*

> [!WARNING]
> Nilai EMP untuk Bus dan Truk sangat bergantung pada gradien spesifik (hingga 12% di Sitinjau Lauik) dan persentase kendaraan berat (sering >20%). Nilai `3.25` dan `5.0` adalah asumsi awal untuk kalibrasi. **WAJIB divalidasi dengan survei traffic counting manual.**

## 3. Ambang Batas LOS (Level of Service)

Sistem menggunakan rasio Volume per Kapasitas (V/C Ratio) atau Derajat Kejenuhan (DS) untuk menentukan LOS, sesuai dengan kriteria MKJI:

| LOS | Rasio V/C | Karakteristik (Ambang Batas Sistem) |
| :--- | :--- | :--- |
| **A** | 0.00 – 0.20 | Arus bebas, kecepatan tinggi, kondisi sangat lancar |
| **B** | 0.21 – 0.44 | Arus stabil, mulai ada batasan kecepatan (Batas "Lancar") |
| **C** | 0.45 – 0.75 | Arus stabil, kecepatan dikendalikan oleh volume |
| **D** | 0.76 – 0.84 | Arus mendekati tidak stabil (Batas "Padat") |
| **E** | 0.85 – 1.00 | Arus tidak stabil, sering macet |
| **F** | > 1.00 | Macet total (Antrean memanjang) |

Pada sistem, status disederhanakan menjadi 3 kategori:
- **LANCAR**: V/C $\le$ 0.44 (Mencakup LOS A dan B)
- **PADAT**: 0.44 $<$ V/C $\le$ 0.84 (Mencakup LOS C dan D)
- **MACET**: V/C $>$ 0.84 (Mencakup LOS E dan F)

## 4. Faktor Penyesuaian

Kapasitas aktual jalan ($C$) dihitung menggunakan rumus:
**$C = C_0 \times FC_w \times FC_{sp} \times FC_{sf} \times FC_{cs}$**

Parameter default sistem yang memerlukan validasi lapangan:
- **$FC_w$ (Lebar Jalur):** 0.90 (Asumsi lebar efektif 3.0 - 3.5 m/lajur di segmen sempit)
- **$FC_{sp}$ (Pemisah Arah):** 1.00 (Tak terbagi, asumsi pemisahan arah 50%-50%)
- **$FC_{sf}$ (Hambatan Samping):** 1.00 (Diasumsikan sangat rendah untuk luar kota tanpa pasar/aktivitas komersial padat di bahu jalan)
- **$FC_{cs}$ (Ukuran Kota):** 1.00 (Jalan antar kota/luar wilayah urban)
