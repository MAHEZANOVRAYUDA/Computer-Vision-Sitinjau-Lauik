# PRD Revisi v3 — Sitinjau Lauik AI Traffic Monitoring System
## Dokumen Tunggal, Menyeluruh, Siap untuk AI Code Editor (Menggantikan v1 & v2)

**Versi:** 3.0 — konsolidasi dan penyempurnaan dari v1.0 dan v2.0
**Tanggal:** 2026-08-30
**Status:** Dokumen ini DIMAKSUDKAN sebagai satu-satunya rujukan aktif. v1 dan v2 tetap disimpan sebagai riwayat audit, tapi AI code editor cukup mengikuti dokumen ini.

---

## 0. Kenapa Dokumen Ini Ditulis Ulang (Bukan Sekadar Ditambah)

Dua PRD sebelumnya (v1, v2) sudah benar mengidentifikasi *apa yang salah* (mkji.py kode mati, gradien diremehkan, dsb), tapi **belum pernah menjelaskan dengan gamblang rumus apa yang SEBENARNYA berjalan di sistem, dari mana asalnya secara ilmiah, dan apakah itu valid**. Itu pertanyaan inti Anda sekarang, dan itu wajar membuat bingung — bahkan setelah dua PRD, pertanyaan "rumus apa yang dipakai" belum terjawab tuntas. Dokumen ini memperbaikinya dengan:

1. Membongkar `sistem_pakar.py` baris-per-konsep, menjelaskan rumus dalam bahasa manusia dan matematika.
2. **Mengidentifikasi kategori ilmiah yang benar** untuk rumus ini (bukan MKJI, tapi bukan berarti tidak valid — ada nama dan literatur sendiri).
3. Meluruskan kalimat "klakson"/"wisatawan lokal" dari laporan ChatGPT — itu karangan, bukan fakta dari kode Anda.
4. Menyusun ulang seluruh roadmap jadi tahapan yang benar-benar bisa dieksekusi AI code editor dari nol sampai layak deployment.

---

## 1. Meluruskan Dulu: Soal Kalimat ChatGPT "Klakson di Kemacetan"

Anda mengutip ini dari laporan ChatGPT:
> *"Jika kecepatan rata-rata ≤15 km/jam, sistem pakar memaksa LOS=F. Logika ini sesuai kebutuhan 'klakson di kemacetan' (wisatawan lokal sering pakai aturan praktis)."*

**Fakta setelah dicek langsung ke kode Anda: kata "klakson" dan "wisatawan lokal" TIDAK ADA di manapun** — bukan di `sistem_pakar.py`, bukan di komentar, bukan di dokumentasi manapun. Itu murni **karangan/interpretasi bebas ChatGPT** untuk "menjelaskan" angka 15 km/jam dengan cerita yang terdengar masuk akal, padahal tidak berdasar apa pun dari kode Anda.

Yang **benar-benar** tertulis di kode (`sistem_pakar.py`, docstring fungsi `klasifikasi_status_hybrid`) sebagai alasan angka 15 km/jam:
> *"ambang_kecepatan_lambat_kmh: Threshold kecepatan untuk override status ke MACET (km/jam)... default 15 km/jam — setara antrean berat."*

Ini rasional teknik lalu lintas yang wajar (kecepatan sangat rendah = indikasi antrean padat), **tapi angka 15 km/jam itu sendiri adalah pilihan default arbiter — tidak dikutip dari studi/observasi lapangan spesifik Sitinjau Lauik**. Ini penting dibedakan:
- **Logikanya (kecepatan rendah → override ke macet) valid secara konsep** — ada dasar ilmiah kuat untuk ini (lihat Bagian 2.3).
- **Angka spesifiknya (15 km/jam) belum divalidasi** dengan data lapangan Sitinjau Lauik — ini murni asumsi awal yang wajar sebagai starting point, sama seperti EMP yang dibahas di PRD sebelumnya.

**Pelajaran untuk Anda:** ini contoh nyata kenapa laporan AI generik (termasuk laporan saya sendiri di masa lalu jika saya tidak hati-hati) tidak boleh dipercaya mentah-mentah untuk hal teknis — selalu minta verifikasi ke kode aktual, bukan cuma ke narasi yang "terdengar masuk akal".

---

## 2. Rumus yang SEBENARNYA Berjalan — Dijelaskan Tuntas

### 2.1 Peta keseluruhan pipeline perhitungan

```
[Kamera A & B] 
    → counting_line.py: hitung kendaraan lintas garis per kelas, per arah, + estimasi kecepatan
    → mqtt_consumer.py: agregasi per interval (default 30 detik), simpan kumulatif masuk/keluar per gerbang
    → occupancy_estimator.py: hitung_occupancy_ruas() = selisih kumulatif Gerbang A masuk − Gerbang B keluar
      (dan sebaliknya) → JUMLAH KENDARAAN RIIL yang sedang berada di ruas jalan saat ini
    → sistem_pakar.py: evaluasi() = ubah jumlah kendaraan riil itu jadi status LANCAR/PADAT/MACET
    → database.py: simpan ke tabel status_ruas
    → api_server.py: tampilkan ke dashboard
```

**mkji.py TIDAK ADA di alur ini sama sekali** — ini yang membuat proyek Anda punya dua "kepribadian" berbeda: yang diklaim di README (MKJI) vs yang benar-benar jalan (occupancy-based custom). Mari bedah dua tahap terakhir yang jadi jantung pertanyaan Anda.

### 2.2 Tahap `occupancy_estimator.py` — INI VALID DAN BAGUS, tidak perlu diragukan

```
Occupancy(arah A→B, kelas) = max(0, Kumulatif_Masuk_Gerbang_A[kelas] − Kumulatif_Keluar_Gerbang_B[kelas])
Occupancy(arah B→A, kelas) = max(0, Kumulatif_Masuk_Gerbang_B[kelas] − Kumulatif_Keluar_Gerbang_A[kelas])
```

**Ini secara matematis dan konseptual benar.** Ini prinsip kekekalan (conservation) paling dasar dalam traffic flow: jika Anda tahu berapa kendaraan MASUK suatu ruas di satu ujung, dan berapa yang sudah KELUAR di ujung lain, selisihnya adalah **jumlah kendaraan yang sedang berada di dalam ruas saat ini** — ini prinsip yang sama dipakai di semua sistem ITS (Intelligent Transportation System) berbasis dua titik pengukuran di dunia, termasuk sistem tol modern. Tidak perlu literatur MKJI untuk memvalidasi ini — ini aritmatika kekekalan massa (conservation of vehicles), bukan model empiris yang perlu kalibrasi rumit.

**Yang perlu divalidasi bukan rumusnya, tapi akurasi INPUT-nya**: apakah `Kumulatif_Masuk_Gerbang_A` dan `Kumulatif_Keluar_Gerbang_B` benar-benar akurat dari deteksi YOLO (soal deteksi motor yang bermasalah, kalibrasi kecepatan, dll — sudah dibahas di PRD v1/v2 Tahap 3-4).

### 2.3 Tahap `sistem_pakar.py` — INI YANG PERLU DILURUSKAN NAMANYA

Rumus intinya:

```
Volume_meter_lajur = Σ (jumlah_kendaraan[kelas] × panjang_fisik_kendaraan[kelas])

KVR (Kapasitas Volumetrik Ruas) = (panjang_ruas × pct_sempit × kapasitas_lateral_sempit) 
                                 + (panjang_ruas × pct_lebar × kapasitas_lateral_lebar)

Persentase_Kepadatan = (Volume_meter_lajur / KVR) × 100%

Status = LANCAR jika Persentase_Kepadatan ≤ 44%
         PADAT  jika 44% < Persentase_Kepadatan ≤ 84%
         MACET  jika Persentase_Kepadatan > 84%
         (di-override jadi MACET jika kecepatan rata-rata < 15 km/jam, terlepas dari persentase)
```

**Nama ilmiah yang benar untuk pendekatan ini: `occupancy-based congestion detection` (deteksi kemacetan berbasis rasio kepadatan/okupansi ruang), BUKAN `V/C ratio MKJI`.**

Ini kategori metodologi berbeda dalam teori aliran lalu lintas (traffic flow theory), dan **kategori ini sah dan punya literatur sendiri**:
- Dasar teorinya: hubungan fundamental `flow = density × speed` (persamaan `q = k·v`, dikenal sebagai **Fundamental Diagram of Traffic Flow**, salah satu konsep paling mapan dalam rekayasa lalu lintas sejak model Greenshields tahun 1935). Dalam kerangka ini, **density (kepadatan)** dan **flow (arus/volume per jam)** adalah dua besaran fisik yang berbeda — rasio Volume/KVR di kode Anda lebih dekat konsepnya ke **density/occupancy ratio**, bukan **V/C ratio** (yang membandingkan dua besaran arus/throughput per jam seperti di MKJI).
- **Occupancy-based congestion detection** adalah metodologi nyata yang dipakai secara luas: loop detector di jalan tol/freeway di banyak negara mengukur "occupancy" (persentase waktu/ruang suatu titik jalan ditempati kendaraan) sebagai indikator kemacetan, sering dianggap **lebih andal** daripada kecepatan saja untuk deteksi dini kemacetan (karena kecepatan bisa turun karena banyak sebab, tapi occupancy tinggi lebih spesifik menandakan kepadatan fisik).
- Riset computer-vision terapan (mis. studi yang memakai kombinasi CNN/YOLO dengan data occupancy dari loop detector untuk melabeli kondisi macet dari citra kamera) mencapai akurasi klasifikasi di atas 90% — ini bukti bahwa pendekatan "hitung kepadatan fisik ruang jalan dari kamera" adalah pendekatan yang **divalidasi secara akademis**, sejalur secara filosofis dengan apa yang dilakukan `sistem_pakar.py` Anda.

**Kesimpulan tegas untuk menjawab keraguan Anda:** rumus `sistem_pakar.py` **BUKAN rumus MKJI, dan tidak akan pernah bisa diklaim sebagai MKJI** — tapi itu **bukan berarti rumus itu salah atau tidak ilmiah**. Itu rumus dari kategori metodologi lain (occupancy/density-based congestion detection) yang sama tuanya dan sama diakuinya dalam rekayasa lalu lintas, hanya beda pendekatan dari MKJI (yang berbasis V/C ratio arus per jam). **Masalah sesungguhnya bukan validitas rumus, tapi PENAMAAN dan KEJUJURAN metodologi** — proyek Anda menyebutnya "MKJI" padahal bukan.

### 2.4 Override kecepatan rendah — kenapa ini valid secara konsep

Menambahkan override "jika kecepatan < X km/jam → paksa MACET" di atas rasio occupancy **adalah pendekatan hybrid yang justru dianjurkan** dalam literatur (lihat kutipan riset di atas: *"Congestion may not be detected by using the speed-based algorithm only... perhaps the optimal speed thresholds are different above a certain occupancy threshold"* — riset transportasi federal AS (Kerner, 2004 dan peneliti lain) secara eksplisit menggabungkan flow rate DAN speed melalui fuzzy logic untuk klasifikasi fase lalu lintas, persis pola yang dilakukan `klasifikasi_status_hybrid()` Anda). Skenario spesifik Sitinjau Lauik (truk mogok di tanjakan = occupancy rendah tapi kecepatan nol) justru **contoh tekstbook** dari kenapa occupancy-only tidak cukup dan speed-override diperlukan.

**Yang perlu diperbaiki bukan konsepnya, tapi:**
1. Angka `15 km/jam` perlu divalidasi dengan data kecepatan riil Sitinjau Lauik (lihat Tahap 3 di Bagian 4), bukan cuma default arbiter.
2. Ambang ini seharusnya **berbeda untuk arah naik vs turun** (lihat PRD v2 Bagian 3.3) — kecepatan 15 km/jam di tanjakan curam adalah hal yang jauh lebih umum/normal (truk memang pelan menanjak) dibanding kecepatan 15 km/jam di jalan datar (itu jelas tanda antrean).

---

## 3. Ringkasan: Apa yang Valid, Apa yang Perlu Diperbaiki, Apa yang Perlu Diubah Namanya

| Komponen | Status Ilmiah | Tindakan |
|---|---|---|
| `hitung_occupancy_ruas()` (selisih kumulatif dual-gerbang) | **Valid** — prinsip kekekalan kendaraan, tidak perlu literatur khusus, secara matematis benar | Tidak perlu diubah rumusnya. Fokus ke akurasi input (deteksi YOLO). |
| Rasio Volume/KVR ("persentase kepadatan") | **Valid sebagai kategori occupancy-based congestion detection**, TAPI **bukan MKJI/V-C ratio** | Ganti semua penamaan "sesuai MKJI" jadi "pendekatan occupancy-based, diadaptasi dari data lapangan". Tidak perlu ubah rumus. |
| Ambang 44%/84% (breakpoint LANCAR/PADAT/MACET) | Meniru breakpoint LOS MKJI (yang berbasis V/C, bukan occupancy) — **secara konsep tidak otomatis valid untuk skala occupancy**, karena occupancy ratio dan V/C ratio punya kurva/perilaku berbeda dalam Fundamental Diagram | Perlu divalidasi ulang dengan data lapangan (lihat Tahap 3): apakah 44%/84% occupancy benar-benar berkorelasi dengan kondisi lancar/padat/macet yang diamati langsung di lapangan, atau perlu dikalibrasi ulang. |
| Override kecepatan < 15 km/jam → MACET | **Valid secara konsep** (hybrid flow+speed adalah praktik yang dianjurkan literatur) | Angka 15 km/jam perlu divalidasi, dan idealnya dibedakan naik/turun (lihat PRD v2). |
| `mkji.py` (implementasi MKJI resmi) | Valid secara struktur MKJI, tapi **kode mati**, dan MKJI standar tidak dirancang untuk gradien 26% (lihat PRD v2 Bagian 3.1) | Hubungkan sebagai metrik pembanding paralel (lihat Bagian 4, Tahap 1). |
| Kalimat "klakson"/"wisatawan lokal" dari laporan ChatGPT | **Tidak ada di kode Anda — murni karangan** | Abaikan sepenuhnya, jangan dikutip di laporan/skripsi Anda. |

---

## 4. Roadmap Deployment — Bertahap, dari Nol Sampai Layak Produksi

> **Instruksi untuk AI code editor:** kerjakan berurutan. Setiap tahap punya Definition of Done (DoD) — jangan lanjut ke tahap berikutnya sebelum DoD terpenuhi dan `pytest tests/` lulus semua.

### TAHAP 0 — Persiapan & Baseline

- [ ] Jalankan `pytest tests/ -v`, simpan hasil sebagai `docs/BASELINE_TEST_SEBELUM_REVISI.txt`.
- [ ] Buat branch `revisi/rumus-dan-metodologi` dari branch aktif.
- [ ] Backup seluruh `config/*.yaml` ke `config/backup_sebelum_revisi/`.

**DoD:** Baseline tercatat, branch dan backup dibuat.

---

### TAHAP 1 — Luruskan Penamaan & Metodologi (PALING PRIORITAS, kerjakan sebelum apapun lain)

Tujuan: sistem tetap pakai rumus yang **sudah ada dan sudah valid** (occupancy-based), tapi semua dokumentasi jujur soal apa itu.

- [ ] **Ganti semua kalimat "sesuai MKJI 1997" atau "metodologi MKJI"** di `README.md`, `docs/PARAMETER_MKJI.md`, dan komentar kode manapun yang merujuk ke `sistem_pakar.py`, menjadi:
  > *"Pendekatan Occupancy-Based Congestion Detection: status kemacetan dihitung dari rasio kepadatan kendaraan riil di ruas jalan (occupancy ratio) terhadap kapasitas volumetrik ruas (KVR), dikombinasikan dengan indikator kecepatan rata-rata (speed override) untuk menangkap kondisi bottleneck event-driven (mis. kendaraan mogok). Pendekatan ini termasuk kategori metodologi occupancy/density-based dalam teori aliran lalu lintas (traffic flow theory), BERBEDA dari pendekatan V/C ratio Manual Kapasitas Jalan Indonesia (MKJI) 1997 yang berbasis rasio arus (flow) per jam. MKJI 1997 dihitung secara paralel sebagai metrik pembanding (lihat bagian [X])."*
- [ ] **Ganti nama file/fungsi supaya tidak menyesatkan** (opsional tapi direkomendasikan untuk kejelasan jangka panjang): pertimbangkan rename `docs/PARAMETER_MKJI.md` → `docs/METODOLOGI_PERHITUNGAN.md`, dengan dua bagian jelas: "Bagian A: Occupancy-Based (Metrik Utama, yang benar-benar dipakai sistem)" dan "Bagian B: MKJI 1997 (Metrik Pembanding)".
- [ ] **Hubungkan `mkji.py` sebagai metrik pembanding paralel** (bukan pengganti):
  - Panggil `mkji.evaluasi_mkji()` di `mqtt_consumer.py` **setelah** `sistem_pakar.evaluasi()`, dengan input yang sama (jumlah kendaraan per kelas dari `occupancy_estimator`).
  - Simpan hasilnya ke kolom baru di tabel `status_ruas`: `mkji_vc_ratio`, `mkji_los` (terpisah dari kolom `rasio_vc`/`level_of_service` yang sudah ada, yang sekarang jelas berarti occupancy-based).
  - Tampilkan di dashboard sebagai info sekunder: *"Estimasi V/C MKJI (indikatif, medan gunung standar — CATATAN: gradien Sitinjau Lauik 20-26% melebihi cakupan normal MKJI, gunakan dengan hati-hati)"*.
- [ ] Tambahkan test baru `test_perbandingan_metodologi.py` yang menjalankan kedua metode (occupancy-based dan MKJI) dengan data sintetis yang sama dan mendokumentasikan **seberapa jauh keduanya berbeda** — ini data yang sangat berharga untuk laporan/skripsi Anda (perbandingan dua pendekatan adalah temuan akademis yang solid).

**DoD Tahap 1:**
- [ ] Tidak ada satu pun klaim "sesuai MKJI" tersisa untuk metrik yang benar-benar dipakai sebagai status utama.
- [ ] `mkji.py` terpanggil nyata, hasilnya tersimpan dan tertampil sebagai metrik kedua.
- [ ] Ada dokumentasi jelas (di README atau file baru) yang menjelaskan DUA metodologi berbeda dan kenapa keduanya ada.
- [ ] Semua test lama tetap lulus, ditambah test baru perbandingan metodologi.

---

### TAHAP 2 — Validasi Ambang & Parameter dengan Data Lapangan

Ini tahap paling penting untuk klaim "valid secara ilmiah" — rumus sudah benar strukturnya (Tahap 1), sekarang **angka-angkanya** perlu bukti empiris, bukan cuma asumsi:

- [ ] **Kumpulkan video sampel** (5-8 video, 15-20 menit tiap video, mencakup jam sepi/jam ramai, arah naik/turun terpisah) dari kedua gerbang — ini sudah disebut di PRD v1/v2, sekarang tujuannya lebih spesifik.
- [ ] **Hitung manual ground truth**: untuk setiap video, catat (a) jumlah kendaraan per kelas yang lewat, (b) kondisi lalu lintas yang **diamati langsung secara visual/subjektif** oleh Anda sebagai observer manusia (lancar/padat/macet — anggap ini "label manusia").
- [ ] **Bandingkan label manusia dengan output sistem** (persentase occupancy dari `sistem_pakar.py`) untuk video yang sama. Ini yang disebut **validasi kalibrasi ambang** — cari tahu, secara empiris, di persentase occupancy berapa manusia benar-benar mulai menyebut kondisi "padat" dan "macet" di Sitinjau Lauik.
- [ ] **Uji apakah ambang 44%/84% cocok** dengan hasil observasi di atas. Jika tidak cocok (mis. ternyata manusia sudah menyebut "macet" di occupancy 60%, bukan 84%), **kalibrasi ulang** `ambang_lancar`/`ambang_padat` di `config.yaml` berdasarkan data ini — bukan sekadar meniru breakpoint MKJI 44%/84% yang berasal dari konteks V/C ratio berbeda.
- [ ] **Validasi ambang kecepatan 15 km/jam** dengan cara serupa: amati kecepatan riil kendaraan saat kondisi benar-benar tersendat vs kondisi normal-tapi-pelan-karena-tanjakan, pisahkan data untuk arah naik dan turun.
- [ ] Dokumentasikan semua hasil di `docs/HASIL_VALIDASI_LAPANGAN.md` dengan format: video, jumlah kendaraan per kelas, occupancy % hasil sistem, label manusia, kesesuaian (ya/tidak), catatan.

**DoD Tahap 2:**
- [ ] Ada minimal 5 sesi video tervalidasi dengan perbandingan label manusia vs output sistem.
- [ ] Ambang `ambang_lancar`, `ambang_padat`, `ambang_kecepatan_lambat_kmh` di config sudah diperbarui berdasarkan data (atau didokumentasikan secara eksplisit kenapa angka lama dipertahankan, dengan bukti pendukung).
- [ ] `docs/HASIL_VALIDASI_LAPANGAN.md` berisi data konkret, bukan asumsi.

---

### TAHAP 3 — Kalibrasi Kelandaian Khusus (Arah Naik/Turun) — dari PRD v2, tetap berlaku

- [ ] Tambahkan field `arah_topografi` (`naik`/`turun`) ke `counting_lines` di `config.yaml`, terpisah dari field `arah` (`masuk`/`keluar`) yang sudah ada.
- [ ] Hitung dan simpan kecepatan rata-rata terpisah per arah topografi.
- [ ] Update skema database: tambah kolom `arah_topografi` di tabel `hitungan_kendaraan`.
- [ ] Sebagai bagian dari Tahap 2 di atas, validasi ambang kecepatan **terpisah** untuk naik vs turun (kemungkinan besar ambang untuk "turun" harus lebih tinggi karena risiko lebih ke insiden daripada macet — lihat PRD v2 Bagian 3.3 soal pola rem blong ODOL di turunan).
- [ ] Dokumentasikan keterbatasan jujur: sistem ini **congestion monitor**, bukan **crash-risk predictor** — jangan overclaim kemampuan deteksi risiko kecelakaan di laporan/skripsi.

**DoD Tahap 3:**
- [ ] Data kecepatan tersimpan dan bisa dianalisis terpisah per arah topografi.
- [ ] Ambang kecepatan (jika berbeda naik/turun) terdokumentasi dengan justifikasi data.

---

### TAHAP 4 — Hardening Keamanan Dasar (dari PRD v1, tetap berlaku tanpa perubahan)

- [ ] CORS: ganti `allow_origins=["*"]` jadi daftar eksplisit.
- [ ] Tambah API key sederhana untuk endpoint sensitif.
- [ ] Cek `mosquitto.conf` — pastikan tidak `allow_anonymous true` untuk deployment lapangan.
- [ ] Tambah `.env.example`, pastikan `.env` asli tidak pernah ter-commit ke git.

**DoD:** CORS tidak wildcard, ada auth minimal, `.env.example` ada, `.env` asli aman.

---

### TAHAP 5 — Perbaikan Deteksi Motor (dari PRD v1, tetap berlaku tanpa perubahan)

- [ ] Uji `confidence_threshold` khusus kelas motor.
- [ ] Evaluasi migrasi ke YOLO11 (nama resmi tanpa huruf "v") dengan modul C2PSA untuk objek kecil.
- [ ] Jalankan `scripts/fine_tune.py` dengan data lokal dari Tahap 2 (video sampel yang sudah dikumpulkan).
- [ ] Dokumentasikan precision/recall sebelum/sesudah.

**DoD:** Recall motor terukur dan terdokumentasi (target realistis, bukan janji sempurna sebelum diuji).

---

### TAHAP 6 — Migrasi Frontend Ringan (dari PRD v1, tetap berlaku tanpa perubahan)

- [ ] Bundle Chart.js lokal (hilangkan dependency CDN).
- [ ] Tambah Alpine.js untuk reaktivitas real-time (bukan React — lihat justifikasi di PRD v1 Bagian 2).
- [ ] Tambah responsivitas mobile dasar.
- [ ] Tambah penanganan visual untuk kegagalan WebSocket.

**DoD:** Dashboard tetap fungsional identik, total ukuran JS jauh lebih kecil dari alternatif React.

---

### TAHAP 7 — Persiapan Deployment Edge (dari PRD v1, tetap berlaku tanpa perubahan)

- [ ] Uji konversi YOLOv8n/YOLO11n → TFLite → Edge TPU **sebelum** membeli/mengonfigurasi Coral secara penuh, ukur persentase fallback ke CPU.
- [ ] Ukur FPS riil CPU-only di Raspberry Pi 5 sebagai baseline.
- [ ] Aktifkan `watchdog.py` di `main.py`.
- [ ] Setup backup database otomatis (`pg_dump` cron harian).
- [ ] CI dasar (GitHub Actions): `pytest` + linting saja — **jangan** loncat ke Kubernetes/Docker Swarm.

**DoD:** Ada catatan terukur FPS dan efisiensi akselerator, watchdog aktif, CI jalan di setiap push.

---

## 5. Definisi "Siap untuk Deployment" — Kriteria Konkret

Sistem dianggap **layak deployment** (untuk demo Dishub / publikasi akademis) ketika SEMUA berikut terpenuhi:

1. **Metodologi jujur dan konsisten**: tidak ada klaim "MKJI" untuk sesuatu yang bukan MKJI. Occupancy-based diberi nama yang benar dan dijustifikasi dengan literatur (Bagian 2.3 dokumen ini).
2. **Ambang tervalidasi data, bukan asumsi**: `ambang_lancar`, `ambang_padat`, `ambang_kecepatan_lambat_kmh` (termasuk versi naik/turun) sudah dibandingkan dengan observasi manusia riil di lapangan (Tahap 2).
3. **Akurasi deteksi terukur**: precision/recall per kelas kendaraan (termasuk motor) terdokumentasi dengan angka, bukan klaim kualitatif ("deteksi bagus").
4. **Keamanan dasar terpenuhi**: tidak ada CORS wildcard, ada auth minimal, kredensial tidak ter-commit ke git (Tahap 4).
5. **Stabilitas operasional**: sistem sudah diuji berjalan kontinu (idealnya ≥48 jam tanpa crash) dengan recovery state yang benar saat restart (ini sudah terpenuhi berdasarkan audit kode — `recover_state()` sudah berfungsi).
6. **Keterbatasan didokumentasikan secara eksplisit**: laporan/skripsi/demo menyebutkan dengan jelas bahwa sistem adalah congestion monitor (bukan crash predictor), gradien Sitinjau Lauik di luar cakupan normal MKJI, dan ODOL tidak terdeteksi langsung dari video.

**Sistem TIDAK PERLU** (dan sebaiknya tidak diklaim) sebagai:
- Sistem prediksi kecelakaan.
- Implementasi MKJI 1997 murni.
- Sistem yang tervalidasi untuk keselamatan kritis (safety-critical).

Kejujuran soal batas-batas ini, dijelaskan dengan bahasa yang percaya diri (bukan minta maaf), adalah yang membuat laporan/skripsi/demo ke Dishub **lebih kredibel**, bukan kurang.

---

## 6. Sumber Riset (Konsolidasi dari v1, v2, dan Riset Baru untuk Rumus)

- Greenshields, B.D. (1935) dan literatur turunannya — **Fundamental Diagram of Traffic Flow**, hubungan `flow = density × speed`, dasar pembeda konsep density/occupancy vs flow/V-C ratio.
- Riset federal transportasi AS (ROSAP/DOT) soal loop detector occupancy-based congestion detection, termasuk kutipan Kerner (2004) soal kombinasi flow+speed via fuzzy logic untuk klasifikasi fase lalu lintas — dasar pembenaran ilmiah untuk pendekatan hybrid occupancy+speed override yang dipakai `sistem_pakar.py`.
- Survei ScienceDirect "Applications of deep learning in congestion detection" — bukti empiris bahwa pendekatan occupancy-based (dikombinasikan CV/YOLO) mencapai akurasi >90% untuk klasifikasi kemacetan, memvalidasi kelayakan filosofi pendekatan proyek Anda.
- Sumber MKJI/PKJI, geometrik Sitinjau Lauik, dan data kecelakaan — sama seperti PRD v2 Bagian 6 (tidak diulang di sini).

---

## 7. Catatan Penutup untuk AI Code Editor

Kabar baik dari analisis mendalam ini: **rumus inti sistem Anda (occupancy-based congestion detection) sudah punya dasar ilmiah yang valid dan kuat** — Anda tidak perlu membongkar ulang logika perhitungan dari nol. Yang selama ini membuat bingung dan meragukan bukan rumusnya, tapi **penamaan yang salah** (mengklaimnya sebagai MKJI padahal bukan) dan **ambang yang belum divalidasi data lapangan**. Kerjakan Tahap 1 (penamaan jujur) dan Tahap 2 (validasi ambang) sebagai prioritas mutlak sebelum tahap lain — begitu dua ini selesai, Anda punya sistem yang bisa dipertanggungjawabkan secara ilmiah tanpa harus menulis ulang satu baris pun dari logika inti yang sudah ada.
