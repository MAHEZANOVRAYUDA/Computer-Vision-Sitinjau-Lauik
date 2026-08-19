# Sistem Deteksi Kemacetan Sitinjau Lauik — Prototipe 1 Kamera

Prototipe sistem deteksi, penghitungan, dan klasifikasi kemacetan lalu lintas
di ruas Sitinjau Lauik (Padang–Solok), menggunakan computer vision (YOLOv8 +
ByteTrack) dan sistem pakar rule-based sesuai standar MKJI.

> **Status saat ini:** kamera fisik sedang bermasalah, sistem dikonfigurasi
> default untuk berjalan dari **video file lokal** (mode `"file"` di
> `config.yaml`). Taruh video traffic Anda di `data/videos/traffic.mp4`.
> Migrasi ke kamera RTSP nanti tinggal ganti 2 baris di `config.yaml` —
> lihat komentar di file itu atau Tahap 5B di `AGENT_SETUP.md`.

**Untuk panduan setup lengkap langkah demi langkah, buka `docs/PANDUAN_SETUP.docx`.**

**Menjalankan dengan AI code editor (Antigravity, Cursor, Windsurf, dsb)?**
Buka proyek ini di editor Anda, lalu minta AI agent untuk membaca dan
mengikuti `AGENT_SETUP.md` — file itu berisi instruksi eksekusi terstruktur
dengan kriteria sukses di tiap tahap, dirancang khusus supaya AI agent bisa
menjalankan setup secara mandiri dan memverifikasi setiap langkah sebelum lanjut.
Versi terbaru sudah disesuaikan untuk alur video file (bukan kamera).

## Struktur Folder

```
sitinjau-lauik-cv/
├── AGENT_SETUP.md            ← Instruksi eksekusi untuk AI code editor
├── config/
│   └── config.yaml          ← SATU-SATUNYA file yang perlu Anda edit untuk konfigurasi
├── src/
│   ├── config_loader.py     ← Memuat config.yaml
│   ├── counting_line.py     ← Logika inti: garis hitung virtual
│   ├── detector.py          ← YOLO + ByteTrack + integrasi counting line
│   ├── event_publisher.py   ← Kirim event ke MQTT broker
│   ├── main.py               ← ENTRY POINT EDGE (jalankan ini pertama)
│   ├── database.py          ← Operasi PostgreSQL
│   ├── mqtt_consumer.py     ← ENTRY POINT SERVER (proses kedua)
│   ├── api_server.py        ← ENTRY POINT DASHBOARD (proses ketiga)
│   └── sistem_pakar.py      ← Logika klasifikasi lancar/padat/macet
├── scripts/
│   ├── kalibrasi_garis.py       ← Bantuan menentukan garis virtual secara visual
│   ├── download_video_youtube.py ← Bantuan download video simulasi (opsional)
│   └── setup_database.sql        ← Schema & seed data database
├── tests/
│   ├── test_counting_line.py     ← Unit test logika penghitungan
│   └── test_sistem_pakar.py      ← Unit test sistem pakar
├── dashboard/
│   └── index.html            ← Dashboard web untuk demo
├── models/                   ← Tempat menyimpan file model YOLO (.pt)
├── data/videos/               ← TARUH video traffic.mp4 Anda di sini
├── data/logs/                 ← Output video hasil deteksi (opsional)
├── requirements.txt
├── .env.example
└── docs/
    └── PANDUAN_SETUP.docx    ← PANDUAN LENGKAP - MULAI DARI SINI
```

## Ringkasan Cara Pakai (detail ada di PANDUAN_SETUP.docx atau AGENT_SETUP.md)

1. Install semua dependency (`pip install -r requirements.txt`)
2. Setup PostgreSQL (sudah ada) & Mosquitto MQTT broker (perlu diinstall)
3. Taruh video traffic Anda di `data/videos/traffic.mp4`
4. Kalibrasi garis virtual: `python scripts/kalibrasi_garis.py`
5. Jalankan 3 proses di 3 terminal terpisah:
   - `python src/main.py` (edge - deteksi dari video file, otomatis loop saat habis)
   - `python src/mqtt_consumer.py` (server - agregasi & sistem pakar)
   - `python src/api_server.py` (dashboard - buka http://localhost:8000)
6. Jalankan test: `pytest tests/ -v`

## Status Proyek

Ini prototipe **1 kamera / 1 gerbang (Gerbang A)**, saat ini berjalan dari
**video file** (bukan kamera fisik) karena kamera sedang bermasalah.
Occupancy yang dihitung adalah selisih masuk-keluar di gerbang yang sama —
bukan occupancy ruas jalan penuh. Untuk versi 2 gerbang penuh dan migrasi ke
kamera RTSP, lihat catatan pengembangan lanjutan di `src/mqtt_consumer.py`,
`AGENT_SETUP.md` Tahap 5B, dan bagian akhir `PANDUAN_SETUP.docx`.
