# 🚦 Sitinjau Lauik AI Traffic Monitoring System

![Status](https://img.shields.io/badge/Status-Prototype%20%2F%20Validasi%20Lapangan-yellow)
![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![AI](https://img.shields.io/badge/AI-YOLOv8-orange.svg)
![IoT](https://img.shields.io/badge/Protocol-MQTT-yellow.svg)
![Database](https://img.shields.io/badge/Database-PostgreSQL-informational.svg)

<div align="center">
  <img src="docs/screencapture-localhost-8000-2026-08-27-11_29_08.png" alt="Dashboard Sitinjau Lauik" width="100%">
</div>

Sistem cerdas berbasis **Computer Vision (AI)** dan **Internet of Things (IoT)** untuk mendeteksi, menghitung, dan menganalisis tingkat kemacetan lalu lintas secara *real-time* di ruas jalan ekstrem **Sitinjau Lauik (Padang - Solok)**. 

Proyek ini dirancang secara khusus untuk berjalan di *Edge Device* (seperti **Raspberry Pi 8GB/16GB**) terhubung ke **2 Kamera CCTV (Gerbang Padang Besi & Gerbang Jembatan Timbang Solok)**, menggunakan jaringan nirkabel/Wi-Fi dengan lalu lintas data yang sangat efisien.

---

## 🏗️ 1. Arsitektur Sistem (Event-Driven Microservices)

Sistem dibagi menjadi 4 layer utama yang saling lepas (*decoupled*) agar tangguh, efisien, dan *scalable*:

1. **Edge AI Layer (`src/main.py`)** - *Berjalan di Raspberry Pi (Edge)*
   - Membaca RTSP stream dari 2 CCTV secara multi-threading.
   - Deteksi objek dengan model **YOLOv8 Nano** (teroptimasi 320x320) atau versi NCNN/ONNX.
   - Melacak pergerakan (*ByteTrack*) dan menghitung kendaraan yang melewati garis imajiner (*Line Crossing*).
   - Mengirim data JSON agregasi yang sangat ringan setiap 20 detik ke pusat menggunakan protokol MQTT.
   - Dilengkapi *Watchdog* otomatis untuk pemantauan suhu dan memori.
2. **Transport Layer (MQTT Broker)** - *Jembatan Komunikasi*
   - Menggunakan **Eclipse Mosquitto**.
   - Dilengkapi sistem *Local Buffer* 5MB (data tidak hilang meski sinyal Wi-Fi putus sementara) dan *Last Will and Testament (LWT)* untuk mendeteksi status kamera (Aktif/Offline).
3. **Core Server Layer (`src/mqtt_consumer.py`)** - *Berjalan di Server Pusat*
   - Berlangganan topik MQTT dan menerima data dari kedua gerbang secara asinkron.
   - Menghitung **Occupancy** ruas (selisih kumulatif masuk vs keluar antar gerbang).
   - Menjalankan **occupancy-based congestion detection** sebagai status operasional utama, plus **MKJI 1997 sebagai metrik pembanding** (bukan pengganti).
   - Menyimpan seluruh raw counter, status agregasi, dan matriks ke **PostgreSQL**.
4. **Presentation Layer (`src/api_server.py`)** - *Dashboard UI*
   - REST API (FastAPI) mem-push data terbaru menggunakan **WebSocket** ke antarmuka web HTML/JS.
   - Dashboard menampilkan status occupancy (LANCAR/PADAT/MACET) sebagai metrik utama, plus V/C MKJI sebagai info sekunder.

---

## 📊 2. Logika Perhitungan & Metodologi

Pendekatan Occupancy-Based Congestion Detection: status kemacetan dihitung dari rasio kepadatan kendaraan riil di ruas jalan (occupancy ratio) terhadap kapasitas volumetrik ruas (KVR), dikombinasikan dengan indikator kecepatan rata-rata (speed override) untuk menangkap kondisi bottleneck event-driven (mis. kendaraan mogok). Pendekatan ini termasuk kategori metodologi occupancy/density-based dalam teori aliran lalu lintas (traffic flow theory), **berbeda** dari pendekatan V/C ratio Manual Kapasitas Jalan Indonesia (MKJI) 1997 yang berbasis rasio arus (flow) per jam. MKJI 1997 dihitung secara paralel sebagai metrik pembanding (lihat [docs/METODOLOGI_PERHITUNGAN.md](docs/METODOLOGI_PERHITUNGAN.md)).

Sistem ini adalah **congestion monitor**, bukan prediktor kecelakaan.

### A. Metrik utama — occupancy / KVR (sistem pakar)

```
Occupancy = max(0, kumulatif masuk satu ujung − kumulatif keluar ujung lain)
Volume_meter_lajur = Σ (jumlah[kelas] × panjang_fisik[kelas])
KVR = (L × pct_sempit × 2) + (L × pct_lebar × 6)
Persentase_kepadatan = Volume / KVR × 100%
```

Status: LANCAR / PADAT / MACET dari ambang `ambang_lancar` / `ambang_padat` di config. Jika kecepatan rata-rata < ambang (bisa dipisah naik/turun), status di-override ke MACET.

Kolom `rasio_vc` di database untuk status utama adalah occupancy ratio, **bukan** V/C MKJI.

### B. Metrik pembanding — MKJI 1997 (indikatif)

```
C = C0 × FCw × FCsp × FCsf × FCcs
```

C0 = 2900 smp/jam (jalan 2/2 UD). Volume 15 menit × 4 → smp/jam dengan EMP gunung. **Catatan:** gradien Sitinjau Lauik ~20–26% melebihi cakupan normal MKJI; gunakan dengan hati-hati.

### C. Keterbatasan yang disengaja

Jangan diklaim sebagai implementasi MKJI murni, sistem prediksi kecelakaan, atau perangkat safety-critical. Ambang 44%/84% dan 15 km/jam adalah titik awal sampai divalidasi observasi lapangan (`docs/HASIL_VALIDASI_LAPANGAN.md`).

---

## 💻 3. Teknologi (Tech Stack)

- **AI/Computer Vision**: `Ultralytics YOLOv8`, `ByteTrack`, `OpenCV`
- **Internet of Things (IoT)**: `Paho-MQTT`, `Eclipse Mosquitto`
- **Backend / Core Engine**: `Python 3.11+`, `FastAPI`, `Uvicorn`, `Psycopg2`
- **Database**: `PostgreSQL` (Relasional & Time-Series Friendly)
- **Frontend Dashboard**: Vanilla HTML5/CSS3 (Glassmorphism), `Chart.js`, WebSockets
- **Deployment & Orchestration**: `Docker`, `Docker Compose`

---

## ✨ 4. Fitur Utama & Kegunaan

1. **Dual Gate Monitoring**: Menghitung selisih (Occupancy Net) antara kendaraan masuk dari Padang dan keluar di Solok, dan sebaliknya.
2. **Rolling Average Calculation**: Mengolah *noise* interval MQTT (20 detik) menggunakan buffer riwayat 15 menit ke database, meminimalisir lag/angka 0 pada tampilan V/C Ratio.
3. **Live Camera Feed**: Penayangan video *Multi-Stream* (*Motion JPEG*) dari Edge Device langsung ke Command Center Web dengan latensi minimal.
4. **Interactive Dashboard**: status occupancy utama, V/C MKJI sekunder, breakdown kendaraan, tren historis, notifikasi sensor.
5. **Connection & Hardware Watchdog**: Deteksi *stale data* jika MQTT terputus, dan pemantauan termal CPU/RAM untuk auto-reboot Raspberry Pi agar umur perangkat awet.
6. **Auto Database Persistence**: Setiap kalkulasi dan rekaman metrik terekam secara persisten untuk keperluan audit kelak (e.g., Export to CSV, dll).

---

## 🚀 5. Cara Menjalankan Sistem (Quick Start)

Metode termudah untuk menjalankan proyek ini pada tahap prototipe/demo adalah menggunakan Docker.

### 1. Kloning Repository & Persiapan Lingkungan
```bash
git clone https://github.com/MAHEZANOVRAYUDA/Computer-Vision-Sitinjau-Lauik.git
cd Computer-Vision-Sitinjau-Lauik

# Konfigurasi file .env (ubah kredensial database sesuai kebutuhan)
cp .env.example .env
```

### 2. Jalankan Seluruh Infrastruktur dengan Docker
Sistem sudah dilengkapi dengan multi-stage Dockerfile yang ringan.
```bash
# Menjalankan Database, MQTT Broker, Edge Nodes, Consumer, dan API
docker compose up -d
```
*Perintah ini otomatis akan menjalankan:*
- `sitinjau_mqtt` (Mosquitto Broker)
- `sitinjau_db` (PostgreSQL - *jika di-enable pada compose*)
- `sitinjau_edge_a` (AI Node Gerbang Padang Besi)
- `sitinjau_edge_b` (AI Node Gerbang Solok)
- `sitinjau_consumer` (occupancy + MKJI pembanding)
- `sitinjau_api` (Backend & Dashboard Server)

### 3. Akses Dashboard
Buka browser dan akses:
- **Dashboard Live:** `http://localhost:8000/dashboard`
- **Cek Status Health:** `docker compose ps`

---

## 🔧 6. Menjalankan Tanpa Docker (Manual)

Bagi yang ingin men-debug atau *tuning* parameter secara langsung di IDE:

1. Buat Virtual Environment & Install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Di Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Pastikan **PostgreSQL** dan **Mosquitto** berjalan di perangkat lokal Anda.
3. Jalankan Consumer (Server Pusat):
   ```bash
   python src/mqtt_consumer.py
   ```
4. Jalankan Edge AI Node (Buka terminal baru):
   ```bash
   python src/main.py --config config/config_gerbang_a.yaml
   ```
5. Buka terminal baru dan Jalankan API Dashboard:
   ```bash
   python src/api_server.py
   ```

---

## 📂 7. Struktur Direktori Utama

```text
📦 Computer-Vision-Sitinjau-Lauik
 ┣ 📂 config/            # File YAML untuk konfigurasi sensitivitas deteksi, dll
 ┣ 📂 dashboard/         # Antarmuka web HTML/JS & WebSocket & Aset
 ┣ 📂 models/            # Tempat menyimpan file .pt (YOLO weights)
 ┣ 📂 scripts/           # Script utilitas & database (kalibrasi, evaluasi, setup.sql)
 ┣ 📂 src/
 ┃ ┣ 📜 api_server.py    # FastAPI & WebSocket server
 ┃ ┣ 📜 database.py      # PostgreSQL Connection Pooling
 ┃ ┣ 📜 detector.py      # Integrasi Ultralytics YOLO & ByteTrack
 ┃ ┣ 📜 event_publisher.py # Modul MQTT Edge + Auto Recovery Buffer
 ┃ ┣ 📜 main.py          # Entry point Edge (Raspberry Pi)
 ┃ ┣ 📜 mkji.py          # MKJI 1997 sebagai metrik pembanding (bukan status utama)
 ┃ ┣ 📜 model_optimizer.py # Eksportir model ke ONNX/NCNN untuk PI
 ┃ ┣ 📜 mqtt_consumer.py # Server pengolah metrik dari seluruh gerbang
 ┃ ┣ 📜 sistem_pakar.py  # Hybrid Rule-Based Evaluation
 ┃ ┣ 📜 video_source.py  # Asynchronous multi-threading Video Capture
 ┃ ┗ 📜 watchdog.py      # Pemonitor suhu & RAM khusus Raspberry Pi
 ┣ 📜 docker-compose.yml # Orkestrasi Production
 ┣ 📜 Dockerfile         # Image Builder Edge/Core
 ┗ 📜 README.md          # Dokumentasi ini
```

---

*Dikembangkan secara intensif dan profesional untuk memecahkan tantangan lalu lintas ekstrem Sitinjau Lauik dengan teknologi AI terdepan dan parameter validasi nyata lalu lintas.*
