# 🚦 Sitinjau Lauik AI Traffic Monitoring System

![Status](https://img.shields.io/badge/Status-Production%20Ready-success)
![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![AI](https://img.shields.io/badge/AI-YOLOv8-orange.svg)
![IoT](https://img.shields.io/badge/Protocol-MQTT-yellow.svg)

Sistem cerdas berbasis **Computer Vision (AI)** dan **Internet of Things (IoT)** untuk mendeteksi, menghitung, dan menganalisis tingkat kemacetan lalu lintas secara *real-time* di ruas jalan ekstrem **Sitinjau Lauik (Padang - Solok)**. 

Proyek ini dirancang secara khusus untuk berjalan di *Edge Device* (seperti **Raspberry Pi 8GB/16GB**) terhubung ke **2 Kamera CCTV (Gerbang Padang Besi & Gerbang Jembatan Timbang Solok)**, menggunakan jaringan nirkabel/Wi-Fi dengan lalu lintas data yang sangat efisien.

---

## 🏗️ 1. Arsitektur Sistem (Event-Driven Microservices)

Sistem dibagi menjadi 4 layer utama yang saling lepas (*decoupled*) agar tangguh, efisien, dan *scalable*:

1. **Edge AI Layer (`src/main.py`)** - *Berjalan di Raspberry Pi (Edge)*
   - Membaca RTSP stream dari 2 CCTV secara multi-threading.
   - Deteksi objek dengan model **YOLOv8 Nano** (teroptimasi 416x416).
   - Melacak pergerakan (*ByteTrack*) dan menghitung kendaraan yang melewati garis (*Line Crossing*).
   - Hanya mengirim data JSON super-ringan setiap 20 detik ke pusat. (Dilengkapi *Watchdog* otomatis).
2. **Transport Layer (MQTT Broker)** - *Jembatan Komunikasi*
   - Menggunakan **Eclipse Mosquitto**.
   - Dilengkapi sistem *Local Buffer* 5MB (data tidak hilang meski sinyal Wi-Fi putus sementara) dan *Last Will and Testament (LWT)*.
3. **Core Server Layer (`src/mqtt_consumer.py`)** - *Berjalan di Server Pusat*
   - Menerima data dari kedua gerbang secara sinkron.
   - Menghitung **Occupancy** (Selisih kendaraan Masuk vs Keluar).
   - Menjalankan evaluasi kemacetan berdasarkan pedoman **MKJI 1997** dan **Sistem Pakar**.
   - Menyimpan hasil metrik ke dalam database PostgreSQL (*Connection Pooling*).
4. **Presentation Layer (`src/api_server.py`)** - *Dashboard*
   - REST API (FastAPI) yang mem-push data secara *real-time* via **WebSocket** ke browser klien.

---

## 📊 2. Logika Perhitungan & Dasar Teori (Standard MKJI 1997)

Sistem ini tidak hanya menebak kemacetan, melainkan menggunakan standar **Manual Kapasitas Jalan Indonesia (MKJI) 1997** untuk jalan 2/2 UD (Dua Lajur Dua Arah Tak Terbagi):

### A. Kapasitas Jalan ($C$)
Berdasarkan MKJI 1997, Kapasitas Dasar ($C_0$) untuk jalan 2/2 UD adalah konstan: **2900 smp/jam**.
Kapasitas aktual disesuaikan dengan faktor koreksi jalan ekstrem pegunungan:
```text
C = C0 × FCW × FCSP × FCSF × FCCS
Dimana:
C0   = 2900 smp/jam
FCW  = Faktor lebar jalur
FCSP = Faktor pemisahan arah
FCSF = Faktor hambatan samping
FCCS = Faktor ukuran kota
```

### B. Ekuivalensi Mobil Penumpang (EMP)
Karena kontur pegunungan (Sitinjau Lauik), bobot kendaraan berat memakan ruang lebih besar:
- Sepeda Motor (MC): **0.40 smp**
- Kendaraan Ringan / Mobil (LV): **1.00 smp**
- Kendaraan Berat (HV - Bus & Truk): **1.30 smp** (Medan Gunung/Curam)

### C. Level of Service (LOS) & Status
Kepadatan ditentukan dari rasio Volume per Kapasitas (V/C Ratio):
- **LANCAR (LOS A - C)**: V/C Ratio $\le 0.75$
- **PADAT (LOS D - E)**: V/C Ratio $0.76 - 1.00$
- **MACET (LOS F)**: V/C Ratio $> 1.00$

> **Sistem Pakar (Override):** Jika mendeteksi kecepatan rata-rata kendaraan turun drastis (mis. $< 15$ km/jam akibat truk mogok/patah as), status langsung di-override menjadi **MACET**, meskipun V/C Ratio volumetrik masih rendah.

---

## 🛠️ 3. Kebutuhan Perangkat (Prerequisites)

- **Hardware:**
  - Raspberry Pi 4/5 (RAM 8GB atau 16GB direkomendasikan).
  - 2x Kamera CCTV / IP Camera pendukung protokol RTSP.
  - Active Cooler / Heatsink untuk menjaga suhu Pi di bawah 80°C.
- **Software:**
  - Docker & Docker Compose (Paling Direkomendasikan).
  - Python 3.11+
  - PostgreSQL 14+
  - Eclipse Mosquitto (MQTT Broker)

---

## 🚀 4. Cara Menjalankan Sistem (Quick Start)

Metode termudah untuk menjalankan proyek ini pada tahap *production* adalah menggunakan Docker.

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
- `sitinjau_edge_a` (AI Node Gerbang Padang Besi)
- `sitinjau_edge_b` (AI Node Gerbang Solok)
- `sitinjau_consumer` (Core Processing & MKJI calculation)
- `sitinjau_api` (Backend & Dashboard Server)

### 3. Akses Dashboard
Buka browser dan akses:
- **Dashboard Live:** `http://localhost:8000/dashboard`
- **Cek Status Health:** `docker compose ps`

---

## 🔧 5. Menjalankan Tanpa Docker (Manual)

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

## 📂 6. Struktur Direktori Utama

```text
📦 Computer-Vision-Sitinjau-Lauik
 ┣ 📂 config/            # File YAML untuk konfigurasi sensitivitas deteksi, dll
 ┣ 📂 dashboard/         # Antarmuka web HTML/JS & WebSocket
 ┣ 📂 models/            # Tempat menyimpan file .pt (YOLO weights)
 ┣ 📂 scripts/           # Script database (setup_database.sql)
 ┣ 📂 src/
 ┃ ┣ 📜 api_server.py    # FastAPI & WebSocket server
 ┃ ┣ 📜 database.py      # PostgreSQL Connection Pooling
 ┃ ┣ 📜 detector.py      # Integrasi Ultralytics YOLO & ByteTrack
 ┃ ┣ 📜 event_publisher.py # Modul MQTT Edge + Auto Recovery Buffer
 ┃ ┣ 📜 main.py          # Entry point Edge (Raspberry Pi)
 ┃ ┣ 📜 mkji.py          # Algoritma perhitungan LOS standar MKJI 1997
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

## 💡 7. Tips Optimasi di Raspberry Pi (Hardware Deployment)

Sistem ini sangat intensif untuk CPU ARM yang kecil. Pastikan Anda melakukan:
1. **Konversi Model ke NCNN:** Format `.pt` cukup berat untuk ARM. Gunakan `model_optimizer.py` untuk mengonversi ke NCNN/ONNX guna mempercepat Inference Rate FPS.
   ```bash
   python src/model_optimizer.py --format ncnn
   ```
2. **Atur Ukuran Frame:** Pada file `config.yaml`, pastikan resolusi diatur ke `416` (bukan `640`) untuk `imgsz`. Ini krusial agar Pi tidak overheat.
3. **Pendinginan Fisik:** Wajib menggunakan modul *Active Cooling* (Kipas) di Pi. Modul `src/watchdog.py` akan me-restart sistem jika suhu menembus 80°C untuk mencegah kerusakan hardware.

---
*Dikembangkan untuk memecahkan tantangan lalu lintas ekstrem Sitinjau Lauik dengan teknologi AI terdepan.*
