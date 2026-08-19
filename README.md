# AI-Powered Traffic Monitoring System (Sitinjau Lauik)

Sistem ini adalah solusi cerdas terintegrasi berbasis Computer Vision (AI) dan Internet of Things (IoT) untuk mendeteksi, menghitung, dan menganalisis tingkat kemacetan lalu lintas secara *real-time* di ruas jalan ekstrem Sitinjau Lauik (Padang - Solok).

Sistem ini dirancang dengan arsitektur **Microservices / Event-Driven (MQTT)** yang memisahkan antara proses deteksi berat di ujung (*Edge AI*) dengan proses analitik dan penyajian data di Pusat (*Core Server*), sehingga sistem menjadi *scalable*, tangguh (*robust*), dan berstandar industri.

---

## 1. Arsitektur Sistem (Clean Architecture)

Sistem dibagi menjadi 4 layer utama yang saling lepas (*decoupled*):

1. **Edge AI Layer (`src/main.py`, `src/detector.py`)**
   - Berjalan di perangkat lokal di lapangan (misal Jetson Nano / PC).
   - Membaca RTSP stream dari IP Camera atau video lokal.
   - Melakukan deteksi objek (YOLOv8) dan pelacakan (ByteTrack).
   - Menghitung kendaraan yang melewati *Virtual Counting Line*.
   - Mengagregasi data setiap 20 detik dan mengirimkannya via protokol MQTT.
2. **Transport Layer (MQTT Broker)**
   - Berfungsi sebagai jembatan komunikasi yang sangat ringan dan cepat.
   - Menggunakan Mosquitto MQTT. Topik: `sitinjau_lauik/{gerbang_id}/agregasi`.
3. **Core Server Layer (`src/mqtt_consumer.py`, `src/sistem_pakar.py`, `src/database.py`)**
   - Berjalan di cloud atau server pusat.
   - Menerima pesan MQTT dari banyak gerbang secara bersamaan.
   - Menyimpan raw data ke PostgreSQL.
   - Menghitung *Occupancy* (kepadatan ruas) menggunakan algoritma selisih antar gerbang.
   - Menjalankan **Sistem Pakar (Rule-based)** untuk menentukan status (LANCAR/PADAT/MACET).
4. **Presentation Layer (`src/api_server.py`, `dashboard/`)**
   - REST API (FastAPI) dan antarmuka web modern.
   - Menggunakan **WebSocket** (`/ws/live`) untuk mendorong (push) data metrik secara *real-time* ke browser klien tanpa membebani server dengan *polling*.

---

## 2. Metodologi, Rumus, dan Logika Perhitungan

Agar *AI Engine* di masa depan (Claude/GLM) dapat menganalisis dan meningkatkan sistem ini, berikut adalah landasan matematis yang digunakan:

### A. Deteksi & Tracking (Computer Vision)
- **Model:** YOLOv8 (Ultralytics) untuk Object Detection (terkalibrasi untuk kelas: Motor, Mobil, Bus, Truk).
- **Tracker:** ByteTrack untuk melacak pergerakan (*trajectory*) dan ID kendaraan antar *frame* agar tidak terjadi perhitungan ganda (*double counting*).
- **Penghitungan Garis (Line Crossing):** Vektor pergerakan dihitung dengan *dot product* dan penyeberangan dideteksi ketika titik pusat *bounding box* memotong garis virtual (*Point-Line Position*).

### B. Kapasitas Volumetrik Ruas (KVR)
Kapasitas jalan tidak dihitung per lajur standar, melainkan menggunakan spesifikasi lebar jalan ekstrem Sitinjau Lauik.
**Rumus:**
```math
KVR = (Panjang \times \%_{Sempit} \times Kap_{Sempit}) + (Panjang \times \%_{Lebar} \times Kap_{Lebar})
```
*Contoh:* Untuk jalan 16.5km, dengan 65% area sempit (muat 2 mobil) dan 35% area lebar (muat 6 mobil), KVR diukur dalam satuan *meter-lajur*.

### C. Volume Aktual Kendaraan (Meter-Lajur)
Mengonversi jumlah kendaraan mentah menjadi bobot panjangnya.
**Rumus:**
```math
Volume = \sum (Jumlah_{Kelas} \times Panjang_{Kelas})
```
*(Asumsi panjang: Motor=2.5m, Mobil=6.0m, Truk=12.0m, Bus=14.0m).*

### D. Estimasi Occupancy (Selisih Kumulatif Dual Gerbang)
Karena ruas Sitinjau Lauik merupakan *closed-system* panjang tanpa banyak persimpangan besar, kepadatan di tengah hutan diestimasi murni dari ujung-ujungnya.
**Rumus:**
```math
Occupancy = (Masuk_A + Masuk_B) - (Keluar_A + Keluar_B)
```
*(Catatan: Rumus ini menggunakan akumulasi reset harian untuk mencegah drift jangka panjang).*

### E. Kepadatan dan Level of Service (LOS)
**Rumus:**
```math
Kepadatan (\%) = \frac{Volume Aktual}{KVR} \times 100
```
**Skala LOS:**
- A: $\le 25\%$ (Sangat Lancar)
- B: $26\% - 50\%$ (Lancar)
- C: $51\% - 60\%$ (Sedang)
- D: $61\% - 75\%$ (Padat)
- E: $76\% - 90\%$ (Sangat Padat / Merayap)
- F: $> 90\%$ (Macet Total)

### F. Sistem Pakar (Hybrid Rules)
Status akhir ditentukan oleh kepadatan. Namun, ada aturan khusus (Override):
**IF** (Kecepatan Rata-rata < Ambang Batas [mis. 15 km/h]) **THEN** Status = MACET.
*(Kondisi ini berguna karena kemacetan gunung biasanya disebabkan oleh 1 truk patah as / mogok yang langsung membuat kecepatan menjadi 0, meskipun kepadatan volumetriknya secara total masih rendah).*

---

## 3. Evaluasi Sistem (Kelebihan & Kekurangan)

Sistem ini sangat transparan. Berikut adalah analisis pro dan kontra untuk pertimbangan perbaikan *AI Engineer* berikutnya:

### Kelebihan (Pros)
1. **Industri-Standar & Clean Code:** Kode berbasis OOP dan functional, di-tipe dengan kuat (*Type Hinting*), penanganan error (`try-except`) yang aman, dan koneksi PostgreSQL yang *auto-reconnect*.
2. **Highly Scalable (Event-Driven):** MQTT memungkinkan penambahan Gerbang C, D, atau E tanpa harus membongkar kode server pusat.
3. **Efisiensi Bandwidth:** *Edge* tidak mengirim *streaming* video HD ke server pusat, melainkan hanya mengirim _string JSON_ ringan setiap 20 detik. Ini sangat cocok untuk kondisi sinyal gunung yang lemah.
4. **Performa Real-time:** Dashboard menggunakan WebSocket dan FastAPI, data muncul instan.

### Kekurangan & Tantangan (Cons) - *Area for Improvement*
1. **Akurasi Kecepatan Lemah (Perspective Distortion):** Saat ini kecepatan dihitung menggunakan pendekatan 2D piksel per meter sederhana (`pixel_dist / pixel_per_meter`). Hal ini menyebabkan *error* besar karena kamera memiliki efek perspektif (kendaraan di kejauhan tampak bergerak lebih lambat di piksel).
   > *Saran Perbaikan:* Implementasikan *Perspective Transform (Bird's Eye View)* menggunakan Matriks Homografi dengan kalibrasi 4 titik di aspal.
2. **Risiko Drift Occupancy:** Jika detektor gagal mengenali 1 mobil yang keluar, angka *Occupancy* di dalam ruas akan tersangkut (bertambah 1 hantu) selamanya sampai di-reset di tengah malam.
   > *Saran Perbaikan:* Gunakan sistem pembacaan Plat Nomor (ALPR) probabilistik, atau gunakan kalibrasi ulang berkala menggunakan analisis spasial jika kepadatan sudah terlalu jauh melenceng.
3. **Model YOLO Bawaan COCO:** Model YOLO yang digunakan saat ini belum dilatih ulang (*fine-tuned*) untuk klasifikasi khas Indonesia (seperti Odong-odong, Truk Tronton ODOL, Angkot).
   > *Saran Perbaikan:* Kumpulkan ribuan gambar dari Sitinjau Lauik, lalu *fine-tune* model menggunakan `scripts/fine_tune.py`.

---

## 4. Struktur Database (PostgreSQL)
Sistem menggunakan skema yang dinormalisasi:
- `gerbang_kamera`: Menyimpan daftar kamera fisik beserta IP dan Status operasional.
- `hitungan_kendaraan`: *Time-series data* mentah jumlah kendaraan masuk/keluar per kelas per interval waktu.
- `status_ruas`: Tabel log hasil evaluasi Sistem Pakar (Kepadatan, Volume, LOS, Status) per titik waktu.

---
*Dokumentasi ini disiapkan untuk transisi secara mulus kepada tim pengembang lanjutan atau Analis AI berikutnya. Happy Coding!*
