# Metodologi Perhitungan — Sitinjau Lauik

Dokumen ini menjelaskan **dua metodologi berbeda** yang dihitung sistem secara paralel. Status operasional di dashboard memakai **Bagian A**. MKJI 1997 (Bagian B) adalah metrik pembanding indikatif, bukan klaim bahwa sistem “sesuai MKJI”.

Sistem ini adalah **congestion monitor** (pemantau kepadatan/kemacetan), bukan prediktor kecelakaan atau sistem keselamatan kritis.

---

## Bagian A — Occupancy-Based Congestion Detection (metrik utama)

Pendekatan Occupancy-Based Congestion Detection: status kemacetan dihitung dari rasio kepadatan kendaraan riil di ruas jalan (occupancy ratio) terhadap kapasitas volumetrik ruas (KVR), dikombinasikan dengan indikator kecepatan rata-rata (speed override) untuk menangkap kondisi bottleneck event-driven (mis. kendaraan mogok). Pendekatan ini termasuk kategori metodologi occupancy/density-based dalam teori aliran lalu lintas (traffic flow theory), **berbeda** dari pendekatan V/C ratio Manual Kapasitas Jalan Indonesia (MKJI) 1997 yang berbasis rasio arus (flow) per jam.

### A.1 Occupancy ruas (kekekalan kendaraan)

Dengan dua gerbang:

```
Occupancy(A→B, kelas) = max(0, Kumulatif_Masuk_A[kelas] − Kumulatif_Keluar_B[kelas])
Occupancy(B→A, kelas) = max(0, Kumulatif_Masuk_B[kelas] − Kumulatif_Keluar_A[kelas])
```

Ini aritmatika kekekalan: selisih masuk−keluar adalah jumlah kendaraan yang sedang berada di ruas. Validitas rumus tidak bergantung pada MKJI; yang perlu divalidasi adalah akurasi deteksi YOLO sebagai input.

### A.2 Volume meter-lajur dan KVR

```
Volume_meter_lajur = Σ (jumlah_kendaraan[kelas] × panjang_fisik[kelas])

KVR = (panjang_ruas × pct_sempit × kapasitas_lateral_sempit)
    + (panjang_ruas × pct_lebar × kapasitas_lateral_lebar)

Persentase_kepadatan = (Volume_meter_lajur / KVR) × 100%
```

Contoh Sitinjau Lauik (parameter dosen): panjang 16 500 m, 65% sempit (2 unit), 35% lebar (6 unit) → KVR = 56 100.

Kolom database `rasio_vc` pada status utama **bukan** V/C MKJI; isinya `Persentase_kepadatan / 100` (occupancy ratio) agar skema lama tetap kompatibel.

### A.3 Status LANCAR / PADAT / MACET + LOS A–F

Ambang operasional default (masih meniru breakpoint LOS, **belum** dikalibrasi ulang dengan observasi lapangan Sitinjau Lauik kecuali dinyatakan di `docs/HASIL_VALIDASI_LAPANGAN.md`):

- LANCAR jika kepadatan ≤ `ambang_lancar` (config)
- PADAT jika `ambang_lancar` < kepadatan ≤ `ambang_padat`
- MACET jika kepadatan > `ambang_padat`

Label LOS A–F pada metrik utama memakai ambang 20 / 44 / 75 / 84 / 100 **sebagai skala bantu**, bukan klaim V/C MKJI.

### A.4 Hybrid speed override

Jika kecepatan rata-rata terukur < ambang (default 15 km/jam, atau terpisah naik/turun jika dikonfigurasi), status dipaksa **macet** terlepas dari occupancy. Ini menangkap bottleneck event-driven (truk mogok) saat occupancy masih rendah.

Angka ambang kecepatan adalah asumsi awal sampai divalidasi data lapangan. Arah naik (tanjakan) secara wajar memakai ambang lebih rendah daripada arah turun.

---

## Bagian B — MKJI 1997 (metrik pembanding)

Dihitung **setelah** evaluasi occupancy, dari arus 15 menit terakhir yang diekstrapolasi ke smp/jam (`× 4`).

```
C = C0 × FCw × FCsp × FCsf × FCcs
```

- C0 = 2900 smp/jam (jalan 2/2 UD, Tabel 5-2 MKJI 1997)
- Volume smp memakai EMP medan gunung (motor 0,4; mobil 1,0; bus 3,25; truk 5,0 — titik tengah rentang, wajib survei lapangan)

**Catatan jujur:** gradien Sitinjau Lauik sekitar 20–26% melebihi cakupan normal MKJI untuk kategori “gunung” (umumnya dikaitkan dengan gradien lebih rendah). Hasil V/C dan LOS MKJI bersifat **indikatif**. Jangan dipakai sebagai satu-satunya dasar keputusan operasional.

Kolom: `rasio_vc_mkji`, `level_of_service_mkji`, `status_label_mkji`, `volume_smp_jam_mkji`, `kapasitas_smp_jam_mkji`.

---

## Referensi konsep (bukan klaim implementasi MKJI)

- Greenshields (1935) dan diagram fundamental `q = k · v` — membedakan density/occupancy vs flow/V-C.
- Occupancy-based congestion detection (praktik loop detector / ITS).
- Hybrid occupancy + kecepatan untuk fase lalu lintas (literatur flow+speed).
