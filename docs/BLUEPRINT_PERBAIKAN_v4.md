# BLUEPRINT PERBAIKAN v4 — Sitinjau Lauik Traffic System

> **Dokumen ini untuk AI code editor (Antigravity/Cursor/dst).**
> Setiap tahap berisi: file target, masalah aktual di kode saat ini, kode
> pengganti/tambahan, dan kriteria selesai (Definition of Done). Kerjakan
> **berurutan** — tahap belakangan bergantung pada tahap sebelumnya.
> Jangan mengubah bagian kode yang tidak disebutkan di tahap terkait.
>
> Konteks proyek: sistem deteksi & klasifikasi kemacetan berbasis
> computer vision (YOLOv8 + ByteTrack) di ruas Sitinjau Lauik
> (Padang–Solok), 2 gerbang kamera, tujuan akhir: (1) demo operasional
> ke Dinas PU/Dishub, (2) landasan naskah jurnal Scopus minimal Q3.
>
> Setelah SETIAP tahap selesai: jalankan `pytest tests/ -v` dan pastikan
> semua test lama tetap lolos sebelum lanjut ke tahap berikutnya.

---

## DAFTAR ISI

- [TAHAP 0 — Keamanan Kredensial (WAJIB PALING AWAL)](#tahap-0)
- [TAHAP 1 — Fix Persistensi Occupancy Dual-Gerbang](#tahap-1)
- [TAHAP 2 — Migrasi Landasan Perhitungan ke MKJI Standar](#tahap-2)
- [TAHAP 3 — Perbaikan Estimasi Kecepatan (Least-Squares)](#tahap-3)
- [TAHAP 4 — Kalibrasi pixel_per_meter per Kamera](#tahap-4)
- [TAHAP 5 — Sinkronisasi Waktu Antar Node](#tahap-5)
- [TAHAP 6 — Perbaikan Deteksi Motor (Confidence & Fine-tuning)](#tahap-6)
- [TAHAP 7 — Mitigasi Double-Count pada Kendaraan Berhenti/U-turn](#tahap-7)
- [TAHAP 8 — Instrumentasi untuk Validasi Ilmiah (MAPE, Precision/Recall)](#tahap-8)
- [TAHAP 9 — Dashboard: Perbaikan Informasi untuk Audiens Non-Teknis](#tahap-9)
- [TAHAP 10 — Checklist Akhir Sebelum Demo Dishub/PU](#tahap-10)

---

<a name="tahap-0"></a>
## TAHAP 0 — Keamanan Kredensial (WAJIB PALING AWAL)

### Masalah saat ini
Password RTSP kamera (`lppm25upi`) dan password PostgreSQL (`postgres123`)
tertulis plaintext dan sudah ter-commit ke git history di:
- `config/config_gerbang_a.yaml` (baris `rtsp_url`, baris `database.password`)
- `config/config_gerbang_b.yaml` (baris `database.password`)
- `config/config.yaml` (baris `database.password` — meski RTSP di sini
  sudah benar pakai `${GERBANG_A_RTSP_URL}`, ini pola yang harus
  diterapkan konsisten ke SEMUA file config)

### Langkah eksekusi

1. Buat/perbarui `.env` (sudah ada `.env.example`, gunakan sebagai acuan
   nama variabel) dengan isi:
   ```
   GERBANG_A_RTSP_URL=rtsp://admin:GANTI_PASSWORD_BARU@192.168.50.212:8554/Streaming/Channels/101
   GERBANG_B_RTSP_URL=
   DB_PASSWORD=GANTI_PASSWORD_BARU
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=sitinjau_lauik_db
   DB_USER=postgres
   ```

2. Edit `config/config_gerbang_a.yaml`, `config/config_gerbang_b.yaml`,
   `config/config.yaml`: ganti SEMUA nilai `rtsp_url` dan
   `database.password` yang hardcode menjadi placeholder `${NAMA_VAR}`,
   mengikuti pola yang sudah ada di `config.yaml` untuk
   `${GERBANG_A_RTSP_URL}`.

3. Pastikan `src/config_loader.py` bisa resolve `${VAR}` bukan cuma di
   `video_source` tapi juga di `database.password`. Cek fungsi
   `_compute_kapasitas` dan `load_config` — saat ini resolusi
   `${VAR}` hanya terjadi di `src/video_source.py` (baris 24-26), BUKAN
   di `config_loader.py`. Tambahkan resolusi environment variable
   generik di `load_config()` sehingga berlaku untuk semua field,
   bukan cuma video source:

   ```python
   # Di config_loader.py, tambahkan fungsi ini dan panggil setelah yaml.safe_load
   def _resolve_env_vars(data):
       """Rekursif ganti '${VAR_NAME}' dengan os.environ['VAR_NAME'] di semua nilai string."""
       if isinstance(data, dict):
           return {k: _resolve_env_vars(v) for k, v in data.items()}
       elif isinstance(data, list):
           return [_resolve_env_vars(v) for v in data]
       elif isinstance(data, str) and data.startswith("${") and data.endswith("}"):
           env_var = data[2:-1]
           resolved = os.environ.get(env_var)
           if resolved is None:
               _loader_log.warning(f"[Config] Environment variable '{env_var}' tidak ditemukan, nilai literal '${{{env_var}}}' dipakai apa adanya.")
               return data
           return resolved
       return data
   ```
   Panggil `data = _resolve_env_vars(data)` tepat setelah
   `data = yaml.safe_load(f)` di `load_config()`.

4. Pastikan `.gitignore` mencantumkan `.env` (cek dulu, kemungkinan
   sudah ada).

5. **Setelah kode diperbaiki**: ganti password RTSP kamera fisik dan
   password PostgreSQL ke nilai baru (di perangkat kamera dan di
   PostgreSQL server) karena nilai lama sudah pernah ter-expose di git
   history — mengubah kode saja tidak menghapus riwayat commit lama.
   (Ini langkah manual di luar kode, bukan tugas AI code editor, tapi
   WAJIB dicatat sebagai TODO untuk Maheza.)

### Definition of Done
- `grep -r "postgres123\|lppm25upi" config/` mengembalikan nol hasil.
- Semua 3 file config memakai `${VAR}` untuk kredensial.
- `python -c "from src.config_loader import load_config; c = load_config('config/config.yaml'); print(c.get('database.password'))"`
  mencetak nilai dari `.env`, bukan `${DB_PASSWORD}` literal.

---

<a name="tahap-1"></a>
## TAHAP 1 — Fix Persistensi Occupancy Dual-Gerbang

### Masalah saat ini
Di `src/mqtt_consumer.py`, state kumulatif (`kumulatif_gerbang_a_masuk`,
dst, baris 62-66) disimpan sebagai **variabel module-level in-memory**.
Fungsi `recover_occupancy_dari_db()` (baris 69-71) cuma:
```python
def recover_occupancy_dari_db(db: Database) -> None:
    # TODO: Implement multi-gerbang recovery if needed
    pass
```
Padahal `src/database.py` sudah punya `ambil_occupancy_hari_ini()` yang
berfungsi dan siap dipakai — hanya belum disambungkan. Akibatnya: setiap
kali proses `mqtt_consumer.py` restart (crash, deploy ulang, reboot
server), semua akumulasi hilang dan occupancy mulai dari 0, padahal
kendaraan riil mungkin masih ada di ruas. Ini akan membuat status
"lancar" palsu tepat setelah restart.

### Langkah eksekusi

1. `src/database.py`: `ambil_occupancy_hari_ini()` saat ini hanya
   mengembalikan net occupancy per kelas TANPA membedakan gerbang A vs
   B maupun arah. Untuk mendukung recovery dual-gerbang yang benar,
   tambahkan method baru yang mengembalikan kumulatif MENTAH per
   gerbang+arah+kelas (bukan yang sudah di-net-kan):

   ```python
   def ambil_kumulatif_masuk_keluar_per_gerbang(self, sejak_jam: int = 24) -> Dict[str, Dict[str, int]]:
       """
       Mengambil akumulasi mentah masuk/keluar per gerbang+kelas dalam
       N jam terakhir (bukan net) — untuk recovery state in-memory
       mqtt_consumer.py saat restart.

       Return: {
         "gerbang_a_masuk": {"motor": 120, "mobil": 45, ...},
         "gerbang_a_keluar": {...},
         "gerbang_b_masuk": {...},
         "gerbang_b_keluar": {...},
       }
       """
       with self._dict_cursor() as cursor:
           cursor.execute(
               """
               SELECT id_gerbang, arah, jenis_kendaraan, SUM(jumlah_terhitung) as total
               FROM hitungan_kendaraan
               WHERE timestamp_interval >= NOW() - make_interval(hours => %s)
               GROUP BY id_gerbang, arah, jenis_kendaraan
               """,
               (int(sejak_jam),),
           )
           rows = cursor.fetchall()

       hasil: Dict[str, Dict[str, int]] = {}
       for row in rows:
           gerbang = row["id_gerbang"]
           arah = row["arah"]
           kelas = row["jenis_kendaraan"]
           key = f"{gerbang}_{arah}"
           hasil.setdefault(key, {})[kelas] = int(row["total"] or 0)
       return hasil
   ```

   **Catatan skala jam**: gunakan window yang masuk akal secara
   operasional (mis. 24 jam, atau sejak tengah malam terakhir) — occupancy
   yang direkonstruksi dari kumulatif SEPANJANG hari akan terus membesar
   dan tidak pernah reset kalau tidak dibatasi window waktu. Diskusikan
   dengan tim: apakah occupancy harus di-reset setiap hari jam 00:00,
   atau pakai sliding window? Untuk mulai, pakai reset harian
   (`WHERE timestamp_interval >= CURRENT_DATE`) — konsisten dengan
   `ambil_occupancy_hari_ini()` yang sudah ada.

2. `src/mqtt_consumer.py`: ganti fungsi `recover_occupancy_dari_db`
   untuk benar-benar mengisi ulang 4 dictionary module-level:

   ```python
   def recover_occupancy_dari_db(db: Database) -> None:
       """
       Memulihkan state kumulatif in-memory dari database saat proses
       consumer baru start/restart, supaya occupancy tidak mulai dari
       0 secara keliru.
       """
       global kumulatif_gerbang_a_masuk, kumulatif_gerbang_a_keluar
       global kumulatif_gerbang_b_masuk, kumulatif_gerbang_b_keluar

       try:
           data = db.ambil_kumulatif_masuk_keluar_per_gerbang(sejak_jam=24)
       except Exception as e:
           logger.error(f"[Recovery] Gagal memulihkan occupancy dari DB: {e}. Mulai dari 0.")
           return

       for kelas, jumlah in data.get("gerbang_a_masuk", {}).items():
           kumulatif_gerbang_a_masuk[kelas] = jumlah
       for kelas, jumlah in data.get("gerbang_a_keluar", {}).items():
           kumulatif_gerbang_a_keluar[kelas] = jumlah
       for kelas, jumlah in data.get("gerbang_b_masuk", {}).items():
           kumulatif_gerbang_b_masuk[kelas] = jumlah
       for kelas, jumlah in data.get("gerbang_b_keluar", {}).items():
           kumulatif_gerbang_b_keluar[kelas] = jumlah

       total_recovered = sum(kumulatif_gerbang_a_masuk.values()) + sum(kumulatif_gerbang_b_masuk.values())
       logger.info(
           f"[Recovery] State occupancy dipulihkan dari DB: "
           f"A_masuk={dict(kumulatif_gerbang_a_masuk)} | A_keluar={dict(kumulatif_gerbang_a_keluar)} | "
           f"B_masuk={dict(kumulatif_gerbang_b_masuk)} | B_keluar={dict(kumulatif_gerbang_b_keluar)} | "
           f"Total unit dipulihkan: {total_recovered}"
       )
   ```

   Perhatikan: fungsi `jalankan()` di `mqtt_consumer.py` (baris ~231-235)
   SUDAH memanggil `recover_occupancy_dari_db(db)` — jadi cukup ganti
   isi fungsinya, tidak perlu ubah pemanggilnya.

3. Tambahkan reset harian: karena occupancy dipulihkan dengan window 24
   jam berjalan (bukan reset jam 00:00 yang presisi), tambahkan
   scheduler ringan di `mqtt_consumer.py` yang me-reset ke-4 dictionary
   ke 0 setiap pukul 00:00 waktu lokal, supaya akumulasi tidak
   membengkak tak terbatas selama proses berjalan lama tanpa restart.
   (Gunakan `threading.Timer` sederhana yang menjadwalkan ulang dirinya
   sendiri setiap kali dipanggil — hindari dependency tambahan seperti
   APScheduler untuk menjaga sistem tetap ringan.)

### Definition of Done
- Matikan proses `mqtt_consumer.py`, jalankan lagi — log baris
  `[Recovery] State occupancy dipulihkan dari DB: ...` muncul dengan
  angka bukan nol (asalkan ada data di `hitungan_kendaraan` hari itu).
- `tests/test_database.py` ditambah test untuk
  `ambil_kumulatif_masuk_keluar_per_gerbang()` dengan data dummy.
- Occupancy yang ditampilkan dashboard tidak mendadak jatuh ke 0/rendah
  tepat setelah restart consumer (bandingkan angka sebelum-sesudah
  restart pada data yang sama).

---

<a name="tahap-2"></a>
## TAHAP 2 — Migrasi Landasan Perhitungan ke MKJI Standar

### Masalah saat ini
Ada DUA landasan matematis yang tidak sinkron di proyek ini:
- `docs/PARAMETER_MKJI.md` — mendokumentasikan pendekatan MKJI 1997
  resmi (V/C ratio, EMP per kelas kendaraan sesuai medan gunung,
  kapasitas dasar dari tabel medan).
- `src/sistem_pakar.py` — kode AKTUAL yang jalan sekarang memakai satuan
  **"meter-lajur"** buatan sendiri (bukan istilah baku MKJI, diakui
  eksplisit di komentar kode sendiri baris 60-63).

Untuk kredibilitas ke Dinas PU dan syarat metodologi jurnal Scopus,
sistem HARUS melaporkan V/C ratio dan LOS sesuai MKJI 1997 sebagai
metrik utama. Pendekatan "meter-lajur" boleh dipertahankan sebagai
metrik pendukung/internal, TAPI bukan yang utama ditampilkan atau
diklaim di paper/laporan resmi.

### Strategi: tambahkan, jangan hapus
Jangan menghapus fungsi meter-lajur yang sudah teruji baik (breaking
`tests/test_sistem_pakar.py` yang sudah ada). Tambahkan modul MKJI
paralel, lalu jadikan MKJI sebagai output utama sementara meter-lajur
tetap tersedia sebagai metrik sekunder/debug.

### Langkah eksekusi

1. Buat file baru `src/mkji.py`:

   ```python
   """
   mkji.py
   =======
   Implementasi perhitungan Level of Service (LOS) sesuai MKJI 1997
   (Manual Kapasitas Jalan Indonesia) untuk jalan 2-lajur tak terbagi
   (2/2 UD) di medan gunung — sesuai karakteristik ruas Sitinjau Lauik
   (gradien 8-12%).

   Formula kapasitas:
       C = C0 x FCw x FCsp x FCsf x FCcs

   Dimana:
       C0   = kapasitas dasar (smp/jam), dari Tabel 5-2 MKJI 1997
              berdasarkan tipe jalan dan medan
       FCw  = faktor koreksi lebar jalur efektif
       FCsp = faktor koreksi pemisahan arah (untuk jalan tak terbagi)
       FCsf = faktor koreksi hambatan samping
       FCcs = faktor koreksi ukuran kota

   Volume dikonversi ke satuan mobil penumpang (smp) memakai EMP
   (Ekuivalen Mobil Penumpang) per kelas kendaraan, khusus medan gunung.

   Referensi: MKJI 1997, Direktorat Jenderal Bina Marga, Tabel 5-2 dan
   5-5. Lihat docs/PARAMETER_MKJI.md untuk detail tabel referensi dan
   catatan validasi lapangan yang WAJIB dilakukan sebelum klaim akademis.
   """

   from dataclasses import dataclass
   from typing import Dict, Optional


   # ---------------------------------------------------------------------
   # Nilai EMP (Ekuivalen Mobil Penumpang) — medan GUNUNG (MKJI Tabel 5-5)
   # ---------------------------------------------------------------------
   # PENTING: nilai bus/truk di sini adalah TITIK TENGAH rentang MKJI untuk
   # medan gunung (3.0-3.5 untuk bus, 4.0-6.0 untuk truk besar). WAJIB
   # divalidasi/disesuaikan dengan survei lapangan aktual — lihat
   # docs/PARAMETER_MKJI.md bagian 2 untuk rentang lengkap dan prosedur
   # validasi. Jangan mengklaim nilai ini final tanpa survei.
   EMP_GUNUNG: Dict[str, float] = {
       "motor": 0.4,
       "mobil": 1.0,
       "bus": 3.25,
       "truk": 5.0,
   }

   # Kapasitas dasar C0 (smp/jam, TOTAL 2 ARAH) — jalan 2/2 UD, MKJI Tabel 5-2
   C0_PER_MEDAN: Dict[str, float] = {
       "datar": 2900.0,
       "bukit": 2500.0,
       "gunung": 2100.0,
   }


   @dataclass
   class HasilMKJI:
       volume_smp_per_jam: float
       kapasitas_smp_per_jam: float
       rasio_vc: float
       level_of_service: str
       status_label: str


   def hitung_volume_smp(
       jumlah_per_kelas_per_jam: Dict[str, float],
       emp: Dict[str, float] = None,
   ) -> float:
       """
       Konversi volume kendaraan/jam per kelas menjadi smp/jam
       menggunakan EMP.

       Args:
           jumlah_per_kelas_per_jam: kendaraan/jam per kelas, mis.
               {"motor": 450, "mobil": 200, "bus": 10, "truk": 30}
           emp: mapping EMP per kelas (default: EMP_GUNUNG)
       """
       emp = emp or EMP_GUNUNG
       return sum(
           jumlah * emp.get(kelas, 1.0)
           for kelas, jumlah in jumlah_per_kelas_per_jam.items()
       )


   def hitung_kapasitas_mkji(
       medan: str = "gunung",
       fc_w: float = 0.90,
       fc_sp: float = 1.00,
       fc_sf: float = 1.00,
       fc_cs: float = 1.00,
   ) -> float:
       """
       C = C0 x FCw x FCsp x FCsf x FCcs (smp/jam, total 2 arah).

       Nilai default fc_w=0.90 mengasumsikan lebar jalur efektif
       3.0-3.5m (lihat docs/PARAMETER_MKJI.md). fc_sp=1.00 untuk jalan
       tak terbagi tanpa pemisah median. Sesuaikan berdasar kondisi
       aktual ruas dan hasil survei.
       """
       if medan not in C0_PER_MEDAN:
           raise ValueError(f"Medan '{medan}' tidak dikenal. Pilihan: {list(C0_PER_MEDAN)}")
       c0 = C0_PER_MEDAN[medan]
       return c0 * fc_w * fc_sp * fc_sf * fc_cs


   def tentukan_los_mkji(rasio_vc: float) -> str:
       """LOS A-F berdasarkan rasio V/C, sesuai MKJI 1997."""
       if rasio_vc <= 0.35:
           return "A"
       elif rasio_vc <= 0.54:
           return "B"
       elif rasio_vc <= 0.60:
           return "C"
       elif rasio_vc <= 0.80:
           return "D"
       elif rasio_vc <= 0.90:
           return "E"
       else:
           return "F"


   def klasifikasi_status_mkji(rasio_vc: float, ambang_lancar: float = 0.54, ambang_padat: float = 0.90) -> str:
       """
       Status operasional sederhana dari rasio V/C.
       Ambang default sesuai docs/PARAMETER_MKJI.md bagian 3
       (0.54 = batas LOS B, 0.90 = batas LOS E/F).
       """
       if rasio_vc <= ambang_lancar:
           return "lancar"
       elif rasio_vc <= ambang_padat:
           return "padat"
       else:
           return "macet"


   def evaluasi_mkji(
       jumlah_per_kelas_per_jam: Dict[str, float],
       medan: str = "gunung",
       fc_w: float = 0.90,
       fc_sp: float = 1.00,
       fc_sf: float = 1.00,
       fc_cs: float = 1.00,
       emp: Dict[str, float] = None,
       ambang_lancar: float = 0.54,
       ambang_padat: float = 0.90,
   ) -> HasilMKJI:
       """Fungsi utama: volume -> smp/jam -> V/C -> LOS -> status, sesuai MKJI 1997."""
       volume_smp = hitung_volume_smp(jumlah_per_kelas_per_jam, emp=emp)
       kapasitas = hitung_kapasitas_mkji(medan, fc_w, fc_sp, fc_sf, fc_cs)

       if kapasitas <= 0:
           raise ValueError("Kapasitas MKJI harus > 0. Periksa parameter fc_w/fc_sp/fc_sf/fc_cs.")

       rasio_vc = volume_smp / kapasitas
       los = tentukan_los_mkji(rasio_vc)
       status = klasifikasi_status_mkji(rasio_vc, ambang_lancar, ambang_padat)

       return HasilMKJI(
           volume_smp_per_jam=round(volume_smp, 2),
           kapasitas_smp_per_jam=round(kapasitas, 2),
           rasio_vc=round(rasio_vc, 4),
           level_of_service=los,
           status_label=status,
       )
   ```

2. Tambahkan section baru di semua file config (`config.yaml`,
   `config_gerbang_a.yaml`, `config_gerbang_b.yaml`):

   ```yaml
   # ---------------------------------------------------------------------
   # MKJI 1997 — parameter kapasitas standar (metrik UTAMA untuk laporan
   # resmi/publikasi, menggantikan meter-lajur sebagai output utama)
   # ---------------------------------------------------------------------
   mkji:
     medan: "gunung"              # gradien 8-12% -> kategori MKJI "gunung"
     fc_w: 0.90                   # faktor lebar jalur, WAJIB divalidasi lapangan
     fc_sp: 1.00                  # tak terbagi, tanpa median
     fc_sf: 1.00                  # hambatan samping rendah (jalan luar kota)
     fc_cs: 1.00                  # jalan rural
     emp:
       motor: 0.4
       mobil: 1.0
       bus: 3.25                  # titik tengah rentang MKJI gunung 3.0-3.5, VALIDASI LAPANGAN
       truk: 5.0                  # titik tengah rentang MKJI gunung 4.0-6.0, VALIDASI LAPANGAN
     ambang_lancar_vc: 0.54
     ambang_padat_vc: 0.90
   ```

3. `src/mqtt_consumer.py`: tambahkan panggilan ke `evaluasi_mkji()` DI
   SAMPING (bukan menggantikan) `evaluasi()` yang sudah ada dari
   `sistem_pakar.py`. Konversi flow per interval ke per jam terlebih
   dahulu (interval agregasi biasanya 20-60 detik, MKJI butuh basis
   per jam):

   ```python
   from src.mkji import evaluasi_mkji

   # ... di dalam on_message(), setelah hasil = evaluasi(...) yang lama:

   interval_jam = interval_detik / 3600.0
   jumlah_per_jam = {
       kelas: jumlah / interval_jam
       for kelas, jumlah in jumlah_untuk_evaluasi.items()
       if interval_jam > 0
   }

   try:
       hasil_mkji = evaluasi_mkji(
           jumlah_per_kelas_per_jam=jumlah_per_jam,
           medan=config.get("mkji.medan", "gunung"),
           fc_w=float(config.get("mkji.fc_w", 0.90)),
           fc_sp=float(config.get("mkji.fc_sp", 1.00)),
           fc_sf=float(config.get("mkji.fc_sf", 1.00)),
           fc_cs=float(config.get("mkji.fc_cs", 1.00)),
           emp=config.get("mkji.emp"),
           ambang_lancar=float(config.get("mkji.ambang_lancar_vc", 0.54)),
           ambang_padat=float(config.get("mkji.ambang_padat_vc", 0.90)),
       )
       logger.info(
           f"[MKJI] Volume: {hasil_mkji.volume_smp_per_jam:.1f} smp/jam | "
           f"Kapasitas: {hasil_mkji.kapasitas_smp_per_jam:.1f} smp/jam | "
           f"V/C: {hasil_mkji.rasio_vc:.3f} | LOS: {hasil_mkji.level_of_service} | "
           f"Status: {hasil_mkji.status_label.upper()}"
       )
   except ValueError as e:
       logger.error(f"[MKJI] ERROR: {e}")
       hasil_mkji = None
   ```

4. `scripts/setup_database.sql`: tambahkan kolom untuk menyimpan hasil
   MKJI di tabel `status_ruas` (jangan drop kolom lama):

   ```sql
   ALTER TABLE status_ruas
     ADD COLUMN IF NOT EXISTS volume_smp_jam_mkji NUMERIC(10, 2),
     ADD COLUMN IF NOT EXISTS kapasitas_smp_jam_mkji NUMERIC(10, 2),
     ADD COLUMN IF NOT EXISTS rasio_vc_mkji NUMERIC(6, 4),
     ADD COLUMN IF NOT EXISTS level_of_service_mkji VARCHAR(5),
     ADD COLUMN IF NOT EXISTS status_label_mkji VARCHAR(20);
   ```

5. `src/database.py`, method `simpan_status_ruas()`: tambahkan parameter
   opsional `hasil_mkji=None` dan simpan ke kolom baru jika tersedia
   (jangan ubah signature yang memaksa breaking existing callers — beri
   default `None`).

6. Tulis unit test baru `tests/test_mkji.py` mengikuti pola
   `tests/test_sistem_pakar.py` — minimal cover:
   - `hitung_volume_smp()` dengan kombinasi kelas kendaraan
   - `hitung_kapasitas_mkji()` untuk ketiga medan (datar/bukit/gunung)
   - `tentukan_los_mkji()` untuk semua 6 kelas A-F, termasuk nilai batas
     tepat (0.35, 0.54, 0.60, 0.80, 0.90)
   - `evaluasi_mkji()` end-to-end dengan angka dari contoh MKJI 1997

### Definition of Done
- `pytest tests/test_mkji.py -v` semua lolos.
- `pytest tests/test_sistem_pakar.py -v` masih semua lolos (tidak ada
  regresi ke fungsi meter-lajur lama).
- Log `mqtt_consumer.py` menampilkan BAIK baris `[Sistem Pakar]` (meter-
  lajur, lama) MAUPUN baris `[MKJI]` (baru) untuk setiap interval.
- README atau `docs/PARAMETER_MKJI.md` diperbarui menjelaskan bahwa MKJI
  adalah metrik pelaporan utama, meter-lajur adalah metrik internal
  pendukung.

---

<a name="tahap-3"></a>
## TAHAP 3 — Perbaikan Estimasi Kecepatan (Least-Squares)

### Masalah saat ini
`src/counting_line.py`, method `proses_deteksi()` baris ~120-131,
menghitung kecepatan hanya dari titik PERTAMA dan titik TERAKHIR di
histori:
```python
y_lama, t_lama = hist[0]
y_baru, t_baru = hist[-1]
delta_t = t_baru - t_lama
pixel_dist = abs(y_baru - y_lama)
```
Ini sangat sensitif terhadap noise deteksi bounding box pada 2 titik
saja. Ganti dengan regresi linear sederhana (least-squares) atas SELURUH
titik histori yang tersedia, jauh lebih tahan noise.

### Langkah eksekusi

1. Di `src/counting_line.py`, tambahkan fungsi helper di atas class
   `PelacakLintasGaris`:

   ```python
   def _estimasi_laju_least_squares(histori: List[Tuple[float, float]]) -> Optional[float]:
       """
       Estimasi laju perubahan posisi (piksel/detik) dari histori
       (posisi_y, timestamp) memakai regresi linear least-squares
       sederhana — jauh lebih tahan noise dibanding metode titik-awal
       vs titik-akhir saja, karena memakai seluruh histori yang ada.

       Return None jika data tidak cukup (< 2 titik atau variansi
       waktu nol).
       """
       n = len(histori)
       if n < 2:
           return None

       ys = [p[0] for p in histori]
       ts = [p[1] for p in histori]

       t_mean = sum(ts) / n
       y_mean = sum(ys) / n

       numerator = sum((t - t_mean) * (y - y_mean) for t, y in zip(ts, ys))
       denominator = sum((t - t_mean) ** 2 for t in ts)

       if denominator == 0:
           return None

       slope_piksel_per_detik = numerator / denominator
       return slope_piksel_per_detik
   ```

2. Tambahkan `Optional` ke import di bagian atas file:
   ```python
   from typing import Dict, List, Optional, Tuple
   ```

3. Ganti blok perhitungan kecepatan di `proses_deteksi()`:

   ```python
   # SEBELUM (baris ~122-131):
   speed_kmh = None
   hist = self._track_history[track_id]
   if len(hist) > 1:
       y_lama, t_lama = hist[0]
       y_baru, t_baru = hist[-1]
       delta_t = t_baru - t_lama
       pixel_dist = abs(y_baru - y_lama)
       if delta_t > 0 and garis.pixel_per_meter > 0:
           speed_ms = (pixel_dist / garis.pixel_per_meter) / delta_t
           speed_kmh = speed_ms * 3.6

   # SESUDAH:
   speed_kmh = None
   hist = self._track_history[track_id]
   MINIMAL_TITIK_UNTUK_KECEPATAN = 5  # butuh histori cukup panjang untuk regresi stabil
   if len(hist) >= MINIMAL_TITIK_UNTUK_KECEPATAN:
       laju_piksel_per_detik = _estimasi_laju_least_squares(hist)
       if laju_piksel_per_detik is not None and garis.pixel_per_meter > 0:
           speed_ms = abs(laju_piksel_per_detik) / garis.pixel_per_meter
           speed_kmh = speed_ms * 3.6
   ```

4. Pertimbangkan menaikkan batas histori dari 30 ke ~45-60 titik di
   `proses_deteksi()` (baris `if len(self._track_history[track_id]) > 30`)
   supaya regresi punya lebih banyak data poin per kendaraan, dengan
   trade-off penggunaan memori sedikit lebih tinggi (masih sangat
   ringan — puluhan angka float per track aktif).

5. Tambahkan test baru di `tests/test_counting_line.py`:
   - Histori linear sempurna (mis. y bergerak konstan 5px/frame pada
     interval waktu tetap) -> kecepatan hasil regresi harus sangat
     dekat dengan kecepatan titik-awal-akhir lama (validasi regresi
     tidak salah arah).
   - Histori dengan 1 outlier ekstrem di tengah -> kecepatan hasil
     regresi harus jauh lebih stabil (persentase deviasi lebih kecil)
     dibanding metode titik-awal-akhir pada data yang sama.

### Definition of Done
- `pytest tests/test_counting_line.py -v` semua lolos termasuk test baru.
- Jalankan sistem dengan video test (`test3.mp4` atau `traffic.mp4`),
  bandingkan sebaran nilai `kecepatan_kmh` di log sebelum vs sesudah
  perubahan — variansi (std dev) semestinya turun untuk kendaraan yang
  bergerak dengan kecepatan relatif konstan.

---

<a name="tahap-4"></a>
## TAHAP 4 — Kalibrasi pixel_per_meter per Kamera

### Masalah saat ini
`pixel_per_meter: 25.0` di-hardcode SAMA di semua counting line, semua
kamera, tanpa proses kalibrasi lapangan yang tercatat. Karena sudut
pandang, jarak, dan tinggi pemasangan tiap kamera CCTV berbeda, angka
generik ini kemungkinan besar salah dan langsung membuat SEMUA estimasi
kecepatan (dan karenanya `klasifikasi_status_hybrid`) tidak valid
secara metodologis.

### Langkah eksekusi

1. Cek isi `scripts/kalibrasi_garis.py` yang sudah ada — pastikan
   mendukung mode kalibrasi `pixel_per_meter`, bukan cuma menentukan
   titik garis. Jika belum, tambahkan mode interaktif:
   - Tampilkan 1 frame dari video/RTSP kamera terkait.
   - User klik 2 titik yang jarak riilnya DIKETAHUI di lapangan
     (misalnya jarak antar marka jalan putus-putus standar 3m, atau
     lebar 1 lajur jalan ~3-3.5m, diukur langsung dengan meteran saat
     survei lapangan).
   - User input jarak riil dalam meter via prompt CLI.
   - Script menghitung `pixel_per_meter = jarak_piksel_klik / jarak_meter_input`
     dan mencetak hasilnya untuk disalin manual ke config YAML terkait
     (jangan auto-write config — biarkan manusia yang commit angka final
     setelah verifikasi visual).

2. Tambahkan CATATAN WAJIB di setiap file config (`config_gerbang_a.yaml`,
   `config_gerbang_b.yaml`) tepat di atas key `pixel_per_meter`:
   ```yaml
   # pixel_per_meter WAJIB dikalibrasi ulang untuk kamera ini secara
   # spesifik menggunakan scripts/kalibrasi_garis.py setelah kamera
   # terpasang fisik di lokasi final. Nilai di bawah adalah PLACEHOLDER
   # dan TIDAK VALID untuk klaim kecepatan/LOS hybrid sampai dikalibrasi.
   # Tanggal kalibrasi terakhir: [ISI SETELAH KALIBRASI LAPANGAN]
   ```

3. Setelah kalibrasi lapangan dilakukan tim (di luar scope AI code
   editor — ini kerja fisik di lokasi), update nilai `pixel_per_meter`
   di config sesuai hasil kalibrasi masing-masing kamera (BUKAN nilai
   sama untuk semua garis lagi).

### Definition of Done
- `scripts/kalibrasi_garis.py` punya mode kalibrasi jarak dengan output
  angka `pixel_per_meter` yang jelas.
- Kedua file config gerbang punya catatan eksplisit soal status
  kalibrasi dan tanggal terakhir.
- (Setelah kalibrasi lapangan manual) nilai `pixel_per_meter` di
  Gerbang A dan Gerbang B TIDAK LAGI identik 25.0 kecuali kebetulan
  hasil pengukuran memang sama.

---

<a name="tahap-5"></a>
## TAHAP 5 — Sinkronisasi Waktu Antar Node

### Masalah saat ini
Occupancy dual-gerbang bergantung pada `hitung_occupancy_ruas()` yang
membandingkan akumulasi dari 2 node edge terpisah (Gerbang A dan B).
Jika jam sistem kedua perangkat (Raspberry Pi/laptop) tidak
tersinkronisasi (drift beberapa detik-menit), agregasi interval bisa
salah menghitung selisih masuk-keluar pada window waktu yang
sebenarnya tidak sama persis.

### Langkah eksekusi

1. Tambahkan dokumentasi operasional baru: `docs/DEPLOYMENT_LAPANGAN.md`
   berisi checklist NTP sync sebelum setiap sesi live (ini panduan
   manusia, bukan kode — tapi WAJIB ada di repo untuk tim):

   ```markdown
   # Checklist Sinkronisasi Waktu — Sebelum Deployment Live

   Kedua edge node (Gerbang A dan Gerbang B) HARUS memakai sumber waktu
   yang sama sebelum sesi pemantauan dimulai, karena occupancy dual-
   gerbang dihitung dari selisih kumulatif 2 node terpisah.

   ## Linux/Raspberry Pi
   ```bash
   sudo timedatectl set-ntp true
   timedatectl status   # pastikan "System clock synchronized: yes"
   ```

   ## Windows (laptop testing)
   Settings > Time & Language > Date & Time > "Sync now"

   ## Verifikasi manual
   Jalankan `date` (Linux) atau `Get-Date` (PowerShell) di kedua
   perangkat pada saat bersamaan, pastikan selisih < 1 detik.
   ```

2. Tambahkan validasi runtime ringan di `src/mqtt_consumer.py`: bandingkan
   `timestamp` yang dikirim tiap payload MQTT dengan waktu server saat
   diterima, log WARNING jika selisih signifikan (indikasi clock drift):

   ```python
   # Di dalam on_message(), setelah payload di-parse:
   drift_detik = abs(time.time() - timestamp)
   if drift_detik > 5.0:
       logger.warning(
           f"[MQTT-Consumer] Drift waktu terdeteksi dari {gerbang_id}: "
           f"{drift_detik:.1f} detik. Cek sinkronisasi NTP node edge ini."
       )
   ```

### Definition of Done
- `docs/DEPLOYMENT_LAPANGAN.md` ada dan lengkap.
- Log warning drift muncul jika salah satu node sengaja diset waktu
  salah untuk pengujian (uji manual: ubah jam sistem laptop tes mundur
  10 menit, jalankan `main.py`, pastikan warning muncul di
  `mqtt_consumer.py`).

---

<a name="tahap-6"></a>
## TAHAP 6 — Perbaikan Deteksi Motor (Confidence & Fine-tuning)

### Masalah saat ini
`confidence_threshold` di-set sangat rendah (0.10-0.15) di semua config
sebagai upaya memaksa lebih banyak deteksi motor. Ini pendekatan
simtomatik yang berisiko meningkatkan false positive di kelas lain
(mobil/bus/truk terdeteksi ganda, bayangan/objek non-kendaraan
terdeteksi). Solusi akar: fine-tuning model dengan data lokal — scaffold
`scripts/fine_tune.py` sudah lengkap tapi belum pernah dijalankan.

### Langkah eksekusi

1. **Bukan tugas AI code editor**, tapi WAJIB dicatat sebagai
   prasyarat: kumpulkan 500-1000 frame dari rekaman kamera lokal
   Sitinjau Lauik (bukan video generik dari internet), representasikan
   kondisi siang/sore/hujan/berkabut, lalu label dengan Roboflow/
   LabelImg mengikuti format yang sudah dijelaskan di
   `scripts/fine_tune.py` (struktur folder `data/fine_tuning/`).

2. Setelah dataset siap, AI code editor menjalankan:
   ```bash
   python scripts/fine_tune.py --model models/yolov8s.pt --epochs 100 --nama-run sitinjau_lauik_v1
   ```

3. Setelah fine-tuning selesai dan model baru tersedia di
   `models/sitinjau_lauik_v1/weights/best.pt`, update SEMUA file config
   (`config.yaml`, `config_gerbang_a.yaml`, `config_gerbang_b.yaml`):
   ```yaml
   model:
     weights_path: "models/sitinjau_lauik_v1/weights/best.pt"
     confidence_threshold: 0.40   # naikkan signifikan — model fine-tuned tidak lagi butuh threshold rendah
   ```
   (Ini sesuai rekomendasi yang SUDAH tertulis di akhir
   `scripts/fine_tune.py` baris 237 — cukup dieksekusi.)

4. Pertimbangkan mengganti backbone ke **YOLO11** (bukan hanya
   fine-tuning YOLOv8s) karena YOLO11 memakai modul **C2PSA**
   (Cross-Stage Partial with Spatial Attention) yang secara arsitektural
   lebih baik untuk deteksi objek kecil seperti motor — ini sudah
   sempat dibahas dan ditulis di laporan dosen sebelumnya. Jika dipilih:
   ```bash
   pip install ultralytics --upgrade
   python scripts/fine_tune.py --model yolo11s.pt --epochs 100 --nama-run sitinjau_lauik_yolo11_v1
   ```
   Bandingkan hasil MAPE (lihat Tahap 8) antara YOLOv8s fine-tuned vs
   YOLO11s fine-tuned — pilih yang lebih baik SECARA TERUKUR, jangan
   asumsi YOLO11 otomatis lebih baik tanpa data pembanding (ini juga
   jadi bahan tabel perbandingan yang kuat untuk paper Scopus).

5. Jalankan `scripts/hitung_akurasi.py` sebelum dan sesudah fine-tuning
   untuk dokumentasi before/after (lihat Tahap 8 untuk detail).

### Definition of Done
- Model baru tersimpan di `models/<nama_run>/weights/best.pt`.
- Config di 3 file menunjuk ke model baru dengan confidence dinaikkan.
- Ada laporan MAPE before/after tersimpan (mis.
  `data/logs/laporan_akurasi_sebelum.txt` dan `_sesudah.txt`) sebagai
  bukti kuantitatif perbaikan — bahan langsung untuk paper.

---

<a name="tahap-7"></a>
## TAHAP 7 — Mitigasi Double-Count pada Kendaraan Berhenti/U-turn

### Masalah saat ini
1. Jika kendaraan berhenti tepat di garis virtual (realistis terjadi —
   riset lapangan Anda mencatat kemacetan Sitinjau Lauik sering
   disebabkan kendaraan mogok/berhenti), jitter piksel kecil dari noise
   deteksi berpotensi memicu perpindahan sisi garis berulang dan
   menyebabkan hitungan ganda meski mitigasi `_sudah_dihitung` sudah ada
   untuk kasus umum.
2. Tidak ada validasi eksplisit untuk kendaraan yang U-turn/putar balik
   di tengah frame — bisa salah terhitung sebagai "keluar" padahal
   kembali ke arah semula.

### Langkah eksekusi

1. Di `src/counting_line.py`, tambahkan **histeresis** pada deteksi
   sisi garis — bukan sekadar `sisi_sebelumnya * sisi_sekarang < 0`,
   tapi mensyaratkan magnitude perubahan sisi melewati ambang batas
   (menghindari jitter kecil di sekitar nilai 0 memicu event):

   ```python
   # Tambahkan konstanta di atas class GarisVirtual:
   AMBANG_HISTERESIS_SISI = 3.0  # unit sama dengan hasil cross-product, sesuaikan setelah uji lapangan

   # Di dalam proses_deteksi(), ganti kondisi:
   # SEBELUM:
   if sisi_sebelumnya * sisi_sekarang < 0 and garis.dalam_rentang_segmen(x_center, y_center):

   # SESUDAH:
   if (
       sisi_sebelumnya * sisi_sekarang < 0
       and abs(sisi_sekarang) > AMBANG_HISTERESIS_SISI
       and abs(sisi_sebelumnya) > AMBANG_HISTERESIS_SISI
       and garis.dalam_rentang_segmen(x_center, y_center)
   ):
   ```
   Catatan: nilai `AMBANG_HISTERESIS_SISI` bergantung skala piksel
   frame — mulai dari nilai kecil (3-5) dan sesuaikan berdasarkan
   observasi log real saat testing, jangan asumsikan angka final tanpa
   uji lapangan.

2. Tambahkan validasi arah pergerakan konsisten sebelum mencatat event
   "melewati garis": cek apakah track_id bergerak secara **konsisten**
   ke satu arah dalam beberapa frame terakhir (bukan cuma 2 titik
   terakhir), memakai tanda `laju_piksel_per_detik` dari fungsi
   `_estimasi_laju_least_squares` yang sudah dibuat di Tahap 3:

   ```python
   # Di dalam proses_deteksi(), sebelum mencatat event, tambahkan cek:
   if len(hist) >= 5:
       laju = _estimasi_laju_least_squares(hist)
       # Jika arah laju (tanda +/-) TIDAK konsisten dengan arah
       # perpindahan sisi_sebelumnya -> sisi_sekarang, kemungkinan
       # noise/U-turn sesaat -> skip pencatatan event kali ini,
       # biarkan frame berikutnya mengonfirmasi ulang.
       arah_perpindahan_sisi = sisi_sekarang - sisi_sebelumnya
       if laju is not None and (laju * arah_perpindahan_sisi) < 0:
           # Arah tidak konsisten -> update sisi_terakhir tapi JANGAN
           # catat event, tunggu konfirmasi frame berikutnya
           self._sisi_terakhir[key] = sisi_sekarang
           continue
   ```

3. Tambahkan test kasus di `tests/test_counting_line.py`:
   - Simulasikan track_id "menempel" di garis dengan jitter piksel kecil
     bolak-balik beberapa frame -> pastikan HANYA tercatat maksimal 1
     event, bukan berkali-kali.
   - Simulasikan track_id yang mendekati garis lalu U-turn sebelum benar-
     benar melewati -> pastikan TIDAK tercatat sebagai event lolos garis.

### Definition of Done
- `pytest tests/test_counting_line.py -v` semua lolos termasuk 2 test
  baru di atas.
- Uji manual dengan video yang memuat kendaraan berhenti lama di dekat
  garis (jika tersedia rekaman relevan) -> hitungan tidak melonjak
  abnormal dibanding video tanpa kendaraan berhenti.

---

<a name="tahap-8"></a>
## TAHAP 8 — Instrumentasi untuk Validasi Ilmiah (MAPE, Precision/Recall)

### Masalah saat ini
`scripts/hitung_akurasi.py` sudah punya metodologi MAPE yang solid,
tapi belum pernah dijalankan dengan data lapangan riil. Untuk syarat
metodologi jurnal Scopus, MAPE saja (akurasi hitungan agregat) tidak
cukup — reviewer akan menanyakan precision/recall di level deteksi
objek per frame (standar evaluasi computer vision).

### Langkah eksekusi

1. Tambahkan script baru `scripts/evaluasi_deteksi.py` yang menghitung
   precision, recall, F1-score, dan mAP@0.5 per kelas dengan
   membandingkan output model terhadap anotasi ground truth manual pada
   sampel frame (bukan video utuh — cukup 100-200 frame representatif
   yang dilabel manual):

   ```python
   """
   evaluasi_deteksi.py
   ====================
   Evaluasi precision/recall/F1/mAP@0.5 model deteksi terhadap ground
   truth berlabel manual, di level DETEKSI OBJEK PER FRAME (bukan
   hitungan agregat seperti hitung_akurasi.py).

   Melengkapi hitung_akurasi.py: script itu mengukur akurasi HITUNGAN
   akhir (setelah tracking+counting line), script ini mengukur akurasi
   DETEKSI mentah model YOLO — dua metrik berbeda yang KEDUANYA
   dibutuhkan untuk paper Scopus (standar evaluasi computer vision).

   Memakai fitur validasi bawaan Ultralytics YOLO (model.val()) yang
   sudah mengimplementasikan mAP standar COCO-style.

   Cara pakai:
       python scripts/evaluasi_deteksi.py --model models/sitinjau_lauik_v1/weights/best.pt --data data/fine_tuning/data.yaml
   """
   import argparse
   import sys
   from pathlib import Path

   ROOT = Path(__file__).resolve().parent.parent
   sys.path.insert(0, str(ROOT))


   def main():
       parser = argparse.ArgumentParser(description="Evaluasi precision/recall/mAP model deteksi.")
       parser.add_argument("--model", type=str, required=True, help="Path ke file model .pt")
       parser.add_argument("--data", type=str, required=True, help="Path ke data.yaml (harus punya split 'test' atau 'val' berlabel)")
       parser.add_argument("--split", type=str, default="test", choices=["val", "test"])
       args = parser.parse_args()

       try:
           from ultralytics import YOLO
       except ImportError:
           print("[ERROR] Package 'ultralytics' tidak terinstall.")
           sys.exit(1)

       model = YOLO(args.model)
       hasil = model.val(data=args.data, split=args.split)

       print("=" * 70)
       print(f"HASIL EVALUASI DETEKSI — split: {args.split}")
       print("=" * 70)
       print(f"mAP50     : {hasil.box.map50:.4f}")
       print(f"mAP50-95  : {hasil.box.map:.4f}")
       print(f"Precision : {hasil.box.mp:.4f}")
       print(f"Recall    : {hasil.box.mr:.4f}")
       print()
       print("Per kelas:")
       for i, nama_kelas in hasil.names.items():
           try:
               print(f"  {nama_kelas:<10} AP50={hasil.box.ap50[i]:.4f}  AP50-95={hasil.box.ap[i]:.4f}")
           except (IndexError, AttributeError):
               continue
       print("=" * 70)
       print()
       print("Simpan angka-angka ini untuk tabel hasil di naskah paper —")
       print("format standar: Precision, Recall, mAP@0.5, mAP@0.5:0.95 per kelas.")


   if __name__ == "__main__":
       main()
   ```

2. Jalankan urutan validasi lengkap untuk dokumentasi paper:
   ```bash
   # 1. Evaluasi deteksi mentah (precision/recall/mAP) — sebelum fine-tuning
   python scripts/evaluasi_deteksi.py --model models/yolov8s.pt --data data/fine_tuning/data.yaml --split test > data/logs/eval_deteksi_sebelum.txt

   # 2. Fine-tuning (Tahap 6)
   python scripts/fine_tune.py --model models/yolov8s.pt --epochs 100

   # 3. Evaluasi deteksi mentah — sesudah fine-tuning
   python scripts/evaluasi_deteksi.py --model models/sitinjau_lauik_v1/weights/best.pt --data data/fine_tuning/data.yaml --split test > data/logs/eval_deteksi_sesudah.txt

   # 4. Evaluasi akurasi hitungan agregat (sudah ada) — sebelum dan sesudah
   python scripts/hitung_akurasi.py --dari-db --mulai "..." --sampai "..." --manual data/logs/hitungan_manual.csv --output data/logs/laporan_akurasi_sesudah.txt
   ```

3. Buat file `docs/HASIL_VALIDASI.md` sebagai tempat mengumpulkan
   semua angka di atas secara terstruktur (tabel markdown), supaya
   langsung bisa disalin ke draft naskah paper nanti:

   ```markdown
   # Hasil Validasi Sistem — untuk Naskah Paper

   ## 1. Precision/Recall/mAP Deteksi (level frame)
   | Model | mAP@0.5 | mAP@0.5:0.95 | Precision | Recall |
   |---|---|---|---|---|
   | YOLOv8s baseline (COCO) | ... | ... | ... | ... |
   | YOLOv8s fine-tuned (lokal) | ... | ... | ... | ... |
   | YOLO11s fine-tuned (lokal, opsional) | ... | ... | ... | ... |

   ## 2. MAPE Hitungan Agregat (level counting line)
   | Kelas | MAPE Sebelum | MAPE Sesudah | Target Akademis |
   |---|---|---|---|
   | Motor | ...% | ...% | ≤10% |
   | Mobil | ...% | ...% | ≤15% |
   | Bus | ...% | ...% | ≤20% |
   | Truk | ...% | ...% | ≤20% |

   ## 3. Validasi V/C Ratio MKJI vs Survei Manual
   | Tanggal | Jam | V/C Sistem | V/C Manual | Selisih |
   |---|---|---|---|---|
   | ... | ... | ... | ... | ...% |
   ```

### Definition of Done
- `scripts/evaluasi_deteksi.py` berjalan tanpa error dengan dataset
  fine-tuning yang sudah dilabel.
- `docs/HASIL_VALIDASI.md` ada, terisi minimal kerangka tabel (boleh
  kosong dulu sampai data lapangan tersedia — yang penting struktur
  siap diisi tim).

---

<a name="tahap-9"></a>
## TAHAP 9 — Dashboard: Perbaikan Informasi untuk Audiens Non-Teknis

### Masalah saat ini
Dashboard menampilkan istilah teknis ("Volume Meter-Lajur", "Occupancy
Estimasi... selisih masuk-keluar") yang sulit dipahami audiens Dishub/PU
saat demo. Setelah Tahap 2 (MKJI), dashboard perlu diperbarui untuk
menampilkan metrik yang lebih familiar sebagai metrik utama.

### Langkah eksekusi

1. `src/api_server.py`: pastikan endpoint `/api/status-terkini` (atau
   endpoint sejenis yang dipakai dashboard) menyertakan field dari hasil
   MKJI (Tahap 2), bukan hanya field meter-lajur lama. Tambahkan field
   baru ke response JSON tanpa menghapus field lama (demi backward
   compatibility):
   ```json
   {
     "volume_meter_lajur": 2220,
     "volume_smp_per_jam_mkji": 145.5,
     "kapasitas_smp_per_jam_mkji": 1890.0,
     "rasio_vc_mkji": 0.077,
     "level_of_service_mkji": "A",
     ...
   }
   ```

2. `dashboard/index.html`: ubah kartu metrik utama dari "Volume
   (Meter-Lajur)" menjadi "Volume Lalu Lintas (smp/jam)" memakai field
   `volume_smp_per_jam_mkji`, dan tambahkan label kecil "V/C Ratio: X.XX"
   di bawahnya sebagai istilah yang lebih dikenal kalangan Dinas PU
   (V/C ratio adalah istilah standar yang mereka pakai sehari-hari).

3. Ubah label "Occupancy Estimasi... selisih masuk-keluar" menjadi
   "Kendaraan di Ruas Saat Ini" dengan subtext yang lebih jelas,
   misalnya: "Estimasi jumlah kendaraan yang sedang melintasi ruas
   Sitinjau Lauik saat ini."

4. Tambahkan kartu metrik baru "Akurasi Sistem" yang menampilkan angka
   dari hasil Tahap 8 (mis. "Presisi deteksi: 92% | MAPE hitungan:
   8.5%"), dengan tooltip singkat menjelaskan artinya. Ini penting
   untuk kredibilitas — menunjukkan tim sadar akan batas akurasi sistem,
   bukan mengklaim sempurna.

5. Untuk grafik "Tren Kepadatan (2 Jam Terakhir)" yang saat ini bisa
   datar di 0 saat histori belum cukup: tambahkan pesan placeholder
   yang jelas alih-alih garis datar membingungkan:
   ```javascript
   // Di fetchRiwayat(), setelah menerima data:
   if (!json.data || json.data.length === 0) {
     // Tampilkan overlay teks "Mengumpulkan data histori..." di atas canvas chart
     // alih-alih membiarkan Chart.js menggambar garis datar di 0
   }
   ```

6. Tambahkan label arah kamera di kartu Live Camera Feeds (mis.
   "GERBANG A — Menghadap ke Padang" bukan cuma "GERBANG A — JL. PADANG
   BASI") supaya audiens yang tidak familiar geometri ruas tetap paham
   arah pergerakan yang ditampilkan.

### Definition of Done
- Dashboard menampilkan V/C ratio dan LOS berbasis MKJI sebagai metrik
  utama, bukan meter-lajur.
- Kartu "Akurasi Sistem" muncul dengan angka dari hasil validasi Tahap 8.
- Grafik tren tidak lagi menampilkan garis datar membingungkan saat data
  kosong.

---

<a name="tahap-10"></a>
## TAHAP 10 — Checklist Akhir Sebelum Demo Dishub/PU

Checklist manual (bukan kode) untuk dijalankan tim sebelum sesi demo
resmi — AI code editor bisa membantu verifikasi item bertanda [CEK KODE]
secara otomatis, sisanya kerja lapangan manusia.

- [ ] [CEK KODE] `pytest tests/ -v` — seluruh test lolos (lama + baru
      dari Tahap 1-9).
- [ ] [CEK KODE] `grep -r "postgres123\|lppm25upi" .` di root project
      (di luar `.git/`) — nol hasil.
- [ ] Password RTSP kamera dan PostgreSQL sudah diganti dari nilai lama
      yang pernah ter-expose di git history (Tahap 0 langkah 5).
- [ ] Kedua kamera (Gerbang A, Gerbang B) sudah dikalibrasi
      `pixel_per_meter` secara individual di lapangan (Tahap 4).
- [ ] NTP sync terverifikasi di kedua edge node sebelum sesi mulai
      (Tahap 5).
- [ ] Minimal 1 sesi validasi MAPE dengan hitungan manual paralel sudah
      dilakukan dan hasilnya didokumentasikan di `docs/HASIL_VALIDASI.md`
      (Tahap 8).
- [ ] Uji ketahanan: matikan-nyalakan broker MQTT / jaringan beberapa
      kali saat sistem berjalan, pastikan buffer lokal bekerja dan data
      tidak hilang/duplikat (buffer JSONL yang sudah ada di
      `event_publisher.py`).
- [ ] Restart `mqtt_consumer.py` sekali sebelum demo untuk memastikan
      recovery occupancy (Tahap 1) berjalan dan angka di dashboard tidak
      mendadak jatuh ke nol.
- [ ] Siapkan slide/penjelasan singkat metodologi MKJI 1997 yang dipakai
      (medan gunung, EMP, faktor koreksi) — audiens Dinas PU akan lebih
      percaya sistem yang secara eksplisit merujuk standar yang mereka
      kenal, dibanding "meter-lajur" custom tanpa penjelasan.
- [ ] Siapkan jawaban jujur untuk pertanyaan "seberapa akurat sistem
      ini?" — pakai angka dari `docs/HASIL_VALIDASI.md`, jangan klaim
      tanpa data.

---

## CATATAN PENUTUP UNTUK AI CODE EDITOR

Kerjakan tahap demi tahap secara berurutan. Setelah setiap tahap:
1. Jalankan `pytest tests/ -v` — semua harus lolos, termasuk test lama.
2. Commit perubahan dengan pesan jelas menyebut nomor tahap, mis.
   `git commit -m "Tahap 1: fix persistensi occupancy dual-gerbang"`.
3. Jangan lanjut ke tahap berikutnya jika ada test yang gagal — laporkan
   dulu kegagalannya secara spesifik sebelum melangkah.

Tahap 0-3 adalah prioritas TERTINGGI (keamanan, korektnes data,
kekuatan metodologi) dan sebaiknya diselesaikan lebih dulu sebelum
Tahap 6-9 (peningkatan kualitas/kenyamanan) karena Tahap 6-9 bergantung
pada fondasi yang benar dari tahap-tahap awal.
