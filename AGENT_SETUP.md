# INSTRUKSI UNTUK AI AGENT — Setup & Jalankan Sistem Deteksi Kemacetan Sitinjau Lauik

> **Untuk AI coding agent (Antigravity, Cursor, Windsurf, Claude Code, dsb):**
> Dokumen ini adalah instruksi eksekusi, bukan dokumen untuk dibaca manusia.
> Jalankan setiap tahap SECARA BERURUTAN. Setiap tahap punya "Kriteria Sukses"
> yang WAJIB diverifikasi sebelum lanjut ke tahap berikutnya. Jika sebuah
> perintah gagal, JANGAN lanjut ke tahap berikutnya — diagnosis dan perbaiki
> dulu, gunakan bagian "Troubleshooting" di bagian bawah file ini.
>
> Konteks proyek: prototipe sistem deteksi kendaraan & kemacetan lalu lintas
> berbasis computer vision (YOLOv8 + ByteTrack), berjalan di Windows dengan
> GPU NVIDIA. **Kamera fisik pengguna sedang bermasalah** — sistem dijalankan
> dulu memakai video file hasil download (mode "file" di config.yaml) untuk
> pengujian lokal. Migrasi ke kamera RTSP tinggal ganti config saat kamera
> sudah siap (lihat Tahap 5B) — tidak ada kode yang perlu diubah.
>
> Environment pengguna saat instruksi ini dibuat: Windows, GPU NVIDIA tersedia,
> PostgreSQL SUDAH terinstall, Mosquitto MQTT BELUM terinstall, status
> PyTorch+CUDA belum diketahui, pengguna SUDAH punya file video traffic hasil
> download sendiri (bukan via kamera).
>
> **Lokasi folder proyek: partisi/drive E:\ (bukan C:\).** Setiap kali
> instruksi di bawah menyebut `cd sitinjau-lauik-cv`, PASTIKAN dulu berada
> di drive E — di PowerShell, `cd` saja TIDAK berpindah drive, harus pakai
> `E:` sebagai perintah terpisah dulu, atau `cd /d` di Command Prompt biasa.
> Contoh urutan yang benar dari awal (sesuaikan path persis dengan lokasi
> ekstrak ZIP pengguna di drive E):
> ```powershell
> E:
> cd E:\sitinjau-lauik-cv
> ```
> Jika sesi terminal baru dibuka dan defaultnya balik ke C:\, ulangi 2 baris
> di atas sebelum menjalankan perintah apa pun dari tahap manapun di bawah.

---

## TAHAP 0 — Deteksi Kondisi Awal (WAJIB dijalankan pertama)

Sebelum melakukan instalasi apa pun, jalankan pengecekan berikut dan laporkan
hasilnya ke pengguna dalam bentuk ringkas sebelum lanjut:

```powershell
# Cek berada di drive & folder proyek yang benar (harus E:\...\sitinjau-lauik-cv)
Get-Location

# Cek Python
python --version

# Cek pip
pip --version

# Cek apakah GPU NVIDIA terdeteksi sistem
nvidia-smi

# Cek apakah PostgreSQL service berjalan
Get-Service -Name postgresql* -ErrorAction SilentlyContinue

# Cek apakah Mosquitto sudah ada
Get-Service -Name mosquitto -ErrorAction SilentlyContinue
where.exe mosquitto 2>$null

# Cek apakah PyTorch sudah terinstall dan apakah CUDA-nya aktif
python -c "import torch; print('torch terinstall:', torch.__version__); print('CUDA aktif:', torch.cuda.is_available())" 2>$null
```

**Kriteria Sukses Tahap 0:** `Get-Location` menunjukkan path di drive `E:\`
(bukan `C:\`), dan berada di dalam atau bisa masuk ke folder
`sitinjau-lauik-cv`. Semua perintah lain di atas berhasil dijalankan
(walau hasilnya "tidak ditemukan" — itu informasi valid, bukan kegagalan).
Catat hasil setiap poin karena akan menentukan tahap mana yang bisa di-skip
di bawah.

---

## TAHAP 1 — Install PyTorch dengan CUDA (skip jika Tahap 0 sudah menunjukkan CUDA aktif)

**Kenapa ini harus dilakukan MANUAL dan TERPISAH dari requirements.txt:**
Jika PyTorch diinstall lewat `pip install -r requirements.txt` secara langsung,
pip akan memasang versi CPU-only karena tidak tahu versi CUDA yang cocok.
Ini membuat YOLO berjalan sangat lambat. Wajib install versi CUDA-nya dulu,
secara eksplisit, SEBELUM requirements.txt.

1. Jalankan `nvidia-smi`, baca angka di kanan atas output pada baris
   "CUDA Version: XX.X" — ini adalah versi CUDA maksimum yang didukung
   driver GPU pengguna (bukan versi yang harus dipasang persis, tapi
   batas atas).

2. Pilih perintah instalasi berdasarkan versi tersebut. Gunakan CUDA 12.4
   sebagai default aman jika versi driver ≥ 12.4:

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

   Jika versi driver di bawah 12.4, gunakan cu121 sebagai gantinya:

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

3. **Verifikasi wajib** setelah instalasi:

```powershell
python -c "import torch; assert torch.cuda.is_available(), 'CUDA TIDAK AKTIF'; print('OK - GPU terdeteksi:', torch.cuda.get_device_name(0))"
```

**Kriteria Sukses Tahap 1:** perintah verifikasi di atas mencetak
`OK - GPU terdeteksi: <nama GPU>` tanpa error AssertionError. Jika muncul
AssertionError, lihat bagian Troubleshooting nomor 1 sebelum lanjut —
JANGAN lanjut ke Tahap 2 dengan CUDA yang belum aktif, karena seluruh
tahap berikutnya bisa "berhasil" secara teknis tapi performa akhir
akan sangat lambat dan menyesatkan saat evaluasi.

---

## TAHAP 2 — Virtual Environment & Dependency Python

```powershell
cd sitinjau-lauik-cv
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**Kriteria Sukses Tahap 2:** `pip install -r requirements.txt` selesai
tanpa error merah. Jalankan verifikasi:

```powershell
python -c "import ultralytics, cv2, yaml, paho.mqtt.client, psycopg2, fastapi; print('Semua library inti berhasil di-import')"
```

Jika ada `ModuleNotFoundError`, itu artinya requirements.txt gagal
terinstall sebagian — cek log pip install di atas untuk nama paket yang
gagal, dan install ulang paket itu secara spesifik.

---

## TAHAP 3 — Install Mosquitto (MQTT Broker) — WAJIB karena belum ada

1. Unduh installer dari https://mosquitto.org/download/ (pilih Windows,
   64-bit).
2. Jalankan installer dengan opsi default (termasuk opsi "Service" tercentang
   supaya berjalan otomatis sebagai Windows Service).
3. Setelah selesai, verifikasi:

```powershell
Get-Service -Name mosquitto
netstat -an | findstr 1883
```

**Kriteria Sukses Tahap 3:** `Get-Service -Name mosquitto` menunjukkan
status `Running`, DAN `netstat` menunjukkan baris dengan port `1883` dan
status `LISTENING`.

**Jika service tidak auto-start** (Status bukan Running), jalankan:

```powershell
Start-Service mosquitto
```

Jika service masih tidak mau start, jalankan broker secara manual untuk
development (buka terminal terpisah, biarkan berjalan):

```powershell
cd "C:\Program Files\mosquitto"
.\mosquitto.exe -v
```

---

## TAHAP 4 — Setup Database (PostgreSQL sudah ada, tinggal buat database & schema)

1. Cek dulu PostgreSQL berjalan dan cari tahu password user `postgres`
   yang di-set pengguna saat instalasi PostgreSQL sebelumnya — **tanyakan
   ke pengguna jika tidak diketahui, jangan menebak password**.

2. Buat database:

```powershell
psql -U postgres -c "CREATE DATABASE sitinjau_lauik_db;"
```

   (akan diminta password — masukkan password PostgreSQL pengguna)

3. Jalankan schema:

```powershell
psql -U postgres -d sitinjau_lauik_db -f scripts/setup_database.sql
```

4. **Update `config/config.yaml`** — cari bagian `database:` dan ganti
   `password: "GANTI_PASSWORD_ANDA"` dengan password PostgreSQL yang
   sebenarnya.

**Kriteria Sukses Tahap 4:** jalankan verifikasi berikut, harus
mengembalikan 4 nama tabel:

```powershell
psql -U postgres -d sitinjau_lauik_db -c "\dt"
```

Tabel yang harus muncul: `ruas_jalan`, `gerbang_kamera`,
`hitungan_kendaraan`, `status_ruas`.

---

## TAHAP 5 — Menyiapkan Video Lokal untuk Pengujian (mode "file")

Pengguna sudah punya file video traffic hasil download sendiri. Pastikan
langkah berikut selesai:

1. **Pastikan file video sudah ada di lokasi yang benar:**

```powershell
Test-Path "data\videos\traffic.mp4"
```

   Jika hasilnya `False`, tanyakan ke pengguna di mana file video mereka
   berada, lalu:
   - Pindahkan/copy file itu ke `data\videos\traffic.mp4`, ATAU
   - Update `config/config.yaml` bagian `video_source.file_path` supaya
     menunjuk ke lokasi file yang sebenarnya (path relatif dari root
     proyek, gunakan forward slash `/` meski di Windows — Python OpenCV
     menerima keduanya).

2. **Pastikan `config/config.yaml` sudah dalam mode file** (seharusnya
   sudah default begini, tapi verifikasi):

```yaml
video_source:
  mode: "file"
  file_path: "data/videos/traffic.mp4"
```

3. **Verifikasi file video bisa dibuka** (test cepat tanpa menjalankan
   seluruh sistem):

```powershell
venv\Scripts\activate
python -c "import cv2; cap = cv2.VideoCapture('data/videos/traffic.mp4'); print('Video bisa dibuka:', cap.isOpened()); ret, frame = cap.read(); print('Frame pertama terbaca:', ret); print('Resolusi asli:', frame.shape if ret else 'N/A')"
```

**Kriteria Sukses Tahap 5:** output menunjukkan `Video bisa dibuka: True`
dan `Frame pertama terbaca: True`. Jika `False`, kemungkinan penyebab:
file corrupt, format codec tidak didukung OpenCV (jarang terjadi untuk
mp4 standar), atau path salah.

**Catatan perilaku sistem dalam mode file:** ketika video mencapai akhir,
`src/main.py` akan otomatis memutar ulang dari awal (loop) supaya
pengujian bisa berjalan terus-menerus tanpa program berhenti sendiri —
Anda akan melihat log `[VIDEO] Video mencapai akhir, memutar ulang dari
awal...` setiap kali ini terjadi. Ini perilaku yang diharapkan, bukan
bug.

---

## TAHAP 5B (nanti, setelah kamera fisik sudah siap) — Migrasi ke RTSP

Bagian ini BELUM perlu dijalankan sekarang — simpan sebagai referensi
untuk saat kamera fisik pengguna sudah bisa dipakai kembali.

1. Cari tahu merek/model kamera. Tanyakan ke pengguna jika tidak
   diketahui — merek menentukan format URL RTSP (Hikvision, Dahua, TP-Link,
   Xiaomi, dsb semua berbeda formatnya).

2. Cari IP address kamera di jaringan lokal. Jika kamera dan laptop
   berada di jaringan WiFi/LAN yang sama, gunakan salah satu cara ini:
   - Buka aplikasi resmi kamera (jika ada, mis. Hik-Connect, gDMSS,
     Dahua Toolbox) — biasanya menampilkan IP address kamera.
   - Atau scan jaringan lokal untuk menemukan perangkat:
     ```powershell
     arp -a
     ```
     Cari entri dengan vendor yang cocok dengan merek kamera.
   - Atau gunakan tool GUI seperti "Advanced IP Scanner" (unduh dari
     https://www.advanced-ip-scanner.com/) untuk melihat semua perangkat
     di jaringan beserta nama/vendornya.

3. Format URL RTSP umum per merek (username/password default SERING
   `admin`/`admin` atau `admin`/kosong — tapi jika kamera sudah pernah
   dikonfigurasi, password bisa sudah diubah, tanyakan ke pengguna):

   | Merek | Format URL RTSP |
   |---|---|
   | Hikvision | `rtsp://user:pass@IP:554/Streaming/Channels/101` |
   | Dahua | `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0` |
   | TP-Link Tapo | `rtsp://user:pass@IP:554/stream1` |
   | Xiaomi/Mi Home | biasanya TIDAK mendukung RTSP langsung tanpa firmware custom |
   | Merek generik ONVIF | `rtsp://user:pass@IP:554/onvif1` (coba beberapa varian path) |

4. WAJIB verifikasi URL di VLC Media Player SEBELUM dicoba di Python —
   ini langkah penting untuk mengisolasi masalah (kalau gagal di VLC,
   masalahnya di jaringan/kredensial, bukan di kode Python):
   - Buka VLC → Media → Open Network Stream → masukkan URL RTSP → Play.
   - Jika video muncul di VLC, URL sudah benar dan siap dipakai di
     `config/config.yaml`.

5. Setelah URL terverifikasi jalan di VLC, update `config/config.yaml`:

```yaml
video_source:
  mode: "rtsp"          # ganti dari "file" ke "rtsp"
  rtsp_url: "rtsp://USER:PASS@IP:554/path-yang-sudah-terverifikasi"
```

6. **Kalibrasi ulang garis virtual** — sudut pandang kamera fisik hampir
   pasti berbeda dari video simulasi, jadi garis virtual lama TIDAK
   berlaku lagi. Jalankan ulang `python scripts/kalibrasi_garis.py`
   setelah beralih ke mode RTSP.

**Kriteria Sukses Tahap 5B:** video kamera berhasil tampil di VLC dengan
URL yang sama seperti yang dimasukkan ke `config.yaml`, DAN kalibrasi
garis virtual sudah diulang untuk sudut pandang kamera fisik yang baru.

---

## TAHAP 6 — Unit Test (WAJIB sebelum menjalankan sistem penuh)

```powershell
pytest tests/ -v
```

**Kriteria Sukses Tahap 6:** semua test menunjukkan `PASSED` (total 18 test
di `test_counting_line.py` dan `test_sistem_pakar.py`). Jika ada yang
`FAILED`, JANGAN lanjut ke Tahap 7 — ini indikasi bug di logika inti yang
harus diperbaiki dulu, bukan masalah environment.

---

## TAHAP 6B — Kalibrasi Garis Virtual (WAJIB untuk video yang dipakai saat ini)

Setelah video di Tahap 5 terverifikasi bisa dibuka, jalankan:

```powershell
python scripts/kalibrasi_garis.py
```

Ikuti instruksi di jendela yang muncul: klik 4 titik (2 untuk lajur kiri,
2 untuk lajur kanan). Salin hasil YAML yang tercetak di terminal ke bagian
`lajur:` di `config/config.yaml`, menggantikan nilai default yang ada.

**Kriteria Sukses:** `config/config.yaml` bagian `lajur:` sudah berisi
koordinat hasil klik manual, bukan lagi nilai default `[100, 400]` dst.

---

## TAHAP 7 — Menjalankan Sistem Penuh (3 proses paralel)

Jalankan 3 proses berikut di 3 terminal terpisah (agent: gunakan
kemampuan multi-terminal/background process jika tersedia; jika tidak,
instruksikan pengguna untuk membuka 3 jendela terminal manual).

**Terminal 1 — Edge (deteksi):**
```powershell
cd sitinjau-lauik-cv
venv\Scripts\activate
python src\main.py
```
Kriteria sukses: jendela video muncul menampilkan feed video file dengan
bounding box hijau di sekitar kendaraan terdeteksi, dan garis virtual
kuning/magenta terlihat di posisi yang sudah dikalibrasi. Video akan
otomatis loop dari awal saat mencapai akhir (lihat catatan Tahap 5).

**Terminal 2 — Server (sistem pakar):**
```powershell
cd sitinjau-lauik-cv
venv\Scripts\activate
python src\mqtt_consumer.py
```
Kriteria sukses: setelah ~20 detik (1 interval agregasi sesuai
config.yaml saat ini), terminal menampilkan log
`[Sistem Pakar] Occupancy total: ... Status: ...`

**Terminal 3 — Dashboard:**
```powershell
cd sitinjau-lauik-cv
venv\Scripts\activate
python src\api_server.py
```
Kriteria sukses: buka browser ke `http://localhost:8000`, dashboard
menampilkan status (lancar/padat/macet) yang match dengan log Terminal 2.

---

## KRITERIA SUKSES KESELURUHAN

Sistem dianggap berhasil berjalan penuh jika SEMUA berikut benar secara
bersamaan:
1. Terminal 1 menampilkan video dengan deteksi kendaraan real-time
2. Terminal 2 mencetak log status setiap ~60 detik tanpa error
3. Dashboard di browser menampilkan angka yang berubah/update setiap
   beberapa detik (bukan macet di "MENUNGGU DATA" terus-menerus)
4. Angka di dashboard match dengan yang dicetak di Terminal 2

Jika ke-4 poin ini terpenuhi, sistem prototipe berhasil berjalan end-to-end.

---

## TROUBLESHOOTING

### 1. `AssertionError: CUDA TIDAK AKTIF` di Tahap 1
- Uninstall dulu: `pip uninstall torch torchvision -y`
- Cek ulang versi CUDA driver dengan `nvidia-smi`
- Coba index-url versi CUDA yang berbeda (cu121, cu118) — daftar lengkap
  ada di https://pytorch.org/get-started/locally/
- Pastikan tidak ada instalasi PyTorch versi CPU yang tertinggal
  (`pip list | findstr torch` harus hanya menunjukkan 1 versi)

### 2. `psql: command not found` di Tahap 4
PostgreSQL terinstall tapi folder `bin`-nya belum ada di PATH Windows.
Cari lokasi instalasi (biasanya `C:\Program Files\PostgreSQL\<versi>\bin`)
dan tambahkan ke PATH, atau jalankan psql dengan path lengkap.

### 3. Video RTSP gagal terhubung di `src/main.py` padahal sudah jalan di VLC
- Cek apakah `config/config.yaml` menyimpan password dengan karakter
  spesial yang perlu di-escape (mis. `@` dalam password akan bentrok
  dengan format URL `user:pass@ip`) — jika password mengandung `@`,
  ganti password kamera atau gunakan URL-encoding.
- Cek Windows Firewall tidak memblokir aplikasi Python untuk koneksi
  jaringan keluar.

### 4. `[MQTT] PERINGATAN: Tidak berhasil terhubung ke broker`
- Ulangi verifikasi Tahap 3 — pastikan service `mosquitto` statusnya
  `Running`, bukan `Stopped`.

### 5. Semua proses jalan tapi dashboard tetap "MENUNGGU DATA" setelah >2 menit
- Cek Terminal 1 — apakah ada kendaraan yang benar-benar terdeteksi
  melewati garis virtual? Jika video sepi kendaraan, tunggu lebih lama
  atau gunakan video yang lebih ramai untuk testing.
- Cek Terminal 2 — apakah ada error `ERROR menyimpan hitungan ke
  database`? Jika ya, database dari Tahap 4 kemungkinan belum benar.

### 6. FPS sangat rendah / video patah-patah walau GPU aktif
- Turunkan resolusi di `config/config.yaml`:
  `process_width: 640`, `process_height: 360`
- Pastikan `model.weights_path` memakai `yolov8n.pt` (nano, paling ringan),
  bukan varian yang lebih besar (s/m/l/x).

---

## CATATAN UNTUK AGENT: File yang TIDAK BOLEH diubah tanpa alasan kuat

- `src/counting_line.py` — logika ini sudah diuji dengan unit test yang
  ketat (termasuk kasus edge yang sebelumnya pernah jadi bug). Jangan
  refactor tanpa menjalankan `pytest tests/test_counting_line.py -v`
  setelahnya dan memastikan semua tetap PASSED.
- `src/sistem_pakar.py` — nilai ambang batas (0.60, 0.90) dan koefisien
  smp adalah nilai dari standar MKJI yang dikutip di dokumen blueprint
  asli proyek, bukan angka sembarang — jangan diubah tanpa konfirmasi
  eksplisit dari pengguna.
- `src/main.py` bagian `baru_saja_di_loop` dan `src/detector.py` bagian
  `reset_tracker()` — mekanisme ini SENGAJA ada untuk mode file: saat
  video diputar ulang dari awal, tracker YOLO/ByteTrack dan riwayat
  "sudah_dihitung" di counting_line HARUS direset, kalau tidak
  penghitungan pada putaran video kedua dan seterusnya akan salah
  (kendaraan baru bisa dianggap duplikat dari track_id lama). Jangan
  hapus logika ini meski terlihat seperti "kode tambahan yang tidak
  perlu".

File yang AMAN dan MEMANG PERLU disesuaikan pengguna:
- `config/config.yaml` — seluruh isi file ini memang dirancang untuk
  diedit sesuai environment masing-masing.
