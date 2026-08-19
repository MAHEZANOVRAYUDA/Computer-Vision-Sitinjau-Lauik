"""
hitung_akurasi.py
==================
Script untuk menghitung akurasi sistem CV dibandingkan dengan
penghitungan manual (ground truth).

Cara pakai:
    python scripts/hitung_akurasi.py --sistem data/logs/hasil_sistem.csv --manual data/logs/hasil_manual.csv

Atau query langsung dari database:
    python scripts/hitung_akurasi.py --dari-db --mulai "2026-08-18 07:00:00" --sampai "2026-08-18 07:30:00"

Format file CSV yang diharapkan:
  hasil_sistem.csv:
    interval,arah,kelas,jumlah
    2026-08-18 07:00:00,masuk,motor,45
    ...

  hasil_manual.csv:
    interval,arah,kelas,jumlah
    2026-08-18 07:00:00,masuk,motor,50
    ...

Output:
  - MAPE per kelas kendaraan
  - MAPE keseluruhan
  - Precision / Recall estimasi (jika ada data ground truth deteksi)
  - Rekomendasi: apakah perlu fine-tuning YOLO?
"""

import argparse
import sys
from pathlib import Path

# Tambah root proyek ke sys.path agar bisa import src.*
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("[ERROR] pandas dan numpy diperlukan.")
    print("Install dengan: pip install pandas numpy")
    sys.exit(1)


# =========================================================================
# Konstanta target akurasi
# =========================================================================

TARGET_MAPE = {
    "motor": 10.0,   # target akademis: ≤10% (kelas paling dominan)
    "mobil": 15.0,   # target: ≤15%
    "truk":  20.0,   # target: ≤20%
    "bus":   20.0,   # target: ≤20%
    "all":   15.0,   # target keseluruhan: ≤15%
}

MINIMUM_MAPE = {
    "motor": 20.0,   # minimum prototipe demo: ≤20%
    "mobil": 25.0,
    "truk":  30.0,
    "bus":   30.0,
    "all":   25.0,
}

GARIS_SEPARATOR = "=" * 70


# =========================================================================
# Fungsi kalkulasi
# =========================================================================

def hitung_mape(actual: pd.Series, predicted: pd.Series) -> float:
    """
    Mean Absolute Percentage Error.
    Mengabaikan baris dengan actual=0 (hindari division by zero).
    """
    mask = actual > 0
    if mask.sum() == 0:
        return float("nan")
    return float(((predicted[mask] - actual[mask]).abs() / actual[mask]).mean() * 100)


def hitung_akurasi_dari_df(
    df_sistem: pd.DataFrame,
    df_manual: pd.DataFrame,
) -> dict:
    """
    Menghitung MAPE per kelas dan keseluruhan dari dua DataFrame.

    Args:
        df_sistem: kolom [interval, arah, kelas, jumlah] — hasil sistem CV
        df_manual: kolom [interval, arah, kelas, jumlah] — hitungan manual

    Returns:
        dict dengan hasil MAPE per kelas dan keseluruhan
    """
    # Pastikan kolom ada
    for df, nama in [(df_sistem, "sistem"), (df_manual, "manual")]:
        kolom_wajib = {"interval", "arah", "kelas", "jumlah"}
        kolom_ada = set(df.columns)
        if not kolom_wajib.issubset(kolom_ada):
            missing = kolom_wajib - kolom_ada
            raise ValueError(f"File {nama} kekurangan kolom: {missing}")

    # Merge berdasarkan (interval, arah, kelas)
    merged = df_sistem.merge(
        df_manual,
        on=["interval", "arah", "kelas"],
        suffixes=("_sistem", "_manual"),
        how="outer",
    ).fillna(0)

    hasil = {}

    # MAPE per kelas
    for kelas in ["motor", "mobil", "truk", "bus"]:
        subset = merged[merged["kelas"] == kelas]
        if len(subset) == 0:
            hasil[kelas] = {"mape": float("nan"), "n_interval": 0, "total_sistem": 0, "total_manual": 0}
            continue
        mape = hitung_mape(subset["jumlah_manual"], subset["jumlah_sistem"])
        hasil[kelas] = {
            "mape": round(mape, 2),
            "n_interval": len(subset),
            "total_sistem": int(subset["jumlah_sistem"].sum()),
            "total_manual": int(subset["jumlah_manual"].sum()),
        }

    # MAPE keseluruhan
    mape_all = hitung_mape(merged["jumlah_manual"], merged["jumlah_sistem"])
    hasil["all"] = {
        "mape": round(mape_all, 2),
        "n_interval": len(merged),
        "total_sistem": int(merged["jumlah_sistem"].sum()),
        "total_manual": int(merged["jumlah_manual"].sum()),
    }

    return hasil


def cetak_laporan(hasil: dict, simpan_ke: str = None):
    """Mencetak laporan akurasi ke terminal dan opsional ke file."""
    lines = []
    lines.append(GARIS_SEPARATOR)
    lines.append("LAPORAN AKURASI SISTEM CV — Sitinjau Lauik")
    lines.append(GARIS_SEPARATOR)
    lines.append("")

    # Tabel per kelas
    header = f"{'Kelas':<10} {'MAPE (%)':>10} {'Status':>10} {'Sistem':>10} {'Manual':>10} {'N-interval':>12}"
    lines.append(header)
    lines.append("-" * len(header))

    perlu_fine_tuning = False

    for kelas in ["motor", "mobil", "truk", "bus", "all"]:
        data = hasil.get(kelas, {})
        mape = data.get("mape", float("nan"))

        if kelas == "all":
            lines.append("")

        if pd.isna(mape):
            status = "TIDAK ADA DATA"
        elif mape <= TARGET_MAPE.get(kelas, 15.0):
            status = "✅ TARGET"
        elif mape <= MINIMUM_MAPE.get(kelas, 25.0):
            status = "⚠️ MINIMUM"
        else:
            status = "❌ BURUK"
            perlu_fine_tuning = True

        mape_str = f"{mape:.1f}%" if not pd.isna(mape) else "—"
        lines.append(
            f"{kelas.upper():<10} {mape_str:>10} {status:>10} "
            f"{data.get('total_sistem', 0):>10} {data.get('total_manual', 0):>10} "
            f"{data.get('n_interval', 0):>12}"
        )

    lines.append("")
    lines.append(GARIS_SEPARATOR)

    if perlu_fine_tuning:
        lines.append("")
        lines.append("⚠️  REKOMENDASI: MAPE di atas ambang minimum untuk beberapa kelas.")
        lines.append("   Fine-tuning YOLO dengan data lokal Sitinjau Lauik SANGAT DISARANKAN.")
        lines.append("   Panduan: lihat docs/VALIDASI_AKURASI.md bagian 6 (Fine-Tuning YOLOv8)")
    else:
        mape_all = hasil.get("all", {}).get("mape", float("nan"))
        if not pd.isna(mape_all) and mape_all <= TARGET_MAPE["all"]:
            lines.append("")
            lines.append("✅ Akurasi memenuhi target untuk publikasi akademis.")
        else:
            lines.append("")
            lines.append("⚠️  Akurasi memenuhi minimum prototipe tapi belum layak publikasi.")
            lines.append("   Pertimbangkan fine-tuning untuk meningkatkan akurasi.")

    lines.append(GARIS_SEPARATOR)

    laporan = "\n".join(lines)
    print(laporan)

    if simpan_ke:
        Path(simpan_ke).parent.mkdir(parents=True, exist_ok=True)
        with open(simpan_ke, "w", encoding="utf-8") as f:
            f.write(laporan)
        print(f"\n[INFO] Laporan disimpan ke: {simpan_ke}")


def query_dari_database(config_path: str, mulai: str, sampai: str) -> pd.DataFrame:
    """
    Query hasil sistem dari database PostgreSQL.

    Args:
        config_path: path ke config.yaml
        mulai: timestamp mulai ISO format (mis. "2026-08-18 07:00:00")
        sampai: timestamp sampai ISO format

    Returns:
        DataFrame dengan kolom [interval, arah, kelas, jumlah]
    """
    from src.config_loader import load_config
    import psycopg2
    import psycopg2.extras

    config = load_config(config_path)

    conn = psycopg2.connect(
        host=config.get("database.host", "localhost"),
        port=config.get("database.port", 5432),
        dbname=config.get("database.name", "sitinjau_lauik_db"),
        user=config.get("database.user", "postgres"),
        password=config.get("database.password", ""),
        connect_timeout=10,
    )

    query = """
        SELECT
            DATE_TRUNC('minute', timestamp_interval) AS interval,
            arah,
            jenis_kendaraan AS kelas,
            SUM(jumlah_terhitung) AS jumlah
        FROM hitungan_kendaraan
        WHERE timestamp_interval >= %s
          AND timestamp_interval <  %s
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
    """

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, (mulai, sampai))
        rows = cur.fetchall()

    conn.close()
    return pd.DataFrame([dict(r) for r in rows])


# =========================================================================
# CLI
# =========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hitung akurasi sistem CV Sitinjau Lauik vs hitungan manual.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  # Dari file CSV
  python scripts/hitung_akurasi.py --sistem data/logs/hasil_sistem.csv --manual data/logs/hasil_manual.csv

  # Dari database (query langsung)
  python scripts/hitung_akurasi.py --dari-db --mulai "2026-08-18 07:00:00" --sampai "2026-08-18 07:30:00"

  # Simpan laporan ke file
  python scripts/hitung_akurasi.py --sistem hasil_sistem.csv --manual hasil_manual.csv --output data/logs/laporan_akurasi.txt

Format CSV:
  interval,arah,kelas,jumlah
  2026-08-18 07:00:00,masuk,motor,45
  2026-08-18 07:00:00,masuk,mobil,12
        """,
    )

    parser.add_argument("--sistem", type=str, help="Path ke CSV hasil sistem CV")
    parser.add_argument("--manual", type=str, help="Path ke CSV hitungan manual (ground truth)")
    parser.add_argument("--dari-db", action="store_true", help="Query hasil sistem dari database")
    parser.add_argument("--mulai", type=str, help="Timestamp mulai (format: 'YYYY-MM-DD HH:MM:SS')")
    parser.add_argument("--sampai", type=str, help="Timestamp sampai (format: 'YYYY-MM-DD HH:MM:SS')")
    parser.add_argument("--config", type=str, default="config/config.yaml", help="Path config YAML")
    parser.add_argument("--output", type=str, help="Path untuk menyimpan laporan teks")

    args = parser.parse_args()

    # Validasi argumen
    if args.dari_db:
        if not args.mulai or not args.sampai:
            parser.error("--dari-db memerlukan --mulai dan --sampai")
        if not args.manual:
            parser.error("--dari-db memerlukan --manual (file ground truth manual)")

        print(f"[INFO] Mengambil data sistem dari database ({args.mulai} → {args.sampai})...")
        try:
            df_sistem = query_dari_database(args.config, args.mulai, args.sampai)
            print(f"[INFO] {len(df_sistem)} baris data sistem dari DB")
        except Exception as e:
            print(f"[ERROR] Gagal query database: {e}")
            sys.exit(1)
        df_manual = pd.read_csv(args.manual)

    elif args.sistem and args.manual:
        if not Path(args.sistem).exists():
            print(f"[ERROR] File tidak ditemukan: {args.sistem}")
            sys.exit(1)
        if not Path(args.manual).exists():
            print(f"[ERROR] File tidak ditemukan: {args.manual}")
            sys.exit(1)
        df_sistem = pd.read_csv(args.sistem)
        df_manual = pd.read_csv(args.manual)

    else:
        parser.error("Harus menyediakan --sistem dan --manual, atau --dari-db")

    print(f"[INFO] Data sistem : {len(df_sistem)} baris")
    print(f"[INFO] Data manual : {len(df_manual)} baris")
    print()

    try:
        hasil = hitung_akurasi_dari_df(df_sistem, df_manual)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    cetak_laporan(hasil, simpan_ke=args.output)


if __name__ == "__main__":
    main()
