# 🚦 Sitinjau Lauik - Computer Vision Traffic Monitoring

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-green.svg)
![YOLO](https://img.shields.io/badge/YOLO-v8-yellow.svg)

Sistem pemantauan lalu lintas pintar (Intelligent Traffic Monitoring System) berbasis *Computer Vision* yang dirancang khusus untuk mendeteksi, menghitung, dan menganalisis volume serta kepadatan kendaraan di jalur ekstrem **Sitinjau Lauik**. Sistem ini mengintegrasikan deteksi objek *real-time* dengan YOLO, pelacakan dengan ByteTrack, serta arsitektur pub-sub MQTT untuk mendistribusikan data ke *dashboard* analitik.

---

## ✨ Fitur Utama

- **Deteksi & Klasifikasi Akurat**: Mendeteksi berbagai kelas kendaraan (Motor, Mobil, Truk Ringan, Truk Berat, Bus) secara *real-time* menggunakan model YOLO.
- **Tracking & Counting**: Dilengkapi pelacakan objek (ByteTrack) yang stabil dan mekanisme garis hitung (*counting line*) cerdas yang mampu membedakan arah (naik/turun).
- **Pengukuran Metrik MKJI**: Mampu mengestimasi kecepatan rata-rata, okupansi ruang jalan, serta menghitung kepadatan lalu lintas sesuai standar Manual Kapasitas Jalan Indonesia (MKJI).
- **Distribusi Data dengan MQTT**: Mengirimkan metrik secara berkala dan ringan menggunakan protokol MQTT, memungkinkan skalabilitas dan integrasi dengan sistem *dashboard* eksternal.
- **Sistem Pakar Kemacetan**: Menganalisis tingkat keparahan kemacetan secara otomatis menggunakan logika *rule-based* (Sistem Pakar).
- **Hardware Watchdog**: Memantau kesehatan sistem seperti penggunaan CPU, RAM, dan Suhu (pada perangkat Edge) untuk mencegah *overheating* atau memori penuh.
- **Live Video Streaming**: Mendukung stream video MJPEG ke *browser* untuk visualisasi langsung (*live dashboard*).
- **PUPR Command Center Dashboard**: Antarmuka web tangguh dengan skema warna spesifik (PUPR Solid Navy & Kuning) yang didesain agar tidak memicu kelelahan mata (*eye strain-free*) saat digunakan untuk *monitoring* berjam-jam.

---

## 🏗️ Arsitektur Sistem

Sistem ini dirancang untuk dapat dijalankan secara tersebar (*distributed*):
1. **Edge Node (Kamera / Sumber Video)**: Menjalankan `src/main.py`. Node ini membaca frame dari kamera/RTSP, menjalankan inferensi AI, dan mengirimkan hasil agregasi (bukan frame video penuh) melalui MQTT.
2. **Message Broker**: Menggunakan Mosquitto MQTT untuk menjembatani komunikasi data.
3. **Consumer Server**: Menjalankan `src/mqtt_consumer.py`. Menerima data dari MQTT, menghitung agregasi (termasuk algoritma MKJI & Sistem Pakar), dan menyimpan ke PostgreSQL.
4. **API Server & Dashboard**: Menjalankan `src/api_server.py`. Menyediakan API (FastAPI) dan melayani antarmuka web interaktif melalui WebSocket.

---

## 🚀 Panduan Instalasi (Instalasi Lokal)

### 1. Persiapan Kebutuhan Sistem
Pastikan sistem Anda telah terinstal:
- **Python** (versi 3.9 ke atas)
- **Git**
- **MQTT Broker** (misal: Eclipse Mosquitto)

### 2. Kloning Repositori
```bash
git clone https://github.com/MAHEZANOVRAYUDA/Computer-Vision-Sitinjau-Lauik.git
cd Computer-Vision-Sitinjau-Lauik
```

### 3. Setup Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# Install dependensi utama
pip install -r requirements.txt
```

### 4. Setup Database, MQTT, dan Menjalankan Sistem
Sistem membutuhkan PostgreSQL dan Mosquitto MQTT. Cara termudah (dan direkomendasikan untuk production) adalah menggunakan Docker:

```bash
# Menjalankan seluruh stack (Database, MQTT, Consumer, API, Edge)
docker-compose up -d
```
*Dashboard dapat diakses di `http://localhost:8000`*

## 🔧 Panduan Kalibrasi Garis Virtual (Admin Panel)

Mulai versi v3, sistem dilengkapi dengan **Admin Panel** khusus agar konfigurasi gerbang dan garis batas tidak perlu lagi mengedit `config.yaml` secara manual.

1. Buka dashboard di browser (`http://localhost:8000`).
2. Klik tombol navigasi (atau akses langsung ke `http://localhost:8000/login.html`) untuk masuk ke halaman Login.
3. Gunakan kredensial admin Anda untuk login.
4. Di dalam **Admin Panel**, pindah ke *tab* **Kalibrasi Garis Virtual**. Pilih Gerbang yang ingin disesuaikan (Gerbang A atau B).
5. Geser titik garis secara interaktif pada *snapshot* kamera menggunakan *mouse*, lalu klik **Simpan Konfigurasi Garis**. Log perubahan akan langsung tercatat, dan algoritma *Counting* akan otomatis menggunakan garis batas yang baru.

---

## ⚙️ Konfigurasi

Semua pengaturan sistem dapat dikelola melalui file `config/config.yaml`.
Anda dapat menyalin contoh konfigurasi dan menyesuaikannya:

```bash
cp .env.example .env
```
Sesuaikan parameter pada file `config.yaml` atau spesifik per-gerbang seperti `config_gerbang_a.yaml`. Parameter penting meliputi:
- `video_source`: Path file video, RTSP URL, atau ID WebCam.
- `mqtt`: Alamat host dan port broker.
- `model`: Path menuju file bobot (*weight*) YOLO (`.pt`).
- `counting_line`: Koordinat poligon dan garis hitung.

---

## 💻 Cara Menjalankan

### Menjalankan Tanpa Docker (Pengembangan)
Jika Anda ingin mengembangkan sistem tanpa Docker, Anda harus menjalankan tiga komponen ini di terminal terpisah:

```bash
# 1. Jalankan Consumer (Pemroses MQTT -> Database)
python src/mqtt_consumer.py

# 2. Jalankan API Server (Dashboard Web)
python src/api_server.py

# 3. Jalankan Edge (Pemrosesan Video/Kamera)
python src/main.py --config config/config_gerbang_a.yaml
```
Tekan tombol `q` pada jendela video edge untuk menghentikan deteksi.

### Menjalankan Pengujian (Testing)
Sistem ini menggunakan kerangka kerja `pytest`. Untuk memastikan semua modul logika berjalan baik:
```bash
python -m pytest
```

---

## 📁 Struktur Direktori

```text
sitinjau-lauik-cv/
├── config/              # File konfigurasi YAML (Global, Gerbang A, Gerbang B)
├── dashboard/           # Antarmuka web (HTML/JS) untuk visualisasi
├── data/                # Data lokal (log, snapshot, sqlite)
├── docs/                # Dokumentasi proyek (Metodologi, PRD)
├── models/              # Tempat menaruh model weights YOLO
├── scripts/             # Skrip utilitas (kalibrasi, fine-tune, dll)
├── src/                 # KODE SUMBER UTAMA (Detector, Tracker, MQTT, Logger)
├── tests/               # Unit testing untuk modul core
├── README.md            # Dokumentasi ini
├── requirements.txt     # Daftar dependensi Python
└── docker-compose.yml   # Konfigurasi Docker (Opsional)
```

---

---

## 📊 Metodologi Perhitungan & Rumus Inti

Sistem ini menjalankan **dua metodologi berbeda** secara paralel. Metrik utama pada dashboard menggunakan pendekatan *Occupancy-Based*, sedangkan standar MKJI 1997 digunakan murni sebagai metrik pembanding (indikatif).

### 1. Occupancy-Based Congestion Detection (Metrik Utama)
Status kemacetan dihitung dari rasio kepadatan kendaraan riil di ruas jalan terhadap Kapasitas Volumetrik Ruas (KVR). Ini sangat relevan untuk medan ekstrem seperti Sitinjau Lauik di mana kemacetan lebih sering dipicu oleh *bottleneck* spasial (seperti truk panjang yang mogok) daripada sekadar volume kendaraan yang tinggi.

**A. Rumus Occupancy (Kekekalan Kendaraan):**
Dengan asumsi 2 gerbang (A = Padang Basi, B = Solok):
```text
Occupancy(A→B, kelas) = max(0, Kumulatif_Masuk_A[kelas] - Kumulatif_Keluar_B[kelas])
Occupancy(B→A, kelas) = max(0, Kumulatif_Masuk_B[kelas] - Kumulatif_Keluar_A[kelas])
```
*Artinya: Selisih jumlah yang masuk dan yang keluar adalah jumlah riil kendaraan yang sedang berada (terjebak/berjalan) di dalam ruas jalan.*

**B. Rumus Volume Meter-Lajur & Kapasitas Volumetrik Ruas (KVR):**
```text
Volume_meter_lajur = Σ (jumlah_kendaraan[kelas] × panjang_fisik[kelas])

KVR = (panjang_ruas × pct_sempit × kapasitas_lateral_sempit)
    + (panjang_ruas × pct_lebar × kapasitas_lateral_lebar)

Persentase_kepadatan = (Volume_meter_lajur / KVR) × 100%
```
*Catatan: Kolom rasio_vc di dashboard adalah representasi persentase kepadatan ini, bukan V/C MKJI murni.*

**C. Hybrid Speed Override (Deteksi Cepat Kemacetan):**
Jika kecepatan rata-rata terukur < 15 km/jam (ambang bisa dikonfigurasi), status dipaksa **MACET** terlepas dari persentase occupancy. Hal ini dirancang untuk mendeteksi secara instan jika ada truk mogok/kecelakaan yang menyebabkan lalu lintas berhenti, padahal ruas jalan belum penuh terisi.

### 2. Standar MKJI 1997 (Metrik Pembanding Indikatif)
Dihitung dari arus 15 menit terakhir yang diekstrapolasi ke smp/jam.
```text
Kapasitas (C) = C0 × FCw × FCsp × FCsf × FCcs
Rasio V/C = Volume (smp/jam) / Kapasitas
```
- **C0**: 2900 smp/jam (standar jalan 2/2 UD, Tabel 5-2 MKJI 1997)
- **Volume SMP**: Dikonversi menggunakan EMP (Ekuivalen Mobil Penumpang) khusus medan gunung:
  - Motor: 0.4
  - Mobil: 1.0
  - Bus: 3.25
  - Truk (termasuk berat): 5.0
*(Nilai ini menggunakan rentang tengah dari standar pegunungan MKJI).*

> **Disclaimer MKJI**: Gradien Sitinjau Lauik (20-26%) jauh melampaui rentang normal yang menjadi basis riset MKJI 1997. Oleh karena itu, metrik MKJI di sistem ini hanya disediakan sebagai **pembanding akademis** dan sebaiknya tidak digunakan sebagai acuan *safety critical*.

---

## 🛠️ Pemeliharaan dan Troubleshooting

- **Sistem berjalan lambat (FPS rendah)**: Sesuaikan parameter `frame_skip` pada `config.yaml` menjadi lebih tinggi (contoh: 4 atau 5).
- **Video Stream tidak muncul**: Pastikan port MJPEG Streamer (misal: 8000 atau 8001) tidak terblokir oleh Firewall.
- **Koneksi MQTT Gagal**: Pastikan Mosquitto berjalan, dan periksa konfigurasi *host* pada `config.yaml`.

---

*Dikembangkan untuk penelitian, pemantauan, dan manajemen lalu lintas cerdas di wilayah dengan topografi menantang (Sitinjau Lauik).*
