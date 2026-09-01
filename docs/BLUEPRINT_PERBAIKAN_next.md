# BLUEPRINT PERBAIKAN v5 — Sitinjau Lauik Command Center
## Menuju Production-Ready: Cepat, Kuat, Tahan Lama

**Untuk:** AI code editor (Antigravity/Cursor/dsb) yang akan mengeksekusi
**Sumber:** Audit baris-per-baris atas `sitinjau-lauik-cv.zip`, revisi kedua (2026-09-01) — memperluas audit v4 dengan fokus khusus pada resiliency, performa, dan kesiapan produksi
**Cara pakai dokumen ini:** 9 Tahap, independen, dikerjakan berurutan sesuai bagian "URUTAN EKSEKUSI" di paling bawah. Setiap Tahap punya file yang disentuh, langkah konkret, dan **Kriteria Selesai** yang harus lulus sebelum lanjut ke Tahap berikutnya. Dokumen ini menggantikan `BLUEPRINT_PERBAIKAN_v4.md` — gunakan versi ini saja.

---

## 0. RINGKASAN TEMUAN AUDIT

### 0.1 Apa yang SUDAH bagus (jangan diubah, ini kekuatan proyek Anda)

Setelah membaca ulang seluruh `src/` baris-per-baris dengan fokus khusus pada resiliency dan performa, ditemukan fondasi yang sudah **cukup matang untuk basis produksi**:

- **`video_source.py`** — threaded frame grabber dengan exponential backoff reconnect RTSP, thread-safe, password RTSP disensor di log. Ini kualitas production, tidak perlu disentuh.
- **`event_publisher.py`** — MQTT dengan Last Will & Testament (LWT), QoS 1, dan **write-ahead buffer lokal** (JSONL) yang otomatis drain saat koneksi pulih — kalau broker mati beberapa jam, tidak ada data yang hilang. Ini pola arsitektur yang solid.
- **`database.py`** — connection pooling, retry, semua query terparameterisasi dengan benar (`make_interval()`, bukan f-string SQL).
- **`logger.py`** — rotasi log harian otomatis, retensi 7 hari, tidak akan membengkak.
- **`counting_line.py`** — histeresis + validasi arah pergerakan sebelum menghitung crossing (mencegah double-count dari jitter deteksi). Logika inti ini sudah teruji lewat iterasi berkali-kali.
- **`Dockerfile`** — multi-stage build, non-root user, healthcheck dasar. Praktik container yang benar.
- **CI (`ci.yml`)** — lint + test otomatis di setiap push. Sudah ada fondasi automated testing.
- **`mqtt_consumer.py`** — thread-safe state management dengan `threading.Lock`, recovery state dari DB saat restart, reset harian otomatis via `threading.Timer`.

### 0.2 Temuan baru dari audit mendalam (production-readiness)

Selain 9 temuan di v4 (kalibrasi visual, endpoint reset palsu, dsb — semua masih berlaku dan tercakup di Tahap 1-3 di bawah), audit lanjutan menemukan 8 isu baru yang menentukan apakah sistem ini **tahan banting** saat berjalan 24/7 tanpa pengawasan:

| # | Temuan | File | Kategori | Dampak |
|---|---|---|---|---|
| 10 | Buffer MQTT lokal di-drain tanpa menunggu konfirmasi (PUBACK) sebelum menghapus file buffer — jika proses mati tepat di tengah drain, entry yang belum benar-benar sampai ke broker bisa hilang permanen | `src/event_publisher.py` fungsi `_drain_buffer` | Kehilangan data | Rendah-sedang: hanya terjadi pada skenario proses crash tepat saat drain, tapi mungkin terjadi saat maintenance server |
| 11 | Ada `import logging` mentah + `logger.info()` untuk **setiap** kendaraan yang berhasil di-crossing, dipanggil di hot path (per-frame, per-track) — bukan lewat `src/logger.py` yang sudah disetup terpusat | `src/counting_line.py` baris 173, 188-189 | Performa & konsistensi | Di jam padat (ratusan crossing/menit), ini menambah I/O log yang tidak perlu dan tidak konsisten formatnya dengan sistem logging lain |
| 12 | Healthcheck di `docker-compose.yml` hanya ada untuk service `api` dan `mosquitto` — service `consumer`, `edge_a`, `edge_b` **tidak punya healthcheck sama sekali**, jadi Docker tidak tahu jika proses edge/consumer diam-diam macet (bukan crash, tapi hang) | `docker-compose.yml` | Observability & self-healing | Kalau proses edge macet tanpa crash, `restart: unless-stopped` tidak akan memicu restart karena container masih dianggap "running" |
| 13 | Tidak ada backup otomatis untuk database PostgreSQL — jika volume Docker/disk server rusak, seluruh histori hilang | Tidak ada file terkait | Disaster recovery | Untuk proyek yang menuju publikasi jurnal (butuh data historis sebagai bukti), ini risiko besar |
| 14 | `docker-compose.yml` tidak mendefinisikan `deploy.resources.limits` (CPU/memory limit) untuk service manapun — satu proses (mis. YOLO inference) bisa memakan semua resource host dan membuat service lain (database, API) ikut lambat | `docker-compose.yml` | Stabilitas multi-service | Penting khusus untuk target akhir (Raspberry Pi) yang resource-nya sangat terbatas |
| 15 | Tidak ada mekanisme retensi/arsip data historis di database — tabel `hitungan_kendaraan` dan `status_ruas` akan terus tumbuh tanpa batas selamanya (berbeda dari file log yang sudah dirotasi otomatis) | `src/database.py`, skema SQL | Skalabilitas jangka panjang | Setelah berjalan bertahun-tahun, query tanpa filter waktu (jarang tapi mungkin) akan melambat; ukuran database membengkak tanpa kendali |
| 16 | Watchdog (`watchdog.py`) memantau RAM dan suhu perangkat, tapi **tidak melakukan aksi apa pun** selain logging saat ambang terlampaui — tidak ada mekanisme auto-restart atau notifikasi keluar sistem (mis. ke Telegram/email) | `src/watchdog.py` | Observability & incident response | Kalau suhu/RAM kritis terjadi tengah malam, tidak ada yang tahu sampai Anda cek manual |
| 17 | Tidak ada dokumentasi/skrip untuk disaster recovery — jika server yang menjalankan `consumer`/`api` mati total, tidak ada runbook langkah pemulihan (restore DB dari backup, urutan start service yang benar, dsb) | Tidak ada file terkait | Operational readiness | Untuk sistem yang akan didemo ke Dishub sebagai calon sistem produksi, ini pertanyaan yang pasti akan ditanyakan |

Kedelapan temuan ini ditangani di **Tahap 8 (Production Hardening)** — bagian baru yang tidak ada di v4.

---

## 1. DESKRIPSI TEKSTUAL REFERENSI UI KALIBRASI (pengganti gambar 3 & 4)

Karena file `.md` ini tidak bisa membawa gambar, bagian ini mendeskripsikan secara rinci tata letak referensi dari proyek teman Anda yang ditunjukkan di gambar 3 dan gambar 4, supaya Tahap 1 bisa dieksekusi tanpa perlu melihat gambar aslinya. **Jika Anda tetap punya kedua gambar itu, tetap sertakan sebagai referensi visual tambahan — deskripsi ini untuk memastikan instruksi tidak hilang maknanya walau gambar tidak disertakan.**

### Tata letak layar penuh (gambar 3)
- Panel utama menampilkan **video/frame kamera** sebagai latar belakang penuh, menampilkan pemandangan jalan raya dari sudut pandang kamera CCTV (jalan dengan pembatas jalan, area rumput di sisi, kemungkinan pegunungan di latar).
- Di atas video, ada **watermark timestamp** ala CCTV di pojok kiri atas (format `TANGGAL JAM:MENIT:DETIK`, mis. "2026-08-31 15:16:37") dan info encoding kecil (nama kamera, FPS).
- Ada **garis horizontal merah** membentang selebar frame dengan label teks "COUNTING LINE" di ujung kiri — ini garis hitung utama.
- Ada **garis vertikal cyan/biru muda** yang berpotongan dengan garis merah di tengah frame — kemungkinan penanda batas lajur atau titik tengah kalibrasi.
- Di pojok kanan bawah video, ada baris info kecil real-time: `Inference: [angka] FPS`, `Deteksi: [angka]`, `Track: [angka]`, `Frame: [lebar]x[tinggi]` — info debug performa sistem yang tampil langsung di atas video.

### Panel kontrol samping (gambar 4)
Panel ini muncul di sisi (kemungkinan kanan atau sebagai overlay/drawer) dari tampilan video di atas, berisi dari atas ke bawah:

1. **Judul**: "KALIBRASI GARIS"
2. **Instruksi singkat**: teks penjelasan cara pakai — "Pilih garis yang akan diedit, lalu klik dua titik di video atau geser ujungnya. Merah = counting. Cyan = pemisah lajur. Simpan agar tidak hilang saat restart."
3. **Toggle pilihan jenis garis** — dua tombol berdampingan: **"Counting (merah)"** (dalam keadaan aktif/terpilih, warna biru terang) dan **"Lajur (cyan)"** (tidak aktif, warna gelap). Ini menentukan garis mana yang sedang diedit saat user klik di video.
4. **Baris tombol aksi**: **"Mode kalibrasi"** dan **"Terapkan"** — kemungkinan "Mode kalibrasi" adalah toggle on/off untuk mengaktifkan mode edit (supaya klik normal di video tidak sengaja mengubah garis saat tidak sedang mengedit), dan "Terapkan" menerapkan perubahan sementara ke tampilan (preview) sebelum disimpan permanen.
5. **Tombol "Simpan config"** — tombol biru terang terpisah, kemungkinan untuk menyimpan konfigurasi secara permanen ke file (beda dari "Terapkan" yang mungkin cuma preview sesi berjalan).
6. **Dropdown "Arah IN (counting)"** dengan pilihan seperti "Turun (atas → bawah)" — menentukan arah pergerakan mana yang dihitung sebagai "masuk" untuk garis counting yang sedang dipilih.
7. **Dropdown "Sisi IN (lajur)"** dengan pilihan seperti "Kiri garis cyan = masuk" — menentukan sisi mana dari garis lajur (cyan) yang dianggap sisi masuk.
8. **Tombol "Reset counter"** — tombol merah, terpisah dari tombol simpan, untuk mereset angka hitungan.
9. **Tampilan koordinat mentah read-only**, format teks monospace:
   ```
   counting: [138, 561, 2146, 553]
   lajur: [1100, 1, 1109, 1295]
   ```
   Menampilkan 4 angka per garis (x1, y1, x2, y2) sebagai referensi/debug transparan, di bawah kontrol dropdown.

10. **Panel "KLASIFIKASI LIVE (FRAME INI)"** — kotak dengan 4 kartu kecil berdampingan (grid 2x2), masing-masing untuk satu kelas kendaraan (Motor, Mobil, Bus, Truck), tiap kartu punya garis warna vertikal di kiri sebagai penanda kelas, angka besar "0" (kemungkinan jumlah terdeteksi di frame saat ini), dan detail kecil "IN: [angka] · OUT: [angka]" di bawahnya.

11. **Panel "TRACK AKTIF"** — menampilkan status singkat, contoh: "Belum ada track stabil" saat tidak ada objek terlacak.

12. **Panel "CROSSING TERBARU"** — daftar scrollable kejadian crossing terakhir, tiap baris format: `[ARAH: IN/OUT] · [KELAS] #[nomor track] ([confidence]%)`, contoh: "OUT · MOBIL #98 (91%)", "OUT · MOTOR #97 (63%)" — daftar terurut dari yang terbaru, dengan scrollbar di sisi kanan panel.

### Bagaimana menerjemahkan ini ke `kalibrasi.html` Anda

Struktur di atas **jangan ditiru 100% identik** — proyek teman Anda punya lebih banyak elemen debug (Track Aktif, Crossing Terbaru dengan confidence score) yang relevan untuk fase pengembangan model, sementara kebutuhan Anda saat ini lebih ke kalibrasi posisi garis untuk demo. Elemen yang **wajib diadopsi** karena langsung menjawab kebutuhan Anda:
- Canvas video sebagai latar dengan garis yang bisa digambar/digeser di atasnya (poin 1 tata letak layar).
- Toggle jenis garis "Counting (merah)" vs pemisah lajur jika Anda pakai konsep serupa (poin 3).
- Tombol Simpan dan Reset Counter terpisah (poin 5, 8) — ini sudah ada polanya di `kalibrasi.html` Anda saat ini, tinggal dipasangkan ke canvas baru.
- Tampilan koordinat mentah read-only (poin 9) — bagus untuk transparansi debug, murah untuk diimplementasi.

Elemen yang **opsional, boleh ditambahkan belakangan** jika waktu memungkinkan: panel Klasifikasi Live, Track Aktif, dan Crossing Terbaru (poin 10-12) — ini akan sangat membantu proses kalibrasi lapangan karena Anda bisa langsung melihat efek geseran garis terhadap deteksi real-time, tapi bukan blocker untuk kalibrasi dasar berfungsi.

---

## TAHAP 1 — Dashboard Kalibrasi Garis Visual

**Tujuan:** Mengganti form angka manual di `kalibrasi.html` dengan canvas interaktif sesuai deskripsi di Bagian 1 di atas: video/frame kamera sebagai latar, garis bisa ditarik langsung dengan mouse, toggle jenis garis, dan panel info di sampingnya.

### File yang disentuh
- `dashboard/kalibrasi.html` — rombak total bagian rendering garis
- `src/mjpeg_streamer.py` — tambah endpoint snapshot single-frame
- `src/api_server.py` — tambah endpoint untuk ambil frame snapshot terbaru, dan endpoint status live per gerbang (untuk panel Klasifikasi Live opsional)

### Langkah konkret

1. **Tambah endpoint snapshot di backend.** Di `src/mjpeg_streamer.py`, tambahkan fungsi yang mengembalikan 1 frame JPEG terakhir (bukan stream terus-menerus) di path `/snapshot`. Jauh lebih ringan daripada streaming MJPEG penuh untuk keperluan menggambar garis statis.

2. **Bangun ulang `kalibrasi.html` dengan struktur 2 kolom** mengikuti deskripsi Bagian 1:
   - **Kolom kiri (lebar, ~65-70%)**: `<canvas>` menampilkan snapshot sebagai background image, garis-garis digambar di atasnya dengan Canvas 2D API.
     - Overlay watermark timestamp di pojok kiri atas canvas (waktu saat ini, format `YYYY-MM-DD HH:MM:SS`), meniru gaya CCTV asli — murah untuk diimplementasi (`setInterval` update teks tiap detik) dan memberi kesan profesional.
     - Overlay info debug di pojok kanan bawah: FPS inference, jumlah deteksi, jumlah track aktif — ambil dari endpoint status yang sudah ada (`/api/status-terkini`), update setiap beberapa detik.
     - Interaksi drag: klik dan tahan pada titik ujung garis (radius klik ~10px di sekitar titik) untuk menggeser; lepas mouse untuk commit posisi baru.
     - Mode "Tambah Garis Baru": tombol terpisah yang mengaktifkan mode klik-2-titik untuk membuat garis baru dari nol.
   - **Kolom kanan (sempit, ~30-35%)**: panel kontrol, dari atas ke bawah:
     - Dropdown pilih gerbang (pertahankan yang sudah ada).
     - Field API Key (pertahankan).
     - Toggle "Counting (merah)" / "Lajur (cyan)" — menentukan garis mana yang sedang aktif diedit di canvas. Styling: tombol aktif warna terang (`--accent` dari `shared.css`), tombol nonaktif abu-abu gelap.
     - Dropdown "Arah IN" — pilihan makna semantik seperti "Turun (atas → bawah)" / "Naik (bawah → atas)", disimpan sebagai bagian dari `counting_lines` di config YAML (field baru `arah_masuk_visual` atau serupa, terpisah dari field `arah` yang sudah ada untuk "masuk"/"keluar" logis — supaya tidak menabrak struktur data yang sudah dipakai `detector.py`).
     - Tampilan koordinat read-only, format monospace: `counting: [x1, y1, x2, y2]`.
     - Tombol "Simpan Konfigurasi" dan "Reset Counter" (styling dipertahankan dari yang sudah ada; logic Reset Counter diperbaiki di Tahap 3).

3. **Konversi koordinat**: canvas mungkin dirender di ukuran berbeda dari resolusi asli video (`process_width` x `process_height` dari `config.yaml`, default 960x540). Sebelum kirim ke backend, konversi koordinat klik canvas ke skala piksel asli video — rumus: `x_asli = x_canvas * (process_width / canvas.width)`, sama untuk y. Ini penting supaya garis yang digambar di kalibrasi persis sama posisinya dengan yang dipakai `detector.py` saat runtime.

4. **Perbaiki endpoint simpan kalibrasi di backend** — ganti pendekatan regex-per-baris di `update_kalibrasi()` (`src/api_server.py`) dengan **parser YAML asli**. Gunakan `ruamel.yaml` (bukan `PyYAML` biasa) karena `ruamel.yaml` mendukung round-trip yang **mempertahankan komentar** `#` di file config — penting karena `config_gerbang_a.yaml` dan `config_gerbang_b.yaml` punya banyak komentar dokumentasi yang tidak boleh hilang saat ditulis ulang otomatis.
   ```
   Tambahkan ruamel.yaml==0.18.* ke requirements.txt
   Baca file dengan yaml = ruamel.yaml.YAML(); data = yaml.load(f)
   Modifikasi nilai counting_lines pada objek hasil parse (masih preserve komentar)
   Tulis kembali dengan yaml.dump(data, f)
   ```

5. **Live preview counting saat kalibrasi** (opsional, sesuai elemen "Klasifikasi Live" dan "Crossing Terbaru" di referensi): polling ringan setiap 3-5 detik ke endpoint status terkini, tampilkan angka masuk/keluar per kelas kendaraan secara live di panel kanan.

### Kriteria Selesai
- Buka `kalibrasi.html`, tampil snapshot kamera asli sebagai latar (bukan kosong/placeholder).
- Garis merah (counting) dan cyan (lajur, jika dipakai) tergambar sesuai posisi asli dari `config_gerbang_x.yaml`.
- Bisa drag titik ujung garis dengan mouse, posisi update real-time di canvas.
- Klik "Simpan Konfigurasi" berhasil menulis file YAML **tanpa menghilangkan komentar** yang sudah ada di file (verifikasi dengan membuka file config setelah simpan — bandingkan jumlah baris komentar sebelum-sesudah).
- Reload halaman, garis yang baru disimpan muncul di posisi yang benar (bukan posisi lama), membuktikan file benar-benar tersimpan dan terbaca ulang dengan tepat.
- Watermark timestamp di canvas menunjukkan waktu berjalan real-time.

---

## TAHAP 2 — Panel Admin Terpusat + Log Aktivitas

**Tujuan:** Memenuhi permintaan: "bagian admin bisa mengatur semuanya dan melihat semua aktivitas dengan detail dan mudah dimengerti".

### File yang disentuh
- Baru: `dashboard/admin.html`
- `src/database.py` — tambah tabel dan fungsi log aktivitas
- `scripts/setup_database.sql` — tambah `CREATE TABLE log_aktivitas`
- `src/api_server.py` — tambah endpoint `/api/admin/log-aktivitas`, `/api/admin/ringkasan`
- Titik kode yang melakukan aksi penting — tambahkan pemanggilan fungsi pencatatan log

### Langkah konkret

1. **Tambah tabel `log_aktivitas` di `setup_database.sql`:**
   ```sql
   CREATE TABLE IF NOT EXISTS log_aktivitas (
       id_log          BIGSERIAL PRIMARY KEY,
       waktu           TIMESTAMP DEFAULT NOW(),
       kategori        VARCHAR(30) NOT NULL,   -- 'kalibrasi' | 'reset_counter' | 'kamera' | 'sistem'
       gerbang_id      VARCHAR(50),
       deskripsi       TEXT NOT NULL,
       actor           VARCHAR(50),            -- 'admin' | 'sistem'
       detail_json     JSONB
   );
   CREATE INDEX IF NOT EXISTS idx_log_waktu ON log_aktivitas(waktu);
   CREATE INDEX IF NOT EXISTS idx_log_kategori ON log_aktivitas(kategori);
   ```
   Terpisah dari file log teks (`data/logs/sistem.log`) yang sudah ada — file teks untuk debugging developer, tabel ini untuk aktivitas bermakna bisnis yang ditampilkan ke user di dashboard.

2. **Tambah fungsi `catat_aktivitas()` di `src/database.py`.** Panggil dari:
   - `update_kalibrasi()` di `api_server.py` — kategori `kalibrasi`, deskripsi `"Garis {id} gerbang {gerbang_id} diubah"`, `detail_json` berisi koordinat lama vs baru.
   - Fungsi reset counter (Tahap 3) — kategori `reset_counter`.
   - Deteksi kamera offline/online (Tahap 5) — kategori `kamera`.

3. **Buat halaman `dashboard/admin.html`**, struktur:
   - Ringkasan atas: kartu metrik "Total kejadian hari ini", "Gerbang aktif", "Kalibrasi terakhir diubah", "Uptime sistem".
   - Tabel log aktivitas dengan filter kategori (dropdown) dan rentang waktu, **paginated** (jangan load semua log sekaligus — `LIMIT`/`OFFSET` di endpoint, default 50 baris per halaman).
   - Setiap baris log dalam bahasa manusia: "🔧 08:42 — Garis counting Gerbang A diubah oleh admin", bukan JSON mentah.
   - Link cepat ke `kalibrasi.html` per gerbang.
   - Tombol reset counter per gerbang (logic dari Tahap 3), supaya admin tidak perlu pindah halaman.

4. **Proteksi akses:** halaman `admin.html` sendiri boleh diakses siapa saja (statis, tidak ada data sensitif di HTML), tapi **semua endpoint API di baliknya** (`/api/admin/*`) wajib `X-API-Key` — pakai pola `_require_api_key()` yang sudah ada.

### Kriteria Selesai
- Buka `admin.html`, terlihat daftar aktivitas terbaru dalam bahasa yang mudah dibaca.
- Ubah kalibrasi lewat `kalibrasi.html`, kembali ke `admin.html`, kejadian muncul di log dalam <10 detik (refresh manual cukup untuk prototipe).
- Filter kategori berfungsi (pilih "kalibrasi" saja, hanya kejadian kalibrasi yang tampil).
- Buka halaman ke-2 paginasi, tidak error, menampilkan baris berikutnya.

---

## TAHAP 3 — Fitur "Hapus Data / Reset ke 0" yang Benar-Benar Berfungsi

**Tujuan:** Satu tombol, klik, semua kalkulasi (counter kumulatif, occupancy, grafik tren) langsung nol — tanpa perlu masuk ke Antigravity/edit kode lagi.

### Kenapa ini rumit secara arsitektur
Tiga proses berjalan terpisah, masing-masing punya "ingatan" sendiri:
1. `src/main.py` (proses edge, per kamera) — `counter_kumulatif` di memori proses (lihat `detector.py`).
2. `src/mqtt_consumer.py` (proses server) — `kumulatif_a_masuk`, `kumulatif_a_keluar`, dst di memori proses.
3. PostgreSQL — tabel `hitungan_kendaraan` dan `status_ruas`.

Menghapus data di database saja **tidak cukup** — proses berikutnya akan tetap memakai angka in-memory lama sebagai basis, sehingga terlihat "tidak ke-reset" walau database sudah kosong.

### Solusi: MQTT command topic + endpoint gabungan

1. **Tambah topik MQTT baru untuk kontrol**, terpisah dari topik data yang sudah ada (`sitinjau_lauik/{gerbang}/agregasi`): buat topik `sitinjau_lauik/command/reset`.

2. **Di `src/main.py`**, tambahkan subscriber MQTT tambahan yang mendengarkan topik ini. Saat menerima pesan reset, panggil `reset_tracker()` yang sudah ada di `detector.py` **dan tambahkan satu baris baru**: `self.counter_kumulatif = defaultdict(int)` di dalam method itu — saat ini `reset_tracker()` hanya mengosongkan `pelacak_garis`, bukan `counter_kumulatif`.

3. **Di `src/mqtt_consumer.py`**, tambahkan handler pesan untuk topik yang sama, panggil ulang `lakukan_reset_harian()` yang sudah ada (fungsi ini sudah tepat — mengosongkan keempat `defaultdict` di dalam `state_lock`) — tinggal panggil dari trigger manual, bukan cuma trigger jadwal tengah malam.

4. **Endpoint baru** `/api/admin/reset-total` di `api_server.py` (ganti `/api/kalibrasi/{gerbang_id}/reset-counter` yang lama, yang saat ini cuma mengembalikan pesan teks tanpa aksi nyata):
   - Wajib `X-API-Key`.
   - Query param `scope`: `"hari_ini"` (default) atau `"semua"` — beri pilihan eksplisit ke user, jangan asumsikan.
   - Langkah di dalam endpoint:
     a. Jika `scope=hari_ini`: `DELETE FROM hitungan_kendaraan WHERE timestamp_interval >= CURRENT_DATE` dan `DELETE FROM status_ruas WHERE timestamp_hitung >= CURRENT_DATE`.
     b. Jika `scope=semua`: `TRUNCATE hitungan_kendaraan, status_ruas` (lebih cepat dari DELETE untuk tabel besar, tapi **tidak bisa di-rollback** — pastikan konfirmasi dobel di frontend untuk opsi ini).
     c. Publish pesan MQTT ke topik `sitinjau_lauik/command/reset` — diterima otomatis oleh semua proses edge dan consumer yang berjalan.
     d. Panggil `catat_aktivitas()` (Tahap 2) mencatat siapa dan kapan.
   - Response jelas: `{"status": "sukses", "pesan": "Semua data [hari ini/histori] dan counter in-memory telah direset ke 0."}`.

5. **Di dashboard** (`admin.html` dan/atau `kalibrasi.html`), tombol "Reset Counter" memanggil endpoint baru. Tambahkan **dialog konfirmasi dua-langkah** (bukan cuma `confirm()` browser biasa) — user harus mengetik ulang kata "RESET" atau centang checkbox "saya paham data akan hilang permanen" sebelum tombol aktif, khususnya untuk `scope=semua`.

### Kriteria Selesai
- Sistem berjalan (edge + consumer + api aktif), beberapa kendaraan sudah terhitung.
- Klik tombol reset di dashboard.
- Dalam <5 detik, semua angka di `index.html` (occupancy, kendaraan per jenis, grafik tren) kembali ke 0 **tanpa restart proses manual**.
- Kendaraan baru yang lewat setelah reset dihitung mulai dari 0, bukan melanjutkan dari angka lama.
- Matikan salah satu proses edge sebelum reset, nyalakan lagi setelah reset — pastikan proses yang baru start juga menerima state ter-reset (bukan recovery angka lama dari DB, karena DB sudah kosong — verifikasi `recover_state()` di `mqtt_consumer.py` berjalan benar pasca-reset).

---

## TAHAP 4 — Perbaikan Keamanan

**Tujuan:** Menutup celah yang ditemukan, proporsional untuk tahap prototipe/demo.

### Langkah konkret

1. **Ganti `API_KEY=admin123` di `.env`** dengan string acak panjang: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Lakukan sebelum demo ke Dishub — API key ini melindungi endpoint yang bisa mengubah konfigurasi kamera dan menghapus data.

2. **Tambah rate limiting** di `api_server.py` untuk endpoint sensitif (`/api/kalibrasi/*`, `/api/admin/*`). Gunakan `slowapi` (kompatibel FastAPI) — batasi misal 10 request/menit per IP. Tidak perlu diterapkan ke endpoint baca-saja yang dipanggil sering oleh dashboard sendiri (`/api/status-terkini`, dll).

3. **Hapus `scripts/migrate_db.py`** — file ini pakai nama kolom lama (`vc_ratio_mkji`, `los_mkji`) yang tidak sinkron dengan skema aktual (`rasio_vc_mkji`, `level_of_service_mkji` di `setup_database.sql`), dan berisiko dijalankan tanpa sengaja oleh siapa pun (termasuk AI agent lain) yang mengira ini "cara resmi migrasi" — padahal `setup_database.sql` sudah menangani migrasi secara idempoten sendiri.

4. **Constraint `gerbang_id` di database sudah cukup** — kolom `hitungan_kendaraan.id_gerbang` sudah `REFERENCES gerbang_kamera(id_gerbang)`, PostgreSQL sendiri menolak insert dengan `gerbang_id` tidak valid. Pastikan saja error dari constraint ini ditangani dengan pesan log jelas di `mqtt_consumer.py` (bukan silent fail) — jangan tambah validasi duplikat di level aplikasi.

5. **Perbaiki CORS wildcard risk** — cek `_cors_origins()` di `api_server.py`: pastikan default fallback (`localhost:8000`, `127.0.0.1:8000`) diganti dengan domain asli sebelum deploy ke jaringan Dishub, jangan biarkan default localhost dipakai di lingkungan produksi tanpa disadari.

### Kriteria Selesai
- `.env` tidak lagi berisi `admin123`.
- Percobaan >10 request/menit ke endpoint kalibrasi dari 1 IP mendapat response `429 Too Many Requests`.
- `scripts/migrate_db.py` sudah tidak ada di repo.
- `CORS_ORIGINS` di `.env` production diisi domain asli, dicek bukan default localhost.

---

## TAHAP 5 — Deteksi Kamera Offline/Online

**Tujuan:** Status "AKTIF" gerbang di dashboard harus benar-benar mencerminkan kondisi real-time, bukan nilai statis dari seed data awal.

### Langkah konkret

1. **Di `mqtt_consumer.py`**, setiap kali `on_message` menerima data, update `last_seen` timestamp per gerbang di memori (dictionary sederhana, dilindungi `state_lock` yang sudah ada).

2. **Tambah background timer** (mirip pola `jadwalkan_reset()` yang sudah ada) yang mengecek setiap 30 detik: jika `last_seen` gerbang manapun lebih tua dari 60 detik (2x interval agregasi default), update `status_perangkat` gerbang itu jadi `'nonaktif'` di database dan catat ke `log_aktivitas` (kategori `kamera`).

3. Saat data masuk kembali dari gerbang yang tadinya nonaktif, update balik jadi `'aktif'` dan catat log "Gerbang X kembali online".

4. **Manfaatkan LWT MQTT yang sudah ada** di `event_publisher.py` — topik `{prefix}/{client_id}/status` sudah mem-publish `online`/`offline` secara otomatis (termasuk saat proses edge crash, broker akan otomatis publish pesan LWT "offline"). Subscribe topik ini juga di `mqtt_consumer.py` sebagai sinyal tambahan yang lebih cepat dari sekadar timeout `last_seen` — kombinasi keduanya (LWT untuk deteksi cepat, timeout untuk fallback jika LWT gagal terkirim) membuat deteksi offline lebih akurat.

### Kriteria Selesai
- Matikan proses `main.py` salah satu gerbang secara sengaja (kill process, bukan graceful shutdown).
- Dalam ~60 detik (atau lebih cepat jika LWT berhasil terkirim), dashboard menampilkan gerbang itu sebagai nonaktif/offline.
- Nyalakan lagi, status kembali aktif otomatis tanpa restart `api_server.py`.

---

## TAHAP 6 — Perbaikan README.md

**Tujuan:** README akurat 100% terhadap kode aktual, lengkap untuk keperluan akademik maupun demo.

### Perbaikan wajib

1. Ganti "database SQLite lokal" → **PostgreSQL**, instruksi setup benar mengarah ke `scripts/setup_database.sql` dijalankan via `psql -U postgres -d sitinjau_lauik_db -f scripts/setup_database.sql` (bukan `python scripts/setup_database.sql` yang salah — itu file `.sql`, bukan `.py`).

2. Ganti "5 kelas kendaraan (Motor, Mobil, Truk Ringan, Truk Berat, Bus)" → **4 kelas**: motor, mobil, bus, truk (sesuai `coco_class_mapping` di `config.yaml`).

3. Tambah bagian **"Menjalankan dengan Docker Compose"** sebagai cara direkomendasikan (`docker-compose.yml` sudah mengorkestrasi 5 service: mosquitto, api, consumer, edge_a, edge_b) — jadikan opsi utama, opsi manual sebagai alternatif.

4. Tambah bagian **"Menjalankan Dashboard"** menjelaskan halaman-halaman (`index.html` = utama, `gerbang.html` = live camera per gerbang, `kalibrasi.html` = kalibrasi garis visual, `admin.html` = panel admin setelah Tahap 2 selesai).

5. Tambah bagian **"Environment Variables"** mendaftar semua variabel dari `.env` (`GERBANG_A_RTSP_URL`, `GERBANG_B_RTSP_URL`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `API_KEY`, `CORS_ORIGINS`) dengan penjelasan singkat, dan peringatan eksplisit ganti `API_KEY` default sebelum deploy manapun.

6. Tambah bagian ringkas **"Metodologi Perhitungan"** menjelaskan dua pendekatan sistem: sistem pakar rule-based berbasis occupancy dan MKJI 1997 sebagai metrik standar resmi — link ke `docs/METODOLOGI_PERHITUNGAN.md` yang sudah ada (jangan duplikasi isi, cukup ringkas + link).

7. Tambah bagian **"Arsitektur Resiliency"** menjelaskan mekanisme ketahanan yang sudah dibangun (buffer MQTT lokal, auto-reconnect RTSP, connection pool database) — ini nilai jual teknis kuat yang layak didokumentasikan untuk pembaca teknis/reviewer jurnal, bukan cuma disimpan sebagai detail implementasi tersembunyi.

8. Tambah bagian **"Production Readiness & Roadmap"** yang jujur tentang status saat ini: fitur mana yang sudah production-grade (resiliency edge, buffer MQTT), mana yang masih prototipe (backup database manual, belum ada monitoring eksternal) — ini justru meningkatkan kredibilitas dokumen dibanding klaim berlebihan.

9. Update **"Struktur Direktori"** — tambahkan `docs/`, dan jelaskan status `scripts/kalibrasi_garis.py` (CLI) setelah Tahap 1 selesai — jika kalibrasi visual dashboard sudah menggantikan fungsinya, tandai sebagai "alternatif command-line" atau pertimbangkan dihapus supaya tidak ada dua cara kalibrasi yang membingungkan.

10. Tambah badge/section status: versi prototipe saat ini (2 kamera, Gerbang A + Gerbang B), catatan jelas deployment akhir memakai Raspberry Pi 5 + Coral USB Accelerator (`device: "cuda"` di `config.yaml` saat ini untuk pengembangan di laptop, bukan konfigurasi final).

### Kriteria Selesai
- Ikuti README dari nol di mesin baru (atau simulasikan langkah demi langkah), tidak ada instruksi yang mengarah ke perintah/file salah.
- Semua klaim fitur di README bisa ditunjuk ke baris kode yang benar-benar mengimplementasikannya.

---

## TAHAP 7 — Peningkatan UI/UX (Perspektif Frontend Engineer)

**Tujuan:** Mengangkat dashboard dari "fungsional generic" ke "terlihat seperti produk command-center yang matang", tanpa mengubah arsitektur data yang sudah bekerja baik.

### Masalah desain spesifik yang ditemukan

1. **Hierarki visual datar** — semua kartu metrik (Occupancy, Rasio Kepadatan, V/C MKJI, LOS Occupancy) punya bobot visual sama persis, tidak ada yang menarik mata ke angka paling penting. Perbaikan: kartu status utama (LOS/status lancar-padat-macet) dibuat lebih besar/menonjol secara proporsi, kartu pendukung dikecilkan atau dikelompokkan sebagai detail sekunder yang bisa di-expand.

2. **Skema warna kuning-navy solid tanpa gradasi kontekstual** — kuning header bagus sebagai warna brand, tapi status lalu lintas (lancar/padat/macet) sebaiknya konsisten memakai fungsi `interpolasiWarnaKapasitas` yang sudah ada di `shared.js`, bukan warna hijau statis terpisah untuk kartu "LANCAR" besar. Satukan sumber warna di satu tempat.

3. **Tipografi monoton** — semua angka besar pakai font-weight dan ukuran mirip. Terapkan skala tipografi tegas: angka utama 2.5-3rem bold, angka sekunder 1.25-1.5rem medium, label selalu kecil-uppercase-secondary color.

4. **Spasi/padding tidak konsisten antar komponen** — definisikan token spasi di `shared.css` (`--space-xs: 0.5rem; --space-sm: 1rem; --space-md: 1.5rem; --space-lg: 2rem;`) dan pakai konsisten di semua halaman, jangan magic number tersebar bebas.

5. **Empty/loading states generic** — tambahkan skeleton loading (kotak abu-abu berkedip halus) untuk kartu metrik saat data belum masuk, alih-alih teks statis "Memuat...".

6. **Ikon kendaraan bergaya emoji default** — ganti dengan icon set konsisten (Lucide icons atau SVG custom sederhana bergaya line-icon seragam) — mencampur emoji dan elemen UI custom adalah tanda paling jelas "belum di-polish" untuk demo profesional ke instansi pemerintah.

7. **Live camera feed tanpa overlay kontekstual** — tambahkan overlay ringan di pojok video container (di HTML, bukan di frame video) menampilkan waktu saat ini dan indikator live berdenyut (pulsing dot animation CSS sederhana), mengikuti gaya watermark CCTV yang sudah dijelaskan di Bagian 1 dokumen ini.

8. **Istilah teknis (MKJI, LOS, V/C) tanpa penjelasan** — istilah ini memang lazim tetap dalam bentuk aslinya di dunia teknik lalu lintas Indonesia, jadi sudah tepat dipertahankan — tapi tambahkan tooltip singkat saat di-hover (mis. "LOS" → "Level of Service — skala A (lancar) hingga F (macet total) sesuai standar MKJI 1997") supaya audiens non-teknis (pejabat Dishub) tidak bingung.

### Rekomendasi umum
- Jangan menambah library besar (React, Vue, dll) — pendekatan vanilla JS + Alpine.js (sudah ada di `dashboard/vendor/`) sudah pas untuk ukuran prototipe ini.
- Prioritaskan poin 1, 2, 3 dulu (hierarki visual, warna konsisten, tipografi) — dampak visual terbesar untuk usaha paling kecil.

---

## TAHAP 8 — Production Hardening (BAB BARU: kecepatan, ketahanan, observability)

**Tujuan:** Menutup 8 temuan baru di Bagian 0.2 — membuat sistem benar-benar siap berjalan 24/7 tanpa pengawasan konstan, bukan sekadar "berfungsi saat didemo".

### 8.1 Perbaiki logging di hot path (Temuan #11)

**File:** `src/counting_line.py`

Ganti `import logging` mentah di dalam fungsi `proses_deteksi` (baris 173, 188-189) dengan logger terpusat yang sudah ada di modul lain:
```python
# Di bagian atas file, tambahkan:
from src.logger import get_logger
logger = get_logger(__name__)

# Ganti semua `import logging; logging.getLogger(__name__).info(...)` 
# dan `.warning(...)` di dalam fungsi menjadi `logger.info(...)` / `logger.warning(...)`
```
Turunkan level log untuk crossing sukses dari `INFO` ke `DEBUG` — event ini terjadi sangat sering (setiap kendaraan lewat), `INFO` semestinya dipakai untuk kejadian penting yang jarang, bukan hot-path per-kendaraan. `detector.py` sudah punya log `[HITUNG]` di level `INFO` untuk tujuan yang sama — jadi log duplikat di `counting_line.py` sebaiknya dihapus sepenuhnya atau diturunkan ke `DEBUG` untuk menghindari duplikasi log yang membingungkan saat membaca `sistem.log`.

**Kriteria selesai:** Jalankan sistem dengan `logging.level: INFO` di config, pastikan log `[HITUNG]` dari `detector.py` tetap muncul tapi tidak ada duplikasi baris log crossing dari `counting_line.py`. Ganti ke `DEBUG` di config, baru baris debug tambahan muncul.

### 8.2 Perbaiki write-ahead buffer MQTT agar benar-benar zero-loss (Temuan #10)

**File:** `src/event_publisher.py`

Fungsi `_drain_buffer()` saat ini publish semua baris lalu langsung `unlink()` file buffer tanpa memverifikasi setiap publish benar-benar diterima broker (PUBACK untuk QoS 1). Perbaikan:
1. Gunakan callback `on_publish` dari `paho-mqtt` untuk melacak `mid` (message ID) dari setiap publish yang dikirim saat drain.
2. Tunggu (dengan timeout wajar, mis. 10 detik total untuk seluruh drain) sampai semua `mid` yang dikirim mendapat konfirmasi `on_publish` sebelum menghapus file buffer.
3. Jika ada entry yang timeout tanpa konfirmasi, **jangan hapus file buffer** — biarkan entry yang belum terkonfirmasi tetap ada untuk percobaan drain berikutnya (saat `on_connect` terpicu lagi). Entry yang sudah terkonfirmasi boleh dihapus dari file (rewrite file hanya dengan sisa entry yang belum terkirim).

**Kriteria selesai:** Simulasikan skenario: matikan broker MQTT, biarkan beberapa event masuk ke buffer lokal, nyalakan broker lagi tapi segera `kill -9` proses `main.py` di tengah proses drain (sebelum semua entry terkirim) — restart proses, pastikan entry yang belum terkonfirmasi saat mati masih ada di buffer dan berhasil dikirim ulang, bukan hilang.

### 8.3 Tambah healthcheck untuk semua service (Temuan #12)

**File:** `docker-compose.yml`, dan tambahan endpoint kecil di masing-masing proses

Saat ini hanya `api` dan `mosquitto` yang punya healthcheck. Tambahkan:

1. **Untuk `edge_a` dan `edge_b`** (proses `main.py`): karena proses ini tidak punya HTTP server bawaan (kecuali MJPEG stream), gunakan pendekatan **file heartbeat** — `main.py` menulis timestamp ke file `data/health/edge_{gerbang_id}.heartbeat` setiap kali berhasil memproses satu frame (atau setiap beberapa detik, jangan setiap frame agar tidak membebani I/O). Healthcheck Docker mengecek apakah file ini dimodifikasi dalam N detik terakhir:
   ```yaml
   healthcheck:
     test: ["CMD", "python", "-c", "import time,sys; import os; p='data/health/edge_gerbang_a.heartbeat'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<30 else 1)"]
     interval: 20s
     timeout: 5s
     retries: 3
     start_period: 30s
   ```
2. **Untuk `consumer`** (proses `mqtt_consumer.py`): pendekatan sama — tulis heartbeat file setiap kali `on_message` berhasil diproses, atau setiap loop MQTT tetap hidup (mis. setiap 10 detik via timer terpisah agar tidak bergantung hanya pada ada-tidaknya pesan masuk).

**Kriteria selesai:** Simulasikan proses `main.py` hang (mis. sengaja infinite loop tanpa update heartbeat) — dalam beberapa healthcheck interval, `docker ps` menunjukkan container berstatus `unhealthy`, dan karena `restart: unless-stopped` sudah ada di compose, Docker akan me-restart container tersebut otomatis.

### 8.4 Backup database otomatis (Temuan #13)

**File baru:** `scripts/backup_database.sh`, tambahan service di `docker-compose.yml`

1. Buat skrip bash sederhana yang menjalankan `pg_dump` ke file terkompresi dengan nama mengandung timestamp, disimpan ke folder `data/backups/`.
2. Tambahkan **cron job** (baik via `cron` di host, atau service tambahan `backup` di `docker-compose.yml` yang menjalankan skrip ini setiap N jam menggunakan image `postgres` kecil dengan `cron`/loop sleep sederhana).
3. Kebijakan retensi: simpan 30 hari backup harian + 12 bulan backup bulanan (hapus backup harian yang lebih tua dari 30 hari, tapi pertahankan 1 backup per bulan untuk histori jangka panjang) — mirip pola retensi log yang sudah ada di `logger.py`, cukup diterapkan level lebih besar untuk database.
4. Dokumentasikan **cara restore** di README (Tahap 6, bagian Disaster Recovery) — `pg_restore` dari file backup, urutan langkah yang benar.

**Kriteria selesai:** Backup file baru muncul di `data/backups/` sesuai jadwal. Lakukan restore test di database terpisah (bukan database produksi), pastikan data yang di-restore identik dengan yang di-backup.

### 8.5 Resource limits per service (Temuan #14)

**File:** `docker-compose.yml`

Tambahkan `deploy.resources.limits` untuk setiap service, khususnya `edge_a`/`edge_b` (paling boros CPU karena inference YOLO):
```yaml
edge_a:
  # ... konfigurasi yang sudah ada ...
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
      reservations:
        cpus: '1.0'
        memory: 1G
```
Sesuaikan angka berdasarkan hasil pengukuran aktual (jalankan `docker stats` saat sistem berjalan normal untuk melihat pemakaian riil, baru tentukan limit yang realistis — jangan menebak angka tanpa data).

**Kriteria selesai:** Jalankan `docker stats`, pastikan tidak ada satu container yang memakai >90% CPU host secara terus-menerus sehingga mengganggu service lain (`api`, `consumer`) — kalau limit terlalu ketat sehingga FPS drop drastis, naikkan bertahap sambil dipantau.

### 8.6 Kebijakan retensi data historis di database (Temuan #15)

**File:** `src/database.py`, atau skrip cron baru `scripts/arsipkan_data_lama.py`

1. Tambahkan fungsi/skrip terjadwal (jalan mingguan, via cron atau `threading.Timer` di `mqtt_consumer.py` seperti pola `jadwalkan_reset()` yang sudah ada) yang mengarsipkan baris `hitungan_kendaraan` dan `status_ruas` yang lebih tua dari **N hari** (tentukan bersama, sarankan 90 hari sebagai default awal karena cukup untuk analisis tren musiman tanpa database membengkak tanpa batas) ke file CSV/Parquet terkompresi di `data/archives/`, baru hapus dari tabel utama setelah berhasil diarsipkan.
2. **Jangan hapus tanpa arsip** — data ini berharga untuk publikasi jurnal Anda; tujuannya menjaga tabel utama tetap ramping untuk query real-time, bukan membuang histori.

**Kriteria selesai:** Jalankan skrip arsip secara manual sekali, pastikan file arsip berisi data yang benar dan baris yang diarsipkan sudah tidak ada lagi di tabel utama (tapi masih bisa dibaca ulang dari file arsip jika dibutuhkan).

### 8.7 Watchdog dengan aksi nyata, bukan cuma logging (Temuan #16)

**File:** `src/watchdog.py`

1. Saat `max_ram_percent` atau `max_temp_c` terlampaui, selain logging (yang sudah ada), tambahkan **notifikasi keluar sistem** — cara paling murah untuk prototipe: kirim pesan ke **Telegram Bot** (butuh 1 bot token gratis dan chat ID, request HTTP sederhana tanpa library tambahan) atau **webhook Discord** (serupa, gratis, setup lebih cepat dari Telegram untuk sebagian orang). Pilih salah satu sesuai yang paling mudah Anda setup.
2. Tambahkan **cooldown** pada notifikasi (mis. jangan kirim notifikasi yang sama lebih dari 1x per 15 menit) — mencegah spam notifikasi jika kondisi kritis bertahan lama.
3. Opsional (jika suhu/RAM sangat kritis, misal >95%): panggil aksi mitigasi otomatis, misal menaikkan `frame_skip` sementara (mengurangi beban inference) via update runtime ke `detector.py`, bukan cuma pasif menunggu manusia bertindak.

**Kriteria selesai:** Simulasikan kondisi RAM tinggi (mis. jalankan proses lain yang memakan RAM banyak bersamaan), pastikan notifikasi benar-benar sampai ke Telegram/Discord dalam waktu wajar, dan tidak spam berulang-ulang untuk kondisi yang sama.

### 8.8 Runbook Disaster Recovery (Temuan #17)

**File baru:** `docs/RUNBOOK_DISASTER_RECOVERY.md`

Dokumen operasional singkat (bukan bagian dari README utama, dokumen terpisah untuk situasi darurat) berisi:
1. **Skenario 1: Server mati total.** Langkah: provision server baru → install Docker → clone repo → restore `.env` dari backup terenkripsi terpisah (jangan simpan `.env` di backup yang sama dengan database) → restore database dari backup terbaru (Tahap 8.4) → `docker compose up -d` dengan urutan service yang benar (`mosquitto` dulu, tunggu healthy, baru `api`/`consumer`/`edge_*`).
2. **Skenario 2: Kamera fisik rusak/dicuri.** Langkah: set `aktif: false` sementara di config gerbang terkait, sistem tetap jalan dengan 1 kamera (fallback ke mode `flow_x_traveltime` yang sudah ada otomatis di `occupancy_estimator.py` saat kamera <2 aktif — **ini sudah bekerja otomatis, tinggal didokumentasikan**).
3. **Skenario 3: Database corrupt.** Langkah: stop `consumer` dan `api` → restore dari backup terakhir → jalankan `setup_database.sql` untuk memastikan skema terbaru (idempoten, aman diulang) → restart service.
4. **Kontak/eskalasi**: siapa yang dihubungi jika Anda tidak bisa diakses (relevan jika proyek ini nantinya diserahterimakan ke operator Dishub).

**Kriteria selesai:** Runbook ini diuji minimal sekali secara manual (idealnya di lingkungan staging/testing, bukan produksi) untuk memastikan langkah-langkahnya benar-benar bisa diikuti orang lain (bukan hanya Anda) tanpa pengetahuan tersembunyi yang tidak tertulis.

---

## URUTAN EKSEKUSI YANG DISARANKAN

Urutan ini mempertimbangkan: risiko keamanan ditutup dulu, lalu fitur yang paling terasa manfaatnya sehari-hari, baru kematangan produksi jangka panjang, dan dokumentasi/polish di akhir setelah semua fungsi stabil.

1. **Tahap 4** (keamanan) — cepat, murah, menutup risiko sebelum banyak bereksperimen dengan fitur baru.
2. **Tahap 3** (reset counter) — fitur yang paling langsung dibutuhkan untuk kemudahan testing sehari-hari.
3. **Tahap 1** (kalibrasi visual) — paling besar dampaknya untuk kemudahan kerja lapangan nanti.
4. **Tahap 2** (admin panel + log) — melengkapi kebutuhan monitoring.
5. **Tahap 5** (deteksi offline/online) — pelengkap Tahap 2, membuat data admin panel lebih berguna.
6. **Tahap 8** (production hardening) — setelah fitur inti stabil, baru perkuat ketahanan jangka panjang. Bisa dikerjakan sub-bagian per sub-bagian (8.1 → 8.8) karena masing-masing cukup independen satu sama lain.
7. **Tahap 6** (README) — setelah semua fitur di atas selesai, supaya README mendokumentasikan kondisi final, bukan kondisi yang akan berubah lagi.
8. **Tahap 7** (UI/UX polish) — paling akhir, setelah semua fungsi benar dan stabil, baru "dipercantik".

Setiap tahap sebaiknya di-commit terpisah ke git (`git commit` per tahap/sub-tahap selesai) supaya jika ada regresi, mudah dilacak penyebabnya. Untuk Tahap 8 khususnya, disarankan membuat branch terpisah (`hardening/tahap-8`) dan uji menyeluruh sebelum merge ke `main`, karena perubahan di tahap ini menyentuh banyak proses yang berjalan bersamaan (edge, consumer, database) — regresi di sini lebih sulit dilacak dibanding perubahan UI murni.
