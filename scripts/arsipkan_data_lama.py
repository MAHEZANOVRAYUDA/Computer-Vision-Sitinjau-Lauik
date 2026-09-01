#!/usr/bin/env python3
"""
arsipkan_data_lama.py
Hapus/arsipkan data hitungan_kendaraan dan status_ruas yang lebih tua dari 30 hari.
Jalankan via cron bulanan.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.config_loader import load_config
from src.database import Database

def main():
    config = load_config("config/config.yaml")
    db = Database(config)
    db.hubungkan()
    
    try:
        # Hapus data lebih tua dari 30 hari
        db.eksekusi("DELETE FROM hitungan_kendaraan WHERE timestamp_interval < NOW() - INTERVAL '30 days'", fetch=False)
        db.eksekusi("DELETE FROM status_ruas WHERE timestamp_hitung < NOW() - INTERVAL '30 days'", fetch=False)
        print("Data lama berhasil dihapus/diarsipkan (lebih dari 30 hari).")
    except Exception as e:
        print(f"Gagal mengarsipkan data: {e}")
    finally:
        db.tutup()

if __name__ == "__main__":
    main()
