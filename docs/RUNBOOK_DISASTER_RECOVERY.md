# RUNBOOK: Disaster Recovery & Troubleshooting
Sitinjau Lauik Traffic System

## 1. Sistem Offline / Tidak Bisa Diakses
**Gejala**: Dashboard tidak bisa dibuka, atau notifikasi Discord menyatakan sistem offline.
**Solusi**:
1. Cek status docker: `docker ps`
2. Jika ada container yang exit, lihat log: `docker logs sitinjau_api` atau `docker logs sitinjau_consumer`
3. Restart container yang bermasalah: `docker restart <nama_container>`
4. Jika seluruh sistem hang, lakukan restart penuh: 
   ```bash
   docker-compose down
   docker-compose up -d
   ```

## 2. Kamera Offline di Dashboard
**Gejala**: Status gerbang di dashboard berubah menjadi "offline".
**Solusi**:
1. Cek status container edge yang bersangkutan (misal `sitinjau_edge_a`).
2. Pastikan stream RTSP kamera bisa diakses (bisa ditest menggunakan VLC Media Player).
3. Cek log kamera: `docker logs sitinjau_edge_a`. Jika ada error `cv2.VideoCapture`, berarti koneksi fisik/jaringan ke IP Camera putus.
4. Periksa suplai daya ke kamera atau switch PoE.

## 3. Akumulasi Kendaraan Tidak Bertambah (Double Counting / Missing)
**Gejala**: Video live menunjukkan kendaraan lewat, tapi counter tidak bertambah.
**Solusi**:
1. Masuk ke halaman Kalibrasi Admin di dashboard menggunakan PC/Laptop.
2. Cek letak garis virtual. Pastikan tidak menempel ujung frame/terlalu dekat dengan batas layar.
3. Geser garis virtual agar objek melewati batas dengan jelas.
4. Simpan konfigurasi kalibrasi baru.

## 4. Database Corrupt / Penuh
**Gejala**: Error `FATAL: database is not accepting commands` atau disk space habis.
**Solusi**:
1. Cek sisa storage: `df -h`
2. Jalankan script arsip untuk menghapus data berumur >30 hari:
   `python3 scripts/arsipkan_data_lama.py`
3. Jika database rusak, restore dari backup harian:
   ```bash
   gunzip -c data/backups/backup_sitinjau_lauik_db_YYYYMMDD_HHMMSS.sql.gz | psql -U postgres -d sitinjau_lauik_db
   ```

## 5. Pesan MQTT Tidak Masuk (Buffer Penuh)
**Gejala**: Data di dashboard tertinggal jauh dari video live.
**Solusi**:
1. Pastikan Mosquitto broker berjalan normal: `docker logs sitinjau_mqtt`
2. Cek apakah ada peringatan di log edge (`sitinjau_edge_a`): `[MQTT Buffer] Buffer lokal melebihi batas 5MB.`
3. Jika koneksi broker down terlalu lama, buffer akan mengosongkan data lama otomatis. Restart broker `docker restart sitinjau_mqtt` untuk memulihkan aliran data.
