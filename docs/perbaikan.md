# PRD v4 — Perbaikan Dashboard, Halaman Monitoring Gerbang, dan Arsitektur Ringan
## Sitinjau Lauik AI Traffic Monitoring System

**Versi:** 4.1 — menambahkan Fase 6 (performa edge & backend, opsional) hasil audit lanjutan
**Tanggal:** 2026-08-31
**Status:** Dokumen aktif untuk dieksekusi oleh AI code editor (Antigravity), bertahap per Fase. Melengkapi, bukan menggantikan, `PRD_REVISI_SITINJAU_LAUIK_v3.md` (v3 = kebenaran ilmiah rumus; v4 = UI/UX, arsitektur halaman, endpoint baru, dan performa edge/backend).
**Cara pakai dokumen ini:** Kerjakan Fase 1 → validasi → Fase 2 → dst. Jangan lompat fase. Setiap fase punya "Definisi Selesai" (Definition of Done) yang bisa dicek objektif.

---

## 0. Ringkasan Masalah (Baseline Audit)

Berdasarkan pemeriksaan langsung terhadap `dashboard/index.html`, `src/api_server.py`, `src/mqtt_consumer.py`, `src/database.py`, dan `src/sistem_pakar.py` per 2026-08-31, kondisi nyata sistem:

| # | Temuan | File terkait | Dampak |
|---|--------|--------------|--------|
| 1 | Angka "% kapasitas terpakai" **sudah dihitung** di backend (`hasil.rasio_vc` = persentase_kepadatan/100, lihat `sistem_pakar.py` baris ~250-273) tapi **tidak pernah ditampilkan sebagai teks kapasitas** di panel status utama. Yang tampil di panel kiri cuma ring LANCAR/PADAT/MACET tanpa angka. | `dashboard/index.html` (panel `status-utama`) | User tidak tahu seberapa dekat ke ambang padat/macet hanya dari lihat panel kiri — harus geser mata ke metric card lain. |
| 2 | `status-ring` (lingkaran di sekitar tulisan LANCAR/PADAT/MACET) warnanya **hanya mengikuti class CSS** (`.lancar`, `.padat`, `.macet` — 3 warna diskrit tetap), **tidak mengikuti gradasi persentase kapasitas riil**. Contoh: 1% dan 43% sama-sama tampak "hijau penuh" padahal beda jauh. | `dashboard/index.html` CSS `.status-ring` | Tidak ada indikasi visual seberapa dekat ke ambang berikutnya. |
| 3 | Section "Aktivitas Kendaraan (5 Menit Terakhir)" (`kendaraan-grid`) hanya menampilkan **1 angka gabungan** per jenis kendaraan (total masuk+keluar 5 menit gabungan Gerbang A dan B), dari `db.ambil_hitungan_terbaru(menit_terakhir=5)` di `api_server.py` baris ~193-197. **Tidak ada breakdown masuk vs keluar, tidak ada breakdown per gerbang, dan window 5 menit terlalu sempit untuk representasi harian.** | `api_server.py` `_build_status_response()`, `dashboard/index.html` | Angka ini turun ke 0 setiap kali tidak ada kendaraan lewat dalam 5 menit terakhir — membingungkan dan tidak informatif dibanding kebutuhan riil (lihat gambar referensi: total masuk hari ini + in/out per jenis). |
| 4 | Data mentah kumulatif masuk/keluar per gerbang per kelas kendaraan **sudah ada dan sudah dihitung** di `mqtt_consumer.py` (`self.kumulatif_a_masuk`, `kumulatif_a_keluar`, `kumulatif_b_masuk`, `kumulatif_b_keluar` — in-memory) dan bisa diambil dari DB lewat `db.ambil_kumulatif_masuk_keluar_per_gerbang()` — **tapi endpoint API ini tidak pernah dipanggil oleh dashboard, hanya dipakai internal untuk recovery state saat restart.** | `src/mqtt_consumer.py`, `src/database.py` | Data yang dibutuhkan untuk fitur "kendaraan per jenis + masuk/keluar" **sudah tersedia di backend**, ini murni pekerjaan expose-ke-API + render UI, bukan membangun fitur dari nol. |
| 5 | Kedua live camera feed (`Gerbang A` dan `Gerbang B`) **selalu di-render langsung di dashboard utama** (`<img src=".../video_feed">` di `camera-grid`, dashboard/index.html baris ~979-988), masing-masing adalah stream MJPEG kontinu yang dimuat browser terus-menerus. | `dashboard/index.html` | Ini beban terbesar untuk performa: 2 stream video MJPEG aktif setiap kali dashboard dibuka, walau user cuma butuh lihat angka. Menyebabkan dashboard terasa berat/lambat, terutama di koneksi terbatas atau saat demo ke Dishub via proyektor/HP. |
| 6 | Dashboard produksi tidak punya mode "developer/kalibrasi" terpisah — semua kalibrasi garis, reset counter, dan debug tracking (seperti contoh gambar referensi teman: kalibrasi garis, arah IN, klasifikasi live per kelas, track aktif) **tidak ada sama sekali** di sistem Anda saat ini. Ini murni fitur baru, bukan bug. | (tidak ada file) | Anda harus kalibrasi garis counting secara manual (edit YAML lalu restart), tidak ada visual/live-feedback saat kalibrasi. |
| 7 | Tidak ditemukan bug fungsional kritis lain di alur inti (occupancy, sistem pakar) — itu sudah divalidasi benar di PRD v3. Fokus v4 murni di lapisan presentasi (dashboard) dan arsitektur pemisahan halaman. | - | - |

**Kesimpulan kunci:** Permintaan Anda **tidak butuh perombakan backend besar**. Backend sudah menyimpan data yang tepat. Pekerjaan utama adalah: (a) menambah 1-2 endpoint API baru yang mengekspos data yang sudah ada, (b) memecah 1 file `dashboard/index.html` monolitik jadi 3 halaman ringan terpisah, dan (c) membangun halaman kalibrasi/debug baru (fitur benar-benar baru, terinspirasi gambar 2).

---

## 1. Keputusan Arsitektur (Baca Sebelum Eksekusi)

### 1.1 Kenapa dashboard terasa berat, dan cara memperbaikinya

Penyebab utama dashboard "berat" itu **stream MJPEG ganda yang selalu aktif**, bukan jumlah data JSON (data status/riwayat sangat kecil, <5 KB). Solusi yang benar bukan "menghapus fitur video", tapi **lazy-load**: video hanya dimuat saat halaman kamera dibuka, bukan saat dashboard ringkasan dibuka.

### 1.2 Struktur halaman baru (menggantikan 1 file monolitik)

```
dashboard/
├── index.html          → DASHBOARD RINGKASAN (default landing page)
│                          - TIDAK ada <img src="video_feed"> sama sekali
│                          - Hanya angka, status, grafik, tombol navigasi
│                          - Polling/WebSocket tetap jalan (ringan, cuma JSON)
│
├── gerbang.html         → HALAMAN LIVE CAMERA (1 halaman, dipakai utk Gerbang A & B)
│                          - Parameter URL ?gerbang=a atau ?gerbang=b
│                          - Video feed HANYA dimuat di halaman ini
│                          - Tombol "← Kembali ke Dashboard" jelas di atas
│
├── kalibrasi.html        → HALAMAN DEV/KALIBRASI (setara gambar referensi 2)
│                          - Untuk Anda sendiri (bukan demo Dishub), bisa dikunci
│                            di belakang parameter ?dev=1 atau tombol tersembunyi
│                          - Video feed + overlay kalibrasi HANYA dimuat di sini
│
├── shared.js             → Fungsi umum dipakai bersama (fetch status, format angka,
│                            koneksi WebSocket) supaya tidak duplikasi kode 3x
├── shared.css            → Variabel warna, komponen umum (card, badge, tombol)
├── vendor/                → (sudah ada, tidak berubah)
├── PU1.png, logo-upi...   → (sudah ada, tidak berubah)
```

**Alasan teknis kenapa ini membuat sistem lebih ringan:**
- Halaman ringkasan (`index.html`) yang paling sering dibuka/di-refresh tidak lagi menanggung beban decode video MJPEG di browser.
- Setiap kali Dishub atau siapa pun membuka dashboard untuk sekadar cek status, mereka tidak lagi menunggu 2 stream video termuat duluan.
- Halaman kamera hanya dibuka saat memang dibutuhkan (operator ingin verifikasi visual).
- Ini pola arsitektur "progressive disclosure" — standar dalam desain dashboard monitoring produksi (mis. Grafana: panel ringkasan ringan, drill-down baru berat).

### 1.3 Prinsip desain status ring (kapasitas terpakai + warna dinamis)

Meniru gambar referensi 1 tapi disesuaikan dengan istilah ilmiah proyek Anda sendiri (occupancy-based, bukan MKJI — sesuai PRD v3):

```
Contoh tampilan target:
┌─────────────────────────────┐
│         [ RING WARNA ]       │
│           LANCAR             │
│  ▓░░░░░░░░░░░░░░░░░░░░░░░░  │  ← progress bar tipis di bawah ring
│  1.1% kapasitas terpakai      │
│  597 / 56.100 meter-lajur     │
└─────────────────────────────┘
```

Field yang dibutuhkan **sudah ada semua** dari `/api/status-terkini` saat ini:
- `data.rasio_vc` → dikali 100 = persen kapasitas terpakai
- `data.volume_smp` → **perlu dicek**: apakah field ini menyimpan `volume_meter_lajur` (pembilang) dalam satuan meter-lajur? Lihat Fase 1 langkah verifikasi.
- Kapasitas (`kapasitas_meter_lajur`, penyebut) → **belum diekspos di API**, harus ditambahkan (Fase 1).

Warna ring: interpolasi halus (bukan lompatan 3-warna) berbasis `rasio_vc`, dengan breakpoint tetap mengacu ambang yang sudah ada (`ambang_lancar=44%`, `ambang_padat=84%`) sebagai titik acuan warna, bukan sebagai satu-satunya penentu (supaya user bisa lihat "mendekati padat" walau masih di zona hijau).

---

## FASE 1 — Backend: Expose Data yang Sudah Ada (tanpa mengubah rumus)

**Tujuan:** Menyediakan field API baru yang dibutuhkan UI, tanpa menyentuh `sistem_pakar.py` atau `occupancy_estimator.py` (rumus sudah divalidasi benar di PRD v3, jangan diubah).

### 1.1 Tambahkan endpoint `/api/kendaraan-per-jenis`

File: `src/api_server.py`

Endpoint baru yang mengembalikan breakdown lengkap: total masuk & keluar per jenis kendaraan, per gerbang, akumulasi HARI INI (bukan 5 menit). Sumber data: `db.ambil_kumulatif_masuk_keluar_per_gerbang(sejak_jam=24)` — fungsi ini **sudah ada** di `database.py`, tinggal dipanggil dari endpoint HTTP baru (saat ini hanya dipanggil `mqtt_consumer.py` untuk recovery internal).

Kontrak response yang diharapkan dashboard:
```json
{
  "per_gerbang": {
    "gerbang_a": {
      "motor": {"masuk": 70, "keluar": 40},
      "mobil": {"masuk": 371, "keluar": 146},
      "bus":   {"masuk": 45,  "keluar": 36},
      "truck": {"masuk": 65,  "keluar": 77}
    },
    "gerbang_b": { "...": "struktur sama" }
  },
  "total_gabungan": {
    "motor": {"masuk": 130, "keluar": 90},
    "mobil": {"masuk": 700, "keluar": 650},
    "bus":   {"masuk": 80,  "keluar": 70},
    "truck": {"masuk": 120, "keluar": 140}
  },
  "total_masuk_hari_ini": 551,
  "sejak_jam": 24
}
```

Catatan penamaan kelas: cek konsistensi `truck` vs `truk` di seluruh kode (`sistem_pakar.py` pakai `truk`, tapi perlu dikonfirmasi konsisten dari `panjang_kendaraan` config dan hasil YOLO). **Jangan mengubah nama kelas di database/MQTT** — cukup pastikan endpoint baru pakai nama kelas yang sama persis dengan yang tersimpan, dan dashboard menerjemahkan ke label tampilan Indonesia (`truck`→"Truck", `mobil`→"Mobil", dst) di sisi frontend saja.

### 1.2 Tambahkan field kapasitas absolut ke `/api/status-terkini`

File: `src/api_server.py`, fungsi `_build_status_response()`

Tambahkan ke `status_dict` sebelum return:
```python
status_dict["kapasitas_meter_lajur"] = float(config.get("kapasitas_meter_lajur_computed") or config.get("sistem_pakar.kapasitas_meter_lajur", 56100))
```
(pola pengambilan sama persis seperti di `mqtt_consumer.py` baris 71 — pakai konfigurasi yang identik, supaya angka penyebut yang ditampilkan di dashboard SELALU sinkron dengan angka yang benar-benar dipakai sistem pakar untuk klasifikasi, tidak ada risiko dua sumber kebenaran berbeda).

Verifikasi wajib sebelum lanjut: cek kolom `volume_smp` di tabel `status_ruas` — apakah ini benar-benar `volume_meter_lajur` (pembilang rasio_vc) dalam satuan meter-lajur, ATAU field lama peninggalan versi MKJI (unit smp berbeda)? Baca `src/sistem_pakar.py` fungsi `evaluasi()` untuk konfirmasi nilai apa yang dikirim ke parameter itu saat `db.simpan_status_ruas()` dipanggil di `mqtt_consumer.py`. **Jika ambigu/campur unit, JANGAN paksa dipakai** — tambahkan field baru yang jelas namanya (`volume_meter_lajur_terpakai`) daripada menimpa makna field lama yang mungkin masih dipakai kode lain.

### 1.3 Endpoint status kamera tetap terpisah dari data feed video

`/api/gerbang-status` (sudah ada) tetap dipakai apa adanya untuk indikator status (aktif/nonaktif) di dashboard ringkasan. Yang berubah hanya: dashboard ringkasan **tidak lagi meminta URL video_feed sama sekali** — itu baru diminta oleh `gerbang.html` saat halaman itu dibuka.

### 1.4 Definisi Selesai Fase 1
- [ ] `GET /api/kendaraan-per-jenis` mengembalikan data sesuai kontrak di atas, teruji manual via browser/curl.
- [ ] `GET /api/status-terkini` mengembalikan field baru `kapasitas_meter_lajur` dengan nilai identik dengan yang dipakai `mqtt_consumer.py` untuk evaluasi status saat ini (cross-check log `[Pakar] Status: ... | Kepadatan: X%` vs `rasio_vc * 100` dari API — harus sama persis).
- [ ] Ambiguitas field `volume_smp` sudah diperiksa dan didokumentasikan (komentar kode atau catatan singkat di PRD ini), tidak dibiarkan menebak.
- [ ] Tidak ada perubahan pada `sistem_pakar.py`, `occupancy_estimator.py`, `mkji.py` (rumus tidak disentuh).
- [ ] Test otomatis baru ditambahkan di `tests/` untuk endpoint `/api/kendaraan-per-jenis` (minimal: response 200, struktur JSON sesuai kontrak, jumlah masuk-keluar tidak negatif).

---

## FASE 2 — Dashboard Ringkasan Baru (`index.html`)

**Tujuan:** Bangun ulang panel status utama + section kendaraan, hapus video feed dari halaman ini, dan tambahkan 2 tombol navigasi ke halaman gerbang.

### 2.1 Panel status utama (kiri) — tambahkan info kapasitas

Di dalam `.status-ring-container`, tambahkan di bawah teks LANCAR/PADAT/MACET:
- Baris progress bar tipis (mirip contoh gambar 1) menunjukkan `rasio_vc * 100`%, lebar bar = persentase, dibatasi maksimum visual 100% meski rasio bisa >100% (tampilkan angka aslinya di teks meski bar penuh).
- Teks kecil: `"X.X% kapasitas terpakai — [volume] / [kapasitas] meter-lajur"` menggunakan field baru dari Fase 1.2. Format angka pakai pemisah ribuan gaya Indonesia (titik, bukan koma): `597 / 56.100`.

### 2.2 Status ring — warna gradasi dinamis

Ganti logika warna ring dari 3 kelas CSS statis menjadi interpolasi warna berbasis `rasio_vc` real-time:
- 0% → hijau (`--lancar`)
- mendekati `ambang_lancar` (44%) → transisi hijau ke kuning (`--padat`)
- mendekati `ambang_padat` (84%) → transisi kuning ke merah (`--macet`)
- di atas 84% → merah penuh, makin gelap/pekat jika jauh melebihi 100%

Implementasi: fungsi JS kecil `interpolasiWarnaKapasitas(persen, ambangLancar, ambangPadat)` yang mengembalikan nilai hex/CSS color, diterapkan ke `border-color` ring dan warna teks status secara dinamis lewat `element.style.setProperty`. Ambang (`ambangLancar`, `ambangPadat`) idealnya diambil dari API (bukan hardcode di JS), supaya jika suatu saat parameter di `config.yaml` diubah, dashboard otomatis ikut menyesuaikan tanpa perlu edit HTML.

### 2.3 Ganti section "Aktivitas Kendaraan (5 Menit Terakhir)" → "Kendaraan Per Jenis (Hari Ini)"

Struktur baru per kartu jenis kendaraan (4 kartu: Motor, Mobil, Bus, Truck), tiap kartu menampilkan:
```
┌───────────────────────┐
│ 🏍️  MOTOR              │
│                        │
│  Masuk: 70   Keluar: 40│
│  (di ruas sekarang: 30)│  ← masuk-keluar, dihitung di frontend
└───────────────────────┘
```
Data diambil dari `total_gabungan` hasil endpoint `/api/kendaraan-per-jenis` (Fase 1.1). Tambahkan juga total gabungan besar di atas 4 kartu ini: `"Total Masuk Hari Ini: 551"` (mengacu `total_masuk_hari_ini`), meniru posisi metric card "TOTAL MASUK HARI INI" di gambar referensi 1.

Refresh interval: tiap 30-60 detik cukup (data ini kumulatif harian, tidak perlu real-time detik demi detik seperti status utama).

### 2.4 Hapus blok `camera-grid` dari `index.html`, ganti dengan 2 tombol navigasi

Ganti seluruh blok `<div id="camera-grid">...</div>` dan fungsi `fetchGerbangStatus()` bagian render video, dengan:
- Card ringkas "Status Kamera" menampilkan HANYA badge aktif/nonaktif tiap gerbang (teks, bukan video) — pakai data yang sudah ada dari `/api/gerbang-status`.
- 2 tombol besar jelas: `[📹 Lihat Gerbang A — Jl. Padang Basi]` dan `[📹 Lihat Gerbang B — Jembatan Timbang Oto]`, masing-masing link ke `gerbang.html?gerbang=a` dan `gerbang.html?gerbang=b`.
- Jika gerbang berstatus nonaktif, tombol tetap ada tapi diberi label "(Offline)" dan style redup — tidak disembunyikan total (supaya user tahu gerbang itu ada tapi sedang mati, bukan tidak pernah ada).

### 2.5 Definisi Selesai Fase 2
- [ ] `index.html` TIDAK mengandung tag `<img>` yang menunjuk ke `video_feed` di manapun.
- [ ] Panel status kiri menampilkan teks persentase + pecahan meter-lajur, sinkron dengan metric card "Rasio kepadatan occupancy" yang sudah ada (dua tempat ini menampilkan angka yang sama, cuma beda format tampilan — tidak boleh terlihat kontradiktif).
- [ ] Ring berubah warna secara halus (bukan lompat 3 warna) sesuai `rasio_vc`.
- [ ] Section kendaraan menunjukkan masuk & keluar terpisah per jenis, bersumber dari endpoint baru.
- [ ] 2 tombol navigasi ke halaman gerbang berfungsi dan terlihat jelas.
- [ ] Diukur manual: waktu dari buka `index.html` sampai seluruh konten ringkasan tampil (network tab browser) — harus terasa lebih cepat dibanding versi lama (baseline: catat waktu load versi lama sebelum mulai Fase 2, bandingkan sesudah).

---

## FASE 3 — Halaman Live Camera Terpisah (`gerbang.html`)

**Tujuan:** Satu halaman dipakai untuk kedua gerbang, video HANYA dimuat di sini.

### 3.1 Struktur halaman

- Baca parameter URL `?gerbang=a` atau `?gerbang=b` (default `a` jika tidak ada/tidak valid).
- Tombol `← Kembali ke Dashboard` mengarah ke `index.html`, ditempatkan jelas di posisi atas (kiri atas, konsisten di semua halaman non-dashboard).
- Tampilkan 1 video feed besar (bukan grid 2 kolom kecil seperti sekarang) sesuai gerbang yang dipilih, plus tombol toggle kecil untuk pindah ke gerbang lainnya tanpa kembali ke dashboard dulu (`[Gerbang A] [Gerbang B]` seperti tab, mengikuti pola gambar referensi 1).
- Di bawah video: metrik ringkas KHUSUS gerbang itu (bukan gabungan) — status koneksi kamera (Live/Offline), FPS jika tersedia dari `/api/gerbang-status`, dan breakdown masuk/keluar per jenis kendaraan khusus gerbang ini (dari `per_gerbang.gerbang_a` atau `.gerbang_b`, Fase 1.1).

### 3.2 Lazy loading video — teknis penting

`<img src="...">` untuk MJPEG stream **hanya ditulis ke DOM setelah halaman `gerbang.html` benar-benar dibuka**, bukan sejak awal load lalu disembunyikan dengan CSS `display:none` (itu tetap akan memuat stream di background, sia-sia). Gunakan JS untuk membuat elemen `<img>` secara dinamis (`document.createElement`) dan set `src` HANYA setelah `DOMContentLoaded` di halaman ini. Saat user menekan tombol kembali ke dashboard atau pindah tab browser, pastikan `img.src = ""` sebelum navigasi (untuk memutus koneksi stream MJPEG secara eksplisit, bukan menunggu browser garbage-collect).

### 3.3 Definisi Selesai Fase 3
- [ ] `gerbang.html?gerbang=a` dan `?gerbang=b` menampilkan video dan data yang benar sesuai parameter.
- [ ] Tombol kembali ke dashboard berfungsi dan terlihat jelas.
- [ ] Video benar-benar berhenti dimuat saat meninggalkan halaman ini (verifikasi via tab Network browser: request ke `video_feed` berhenti setelah pindah halaman).
- [ ] `index.html` (Fase 2) sudah tidak memuat video sama sekali — dikonfirmasi ulang di sini bahwa keduanya benar-benar independen.

---

## FASE 4 — Halaman Kalibrasi & Debug (`kalibrasi.html`) — Fitur Baru

**Tujuan:** Membangun panel kalibrasi garis + monitoring live deteksi, terinspirasi gambar referensi 2, disesuaikan dengan arsitektur sistem Anda (2 gerbang, dual-direction counting line per kamera — bukan sistem re-ID multi-kamera seperti tampak di gambar referensi 2 milik teman Anda, jadi jangan tiru fitur yang tidak relevan seperti "asosiasi ID lintas kamera").

Ini murni fitur baru — tidak ada baseline lama untuk dibandingkan. Susun sebagai sub-fase kecil supaya bisa dicek satu-satu:

### 4.1 Backend: endpoint kalibrasi

Perlu endpoint baru (belum ada sama sekali):
- `GET /api/kalibrasi/{gerbang_id}` → kembalikan koordinat garis counting saat ini (dari config aktif gerbang tsb, baca `config_gerbang_a.yaml`/`config_gerbang_b.yaml`).
- `POST /api/kalibrasi/{gerbang_id}` → terima koordinat garis baru (titik-titik piksel), tulis ke file config YAML gerbang terkait. **Wajib validasi input** (koordinat harus angka valid dalam batas resolusi frame, format sesuai yang dibaca `counting_line.py`) sebelum menimpa file config — jangan biarkan endpoint ini menerima payload sembarangan yang bisa merusak file YAML produksi.
- `POST /api/kalibrasi/{gerbang_id}/reset-counter` → reset counter in-memory gerbang tsb (perlu mekanisme komunikasi ke proses edge yang berjalan — lihat catatan arsitektur di 4.2).

Amankan endpoint ini dengan mekanisme API key yang sama seperti yang sudah dipakai untuk `export_riwayat` (`_require_api_key`, lihat `api_server.py` baris ~151) — endpoint yang bisa MENGUBAH konfigurasi sistem tidak boleh terbuka tanpa autentikasi, beda dengan endpoint baca-saja di Fase 1-3.

### 4.2 Catatan arsitektur penting: proses edge vs proses server

Perhatikan: `mqtt_consumer.py` adalah proses SERVER (menerima data via MQTT), sedangkan deteksi/tracking/counting-line berjalan di proses EDGE (kemungkinan `src/main.py` + `src/detector.py` + `src/counting_line.py`, berjalan dekat kamera). **Reset counter dan reload kalibrasi garis harus terjadi di proses EDGE, bukan di server**, karena di situlah state tracking hidup. Ini berarti:
- Endpoint API kalibrasi di `api_server.py` (server) hanya mengubah **file config**.
- Proses edge (`main.py`) perlu mekanisme untuk **mendeteksi perubahan file config dan reload otomatis** (file-watcher sederhana, atau polling perubahan `mtime` file config setiap beberapa detik), ATAU alternatif lebih sederhana untuk versi awal: cukup tampilkan instruksi di UI "Konfigurasi tersimpan — restart proses edge (`main.py`) untuk menerapkan" tanpa hot-reload otomatis dulu. **Pilih pendekatan kedua (manual restart) untuk iterasi pertama** — hot-reload live itu pekerjaan signifikan sendiri dan tidak wajib untuk kebutuhan kalibrasi Anda saat ini (kalibrasi dilakukan sesekali, bukan tiap menit).

### 4.3 Frontend: kanvas kalibrasi interaktif

- Tampilkan 1 frame terbaru dari kamera gerbang terpilih (gambar statis, BUKAN stream live terus — cukup ambil 1 snapshot saat halaman kalibrasi dibuka, mengurangi beban dibanding video kontinu; tombol "Ambil Snapshot Baru" untuk refresh manual).
- Overlay garis counting yang bisa digeser titik-titiknya (drag 2 titik ujung garis) di atas gambar snapshot, mirip pola gambar referensi 2 ("pilih garis, klik dua titik di video, geser ujungnya").
- Tombol "Simpan Konfigurasi" mengirim koordinat baru ke `POST /api/kalibrasi/{gerbang_id}`.
- Panel info di samping: jumlah kelas terdeteksi live (jika tersedia dari status terbaru gerbang itu), status counting (arah IN, sisi cyan/merah sesuai konvensi yang sudah ada di kode Anda).
- Halaman ini TIDAK perlu tampil di navigasi utama dashboard produksi — cukup diakses lewat URL langsung (`kalibrasi.html?gerbang=a`) supaya tidak membingungkan Dishub saat demo.

### 4.4 Definisi Selesai Fase 4
- [ ] Endpoint kalibrasi baca (`GET`) berfungsi, kembalikan koordinat garis aktual dari config file.
- [ ] Endpoint kalibrasi tulis (`POST`) tervalidasi, terlindungi API key, dan terbukti berhasil menulis ke file YAML yang benar saat diuji manual.
- [ ] Halaman `kalibrasi.html` bisa menampilkan snapshot + overlay garis yang bisa digeser, dan tombol simpan berfungsi end-to-end (drag garis → simpan → cek isi file YAML berubah sesuai).
- [ ] Didokumentasikan jelas di UI bahwa perubahan butuh restart proses edge manual (bukan hot-reload) untuk iterasi pertama ini.
- [ ] Tidak ada tautan halaman ini dari `index.html` produksi (akses via URL langsung saja).

---

## FASE 5 — Pembersihan Kode Bersama & Optimasi Ringan

**Tujuan:** Setelah 3 halaman terpisah stabil (Fase 2-4), rapikan duplikasi dan pastikan benar-benar ringan.

### 5.1 Ekstrak kode bersama
- Pindahkan fungsi JS yang dipakai di >1 halaman (format angka Indonesia, koneksi WebSocket/polling, fetch status dasar) ke `dashboard/shared.js`, di-import di ketiga halaman.
- Pindahkan variabel CSS (`:root { --lancar, --padat, --macet, ... }`) dan komponen umum (`.glass-panel`, `.metric-card`, tombol) ke `dashboard/shared.css`.

### 5.2 Audit ukuran & jumlah request
- Ukur ukuran total halaman (HTML+CSS+JS, tanpa video) untuk `index.html` — target realistis untuk dashboard status: di bawah 150 KB total (belum termasuk font/vendor eksternal yang sudah di-cache browser).
- Konfirmasi tidak ada request ke `video_feed` sama sekali saat membuka `index.html` (cek tab Network browser, filter tipe "img"/"media").

### 5.3 Definisi Selesai Fase 5
- [ ] Tidak ada duplikasi fungsi JS identik di 3 file HTML berbeda.
- [ ] `index.html` terbukti (via DevTools Network tab, direkam sebagai screenshot atau catatan) tidak memuat stream video sama sekali.
- [ ] Ketiga halaman tetap berfungsi identik seperti sebelum refactor (regresi manual: buka satu-satu, cek semua data tampil benar).

---

## FASE 6 — Performa Edge & Backend (Opsional, Setelah Dashboard Stabil)

**Tujuan:** Item performa yang ditemukan saat audit lanjutan, di luar lapisan dashboard (Fase 1-5). Tidak wajib untuk demo Dishub, tapi relevan untuk deployment jangka panjang (termasuk migrasi ke Raspberry Pi 5). Kerjakan Fase 6 HANYA setelah Fase 1-5 selesai dan stabil — supaya perubahan di lapisan edge/backend tidak bercampur dengan perubahan dashboard saat proses review.

### 6.1 Overlay drawing tetap jalan walau tidak ada yang menonton

**Temuan:** `DetektorKendaraan.proses_frame()` di `src/detector.py` selalu memanggil `Visualizer.gambar_overlay()` (menggambar bounding box, label, garis counting) di **setiap frame yang diproses**, terlepas apakah ada klien yang sedang membuka `video_feed` MJPEG atau tidak. Ini kerja CPU yang terbuang percuma pada momen-momen (mayoritas waktu operasional) saat tidak ada operator yang sedang melihat halaman `gerbang.html`.

**Perbaikan:**
- Tambahkan mekanisme flag "ada klien aktif" di `src/mjpeg_streamer.py` — hitung jumlah koneksi `StreamingResponse` yang sedang terbuka (increment saat `video_feed()` dipanggil, decrement saat generator berhenti/klien putus koneksi).
- Ekspos flag ini lewat fungsi kecil, mis. `mjpeg_streamer.ada_viewer_aktif() -> bool`.
- Di `detector.py` / `main.py`, panggil `Visualizer.gambar_overlay()` HANYA jika `ada_viewer_aktif()` bernilai True. Jika tidak ada viewer, kirim `frame` mentah (tanpa overlay) ke `update_frame()`, atau skip `update_frame()` sepenuhnya — deteksi, tracking, dan counting tetap jalan seperti biasa (logika inti TIDAK boleh bergantung pada ada/tidaknya viewer), yang di-skip murni proses menggambar visual untuk ditonton manusia.

**Definisi Selesai:**
- [ ] Overlay tidak digambar saat tidak ada klien MJPEG aktif (verifikasi: pantau CPU usage proses edge sebelum & sesudah, dengan dan tanpa `gerbang.html` terbuka).
- [ ] Counting, tracking, dan publish MQTT tetap akurat dan tidak berubah perilakunya baik saat ada maupun tidak ada viewer (regresi: bandingkan hasil hitungan sebelum/sesudah perubahan ini pada video sumber yang sama).

### 6.2 `frame_skip` statis, tidak adaptif terhadap beban

**Temuan:** `tampilan.frame_skip` di config (default 4) adalah angka tetap — sistem selalu memproses 1 dari setiap 4 frame lewat YOLO, terlepas dari kecepatan inferensi aktual perangkat. Ini cukup aman di laptop dengan GPU NVIDIA (sesuai environment pengembangan Anda saat ini), tapi berisiko saat nanti pindah ke Raspberry Pi 5 + Coral (rencana deployment akhir Anda menurut catatan proyek): kalau frame_skip dipertahankan sama padahal Raspberry Pi jauh lebih lambat, backlog frame akan menumpuk; kalau frame_skip dinaikkan asal supaya tetap real-time, sampling rate turun dan akurasi counting bisa terdampak (kendaraan cepat berpotensi terlewat dalam gap antar-sampel).

**Perbaikan (untuk iterasi awal, tidak perlu rumit):**
- Ukur waktu eksekusi `self.model.track(...)` di `proses_frame()` (sudah ada waktu mulai/selesai yang bisa diambil dengan `time.time()` di sekitar pemanggilan tersebut).
- Jika rata-rata waktu inferensi (moving average beberapa frame terakhir) melebihi ambang tertentu relatif terhadap FPS sumber video, naikkan `frame_skip` secara bertahap (mis. +1) sampai waktu proses per-siklus kembali di bawah ambang; jika di bawah ambang dengan margin, turunkan `frame_skip` bertahap (mis. -1, dengan batas bawah agar tidak ke 0/1 yang terlalu berat) untuk memanfaatkan headroom perangkat.
- **Catatan penting:** perubahan `frame_skip` mengubah rate sampling, yang bisa sedikit mengubah kalibrasi estimasi kecepatan di `counting_line.py` (yang menghitung delta piksel antar-frame yang diproses). Sebelum mengaktifkan mode adaptif otomatis, pastikan `counting_line.py` menghitung kecepatan dari **delta waktu aktual** (timestamp antar-sampel), bukan asumsi interval frame yang tetap — jika sudah begitu, adaptif frame_skip aman; jika belum, ini harus diperbaiki dulu sebagai prasyarat sebelum Fase 6.2 dikerjakan.

**Definisi Selesai:**
- [ ] Frame skip menyesuaikan otomatis berdasarkan rata-rata waktu inferensi terukur, dengan batas atas dan bawah yang wajar (jangan biarkan naik/turun tak terbatas).
- [ ] Dikonfirmasi bahwa `counting_line.py` sudah pakai delta waktu aktual (bukan asumsi interval tetap) sebagai prasyarat sebelum mode adaptif dinyalakan — jika belum, ini diperbaiki lebih dulu sebagai sub-langkah sebelum lanjut.
- [ ] Diuji di kondisi beban tinggi tiruan (mis. batasi CPU secara sengaja atau jalankan proses lain bersamaan) untuk memastikan sistem tetap stabil, tidak crash atau macet, saat frame_skip menyesuaikan naik.

### 6.3 Endpoint `/api/riwayat` (grafik tren) masih pola polling per-klien, bukan broadcast

**Temuan:** Status real-time (`_ws_broadcast_loop` di `api_server.py`) sudah benar secara arsitektur — 1 query database di server, hasilnya di-broadcast ke semua klien WebSocket sekaligus. Tapi endpoint `/api/riwayat` (dipakai grafik tren "2 jam terakhir") masih dipanggil independen oleh tiap klien dashboard (`setInterval(fetchRiwayat, 20_000)` di `dashboard/index.html`) — jika dashboard dibuka di banyak device bersamaan (skenario realistis saat demo ke Dishub: beberapa staf membuka dashboard dari laptop/HP masing-masing), setiap device melakukan query database sendiri-sendiri untuk data historis yang sebenarnya identik untuk semua orang di waktu yang sama.

**Perbaikan:** Untuk skala kecil (beberapa klien saat demo), ini **belum darurat** — cukup dicatat sebagai item peningkatan, bukan kewajiban. Jika ingin diperbaiki: satukan data riwayat ke dalam payload broadcast WebSocket yang sudah ada (`_build_status_response()` bisa ditambah field riwayat ringkas), sehingga klien tidak perlu polling HTTP terpisah untuk grafik — cukup satu koneksi WebSocket per klien untuk semua kebutuhan data real-time + riwayat singkat. Riwayat jangka panjang (>2 jam, untuk keperluan laporan/ekspor) tetap lewat endpoint HTTP biasa karena itu tidak perlu real-time.

**Definisi Selesai (jika dikerjakan):**
- [ ] Data grafik tren tersedia dari payload WebSocket yang sudah ada, tanpa endpoint HTTP polling terpisah untuk kebutuhan tampilan real-time.
- [ ] Diuji dengan >1 tab/device dashboard terbuka bersamaan — jumlah query database ke tabel `status_ruas` untuk data riwayat tidak bertambah linear terhadap jumlah klien yang terbuka.

### 6.4 Item yang SUDAH diperiksa dan TIDAK perlu diubah (dicatat supaya tidak dikerjakan ulang tanpa perlu)

- **MJPEG streamer (`src/mjpeg_streamer.py`)** sudah dioptimasi dengan baik: FPS dibatasi 8, JPEG quality 50, thread-safe dengan lock. Tidak ada perubahan dibutuhkan di sini — beban dashboard yang terasa berat berasal dari jumlah stream yang dimuat SEKALIGUS di satu halaman (sudah ditangani Fase 2-3), bukan dari efisiensi encoding stream itu sendiri.
- **Connection pooling database (`src/database.py`)** sudah pakai `SimpleConnectionPool` dengan `min=1, max=10` per proses, plus retry logic saat gagal konek. Ukuran ini wajar untuk skala prototipe 2 gerbang; tidak perlu diubah kecuali nanti terbukti jadi bottleneck nyata (baru diperbesar jika ada bukti, jangan diperbesar spekulatif).
- **Indexing tabel database** (`idx_hitungan_timestamp`, `idx_hitungan_gerbang`, `idx_status_timestamp` di `scripts/setup_database.sql`) sudah mencakup kolom yang paling sering dipakai untuk filter waktu dan gerbang. Tidak ada query lambat yang teridentifikasi dari query pattern yang ada saat ini.

### 6.5 Definisi Selesai Fase 6 (keseluruhan)
- [ ] 6.1 dan 6.2 dikerjakan dan diuji sesuai kriteria masing-masing di atas.
- [ ] 6.3 dikerjakan JIKA ada kebutuhan nyata multi-klien bersamaan (opsional, bisa ditunda tanpa risiko untuk skala demo saat ini).
- [ ] Regresi penuh: jalankan `pytest` dan verifikasi manual bahwa hasil counting/occupancy pada video sumber yang sama tidak berubah dibanding sebelum Fase 6 (perubahan di fase ini murni soal KAPAN/BERAPA SERING kerja dilakukan, bukan mengubah APA yang dihitung).

---

## 2. Yang SENGAJA TIDAK Dimasukkan ke PRD Ini (dan Kenapa)

- **Tidak mengubah rumus `sistem_pakar.py`, `occupancy_estimator.py`, atau memperbaiki `mkji.py`** — itu ranah PRD v3, sudah dianalisis terpisah dan tidak tumpang tindih dengan permintaan UI/UX Anda sekarang. Jangan campur dua pekerjaan ini dalam satu sesi eksekusi AI code editor supaya mudah di-review satu-satu.
- **Tidak menambahkan fitur asosiasi ID lintas kamera / re-identification** — itu terlihat di gambar referensi 2 milik teman Anda ("Biaya asosiasi", "Pencocokan per kelas, Hungarian", filter Kalman) tapi itu relevan untuk arsitektur MULTI-KAMERA PER RUAS yang butuh melacak kendaraan yang sama lintas kamera dalam satu ruas panjang. Arsitektur Anda (2 gerbang, masing-masing dual-direction counting line dalam 1 frame) tidak butuh re-ID — occupancy dihitung dari selisih kumulatif, bukan pencocokan identitas kendaraan. Meniru fitur ini akan jadi over-engineering yang tidak dibutuhkan desain Anda.
- **Tidak migrasi model YOLO / fine-tuning** — itu topik terpisah yang sedang berjalan (laporan ke dosen soal deteksi motor), di luar cakupan PRD ini.
- **Tidak menyentuh Raspberry Pi/Coral deployment** — PRD ini murni soal dashboard yang jalan di laptop/server Anda saat pengembangan; isu Coral USB Accelerator sudah dicatat di PRD v3 sebagai isu terpisah.

---

## 3. Ringkasan Urutan Eksekusi untuk Antigravity

```
FASE 1 (Backend)  → FASE 2 (Dashboard ringkas)  → FASE 3 (Halaman gerbang)
      ↓                                                    ↓
      └──────────────→ FASE 4 (Kalibrasi, opsional paralel dgn Fase 3)
                                    ↓
                              FASE 5 (Pembersihan)
                                    ↓
                    FASE 6 (Performa edge & backend, opsional, terpisah dari dashboard)
```

Fase 1 wajib duluan (semua fase lain butuh datanya). Fase 2 dan 3 berurutan erat (Fase 2 menghapus video, Fase 3 menampung video yang dihapus — jangan selesaikan Fase 2 tanpa Fase 3 siap, supaya tidak ada periode di mana fitur lihat kamera hilang total). Fase 4 bisa dikerjakan kapan saja setelah Fase 1 (tidak bergantung pada Fase 2/3). Fase 5 selalu setelah Fase 2-4 selesai (membereskan hasil ketiganya). Fase 6 murni opsional dan sengaja dipisah paling akhir — menyentuh lapisan edge/deteksi (bukan dashboard), sehingga dampak perubahannya perlu direview terpisah dari perubahan UI supaya mudah dilacak kalau ada regresi.

**Setelah setiap fase selesai, jalankan test suite yang ada (`pytest`) untuk memastikan tidak ada regresi di rumus inti**, sebelum lanjut ke fase berikutnya.