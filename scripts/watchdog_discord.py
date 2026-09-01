#!/usr/bin/env python3
"""
watchdog_discord.py
Script untuk mengirim notifikasi ke Discord Webhook.
Jalankan via cron setiap 5 menit.
"""
import sys
import time
import requests
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.config_loader import load_config
from src.database import Database

def main():
    config = load_config("config/config.yaml")
    
    # URL Webhook Discord
    WEBHOOK_URL = config.get("discord.webhook_url", "")
    if not WEBHOOK_URL:
        print("Webhook URL tidak diset. Tambahkan discord.webhook_url di config.yaml.")
        return
        
    db = Database(config)
    db.hubungkan()
    
    # 1. Cek status macet
    try:
        status = db.ambil_status_terbaru()
        if status and status.get("status_label") == "macet":
            waktu_str = status.get("timestamp_hitung").strftime("%Y-%m-%d %H:%M:%S")
            msg = f"⚠️ **PERINGATAN KEMACETAN** ⚠️\nSitinjau Lauik terdeteksi MACET pada {waktu_str}.\nRasio V/C: {status.get('rasio_vc', 0):.2f}"
            
            payload = {"content": msg}
            requests.post(WEBHOOK_URL, json=payload)
            print("Notifikasi kemacetan terkirim.")
    except Exception as e:
        print(f"Error cek status: {e}")
        
    # 2. Cek heartbeat docker
    heartbeat_file = Path("data/logs/heartbeat_main.txt")
    if heartbeat_file.exists():
        try:
            last_hb = int(heartbeat_file.read_text().strip())
            if time.time() - last_hb > 300: # 5 menit mati
                msg = "🚨 **SISTEM OFFLINE** 🚨\nEdge Node Sitinjau Lauik tidak merespon (heartbeat mati lebih dari 5 menit)."
                requests.post(WEBHOOK_URL, json={"content": msg})
                print("Notifikasi offline terkirim.")
        except Exception as e:
            pass
            
    db.tutup()

if __name__ == "__main__":
    main()
