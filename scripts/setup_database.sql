-- =====================================================================
-- SCHEMA DATABASE - Sistem Deteksi Kemacetan Sitinjau Lauik
-- Sesuai Blueprint 4 (Skema Basis Data) dari dokumen final
-- =====================================================================
-- Cara pakai: lihat docs/PANDUAN_SETUP.docx bagian "Setup Database"
-- Atau jalankan langsung: psql -U postgres -f scripts/setup_database.sql
-- =====================================================================

-- Buat database (jalankan ini terpisah jika database belum ada)
-- CREATE DATABASE sitinjau_lauik_db;

-- Setelah masuk ke database sitinjau_lauik_db, jalankan sisa script ini:

-- ---------------------------------------------------------------------
-- Tabel 1: ruas_jalan
-- Metadata ruas jalan yang dipantau (untuk prototipe: hanya 1 ruas)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ruas_jalan (
    id_ruas         SERIAL PRIMARY KEY,
    nama_ruas       VARCHAR(255) NOT NULL,
    panjang_meter   NUMERIC(10, 2),
    jumlah_lajur    INTEGER NOT NULL DEFAULT 2,
    kapasitas_dasar_smp_jam NUMERIC(10, 2),  -- hasil survei MKJI, atau nilai sementara untuk prototipe
    koordinat_lat_a NUMERIC(10, 7),
    koordinat_lng_a NUMERIC(10, 7),
    koordinat_lat_b NUMERIC(10, 7),
    koordinat_lng_b NUMERIC(10, 7),
    status_aktif    BOOLEAN DEFAULT TRUE,
    dibuat_pada     TIMESTAMP DEFAULT NOW()
);

-- ---------------------------------------------------------------------
-- Tabel 2: gerbang_kamera
-- Titik pemasangan kamera (Gerbang A, Gerbang B)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gerbang_kamera (
    id_gerbang      VARCHAR(50) PRIMARY KEY,  -- mis. "gerbang_a"
    id_ruas         INTEGER REFERENCES ruas_jalan(id_ruas),
    nama_gerbang    VARCHAR(255) NOT NULL,
    arah_menghadap  VARCHAR(50),  -- "ke_padang" atau "ke_solok"
    ip_address      VARCHAR(50),
    status_perangkat VARCHAR(20) DEFAULT 'aktif',  -- aktif / nonaktif / maintenance
    dibuat_pada     TIMESTAMP DEFAULT NOW()
);

-- ---------------------------------------------------------------------
-- Tabel 3: hitungan_kendaraan (fact table - data agregat per interval)
-- TIDAK menyimpan identitas kendaraan individual, sesuai keputusan
-- privasi di dokumen blueprint asli.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hitungan_kendaraan (
    id_hitungan     BIGSERIAL PRIMARY KEY,
    id_gerbang      VARCHAR(50) REFERENCES gerbang_kamera(id_gerbang),
    timestamp_interval TIMESTAMP NOT NULL,
    lajur_id        VARCHAR(50) NOT NULL,       -- "lajur_kiri" / "lajur_kanan"
    arah            VARCHAR(10) NOT NULL,        -- "masuk" / "keluar"
    jenis_kendaraan VARCHAR(20) NOT NULL,        -- "motor" / "mobil" / "bus" / "truk"
    jumlah_terhitung INTEGER NOT NULL DEFAULT 0,
    arah_topografi  VARCHAR(10),                 -- "naik" / "turun"
    dibuat_pada     TIMESTAMP DEFAULT NOW()
);

-- Index untuk mempercepat query berdasarkan waktu dan gerbang (dipakai terus oleh dashboard)
CREATE INDEX IF NOT EXISTS idx_hitungan_timestamp ON hitungan_kendaraan(timestamp_interval);
CREATE INDEX IF NOT EXISTS idx_hitungan_gerbang ON hitungan_kendaraan(id_gerbang);

ALTER TABLE hitungan_kendaraan
  ADD COLUMN IF NOT EXISTS arah_topografi VARCHAR(10);

-- ---------------------------------------------------------------------
-- Tabel 4: status_ruas (hasil klasifikasi sistem pakar)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS status_ruas (
    id_status       BIGSERIAL PRIMARY KEY,
    id_ruas         INTEGER REFERENCES ruas_jalan(id_ruas),
    timestamp_hitung TIMESTAMP NOT NULL,
    total_kendaraan_saat_ini INTEGER,  -- occupancy, semua kelas dijumlah
    volume_smp      NUMERIC(10, 2),
    rasio_vc        NUMERIC(6, 4),
    level_of_service VARCHAR(5),   -- A-F sesuai MKJI
    status_label    VARCHAR(20),   -- "lancar" / "padat" / "macet"
    teks_rekomendasi TEXT,
    -- Kolom MKJI 1997 (Tahap 2 Blueprint v4)
    volume_smp_jam_mkji     NUMERIC(10, 2),
    kapasitas_smp_jam_mkji  NUMERIC(10, 2),
    rasio_vc_mkji           NUMERIC(6, 4),
    level_of_service_mkji   VARCHAR(5),
    status_label_mkji       VARCHAR(20),
    dibuat_pada     TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_status_timestamp ON status_ruas(timestamp_hitung);

-- ALTER TABLE untuk database yang sudah ada (idempoten, aman dijalankan ulang)
ALTER TABLE status_ruas
  ADD COLUMN IF NOT EXISTS volume_smp_jam_mkji NUMERIC(10, 2),
  ADD COLUMN IF NOT EXISTS kapasitas_smp_jam_mkji NUMERIC(10, 2),
  ADD COLUMN IF NOT EXISTS rasio_vc_mkji NUMERIC(6, 4),
  ADD COLUMN IF NOT EXISTS level_of_service_mkji VARCHAR(5),
  ADD COLUMN IF NOT EXISTS status_label_mkji VARCHAR(20);


-- ---------------------------------------------------------------------
-- Data awal (seed) untuk prototipe: 1 ruas jalan + Gerbang A
-- ---------------------------------------------------------------------
INSERT INTO ruas_jalan (
    nama_ruas, jumlah_lajur, kapasitas_dasar_smp_jam,
    koordinat_lat_a, koordinat_lng_a, koordinat_lat_b, koordinat_lng_b
) VALUES (
    'Sitinjau Lauik (Padang Basi - Jembatan Timbang Oto)', 2, 1500,
    -0.9514185, 100.4814637, -0.9608433, 100.5760363
) ON CONFLICT DO NOTHING;

INSERT INTO gerbang_kamera (id_gerbang, id_ruas, nama_gerbang, arah_menghadap, status_perangkat)
VALUES ('gerbang_a', 1, 'Gerbang A - Jl. Padang Basi', 'ke_padang', 'aktif')
ON CONFLICT (id_gerbang) DO NOTHING;

-- Gerbang B: aktif untuk mode demo/prototipe 2 kamera
INSERT INTO gerbang_kamera (id_gerbang, id_ruas, nama_gerbang, arah_menghadap, status_perangkat)
VALUES ('gerbang_b', 1, 'Gerbang B - Jembatan Timbang Oto', 'ke_solok', 'aktif')
ON CONFLICT (id_gerbang) DO NOTHING;
