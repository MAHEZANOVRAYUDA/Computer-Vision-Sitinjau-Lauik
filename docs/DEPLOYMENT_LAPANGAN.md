# Checklist Deployment Lapangan — Sitinjau Lauik Traffic System

> Dokumen ini WAJIB dibaca dan diikuti sebelum setiap sesi pemantauan live.
> Kedua edge node (Gerbang A dan Gerbang B) harus melalui semua checklist ini.

---

## 1. Sinkronisasi Waktu (NTP) — WAJIB Sebelum Live

Kedua edge node (Gerbang A dan Gerbang B) **HARUS** memakai sumber waktu
yang sama sebelum sesi pemantauan dimulai, karena occupancy dual-gerbang
dihitung dari selisih kumulatif 2 node terpisah.

Jika jam node tidak tersinkronisasi, event "masuk" di Gerbang A dan "keluar"
di Gerbang B bisa terhitung di interval waktu yang berbeda, menyebabkan
occupancy dihitung tidak akurat.

### Linux / Raspberry Pi

```bash
# Aktifkan sinkronisasi NTP otomatis
sudo timedatectl set-ntp true

# Verifikasi (pastikan "System clock synchronized: yes")
timedatectl status
```

### Windows (laptop testing)

```
Settings > Time & Language > Date & Time > "Sync now"
```

Atau via PowerShell (jalankan sebagai Administrator):

```powershell
w32tm /resync /force
```

### Verifikasi Manual

Jalankan `date` (Linux) atau `Get-Date` (PowerShell) di **kedua perangkat
pada saat bersamaan**. Pastikan selisih waktu < 1 detik.

```bash
# Linux
date +"%Y-%m-%d %H:%M:%S"

# Windows PowerShell
Get-Date -Format "yyyy-MM-dd HH:mm:ss"
```

> **Jika selisih > 5 detik**: sistem akan log WARNING di `mqtt_consumer.py`
> dengan pesan `[MQTT-Consumer] Drift waktu terdeteksi dari gerbang_X: X.X detik`.
> Jangan lanjutkan live sebelum drift diperbaiki.

---

## 2. Kalibrasi Kamera — Sebelum Deploy Pertama Kali atau Setelah Pindah Posisi

Setiap kamera HARUS dikalibrasi secara individual karena sudut pandang,
ketinggian pemasangan, dan jarak ke jalan berbeda.

### Langkah Kalibrasi Garis Virtual

```bash
python scripts/kalibrasi_garis.py
```

Klik 4 titik di frame video, salin koordinat ke config YAML terkait.

### Langkah Kalibrasi pixel_per_meter

```bash
python scripts/kalibrasi_garis.py --kalibrasi-meter
```

Klik 2 titik yang jarak riilnya diketahui (mis. jarak antar marka jalan 3m,
atau lebar satu lajur yang sudah diukur dengan meteran), input jarak real,
salin nilai `pixel_per_meter` ke config YAML.

**Status Kalibrasi:**

| Komponen | Gerbang A | Gerbang B |
|---|---|---|
| Garis virtual (counting line) | [ ] Belum / [ ] Sudah: ______ | [ ] Belum / [ ] Sudah: ______ |
| pixel_per_meter | [ ] Belum / [ ] Sudah: ______ | [ ] Belum / [ ] Sudah: ______ |
| Tanggal kalibrasi | ______ | ______ |

---

## 3. Checklist Sebelum Setiap Sesi Live

```
[ ] NTP sync terverifikasi di Gerbang A dan Gerbang B (selisih < 1 detik)
[ ] Kamera Gerbang A terhubung dan streaming normal
[ ] Kamera Gerbang B terhubung dan streaming normal (jika sudah terpasang)
[ ] Broker MQTT berjalan (mosquitto atau broker pilihan)
[ ] PostgreSQL berjalan dan database dapat diakses
[ ] Jalankan: python src/main.py config/config_gerbang_a.yaml
[ ] Jalankan: python src/mqtt_consumer.py config/config_gerbang_a.yaml
[ ] Jalankan: python src/api_server.py
[ ] Buka dashboard: http://localhost:8000
[ ] Verifikasi: angka occupancy muncul dan tidak stuck di 0
[ ] Verifikasi: log [MKJI] muncul di mqtt_consumer log
[ ] Restart mqtt_consumer sekali untuk test recovery occupancy
```

---

## 4. Prosedur Shutdown yang Aman

```bash
# Hentikan semua proses dengan Ctrl+C secara berurutan:
# 1. src/main.py (edge node)
# 2. src/mqtt_consumer.py (server consumer)
# 3. src/api_server.py (API server)

# Atau jika menggunakan start_all.bat, gunakan Ctrl+C di terminal yang sama
```

---

## 5. Troubleshooting Umum

| Gejala | Kemungkinan Penyebab | Solusi |
|---|---|---|
| Dashboard tidak update | mqtt_consumer tidak berjalan | Jalankan ulang mqtt_consumer |
| Occupancy tiba-tiba jatuh ke 0 | Restart consumer tanpa recovery | Cek log: `[Recovery]` harus muncul |
| Warning "Drift waktu" di log | NTP tidak aktif di salah satu node | Jalankan `timedatectl set-ntp true` |
| RTSP stream tidak bisa dibuka | Password kamera salah atau jaringan putus | Cek `.env` dan koneksi jaringan |
| LOS selalu A (sangat rendah) | pixel_per_meter belum dikalibrasi | Jalankan kalibrasi pixel_per_meter |
| DB connection failed | PostgreSQL tidak berjalan | Start PostgreSQL service |

---

## 6. Catatan Khusus Demo ke Dinas PU/Dishub

- Siapkan penjelasan singkat tentang metodologi **MKJI 1997** (V/C ratio, EMP, faktor koreksi)
- Siapkan angka akurasi dari `docs/HASIL_VALIDASI.md` untuk menjawab pertanyaan "seberapa akurat sistem ini?"
- Dashboard sudah menampilkan V/C ratio dan LOS (bukan meter-lajur) sebagai metrik utama
- Pastikan Gerbang A sudah terkalibrasi sebelum demo
