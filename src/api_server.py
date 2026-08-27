"""
api_server.py
==============
API server (FastAPI) yang menyajikan data untuk dashboard web.
Ini yang akan dibuka di browser saat demo ke Dishub.

Cara menjalankan (proses terpisah, di terminal ketiga):
    python -m src.api_server

Atau via uvicorn langsung:
    uvicorn src.api_server:app --host 0.0.0.0 --port 8000

Lalu buka browser ke: http://localhost:8000

Perbaikan v2:
- Inisialisasi DB dipindah ke startup event FastAPI (bukan module-level),
  mencegah crash saat file diimport oleh test runner
- Tambah endpoint /api/health untuk health check monitoring
- Tambah endpoint /api/gerbang-status mengembalikan data gerbang dari DB (bukan hardcode)
- Tambah WebSocket endpoint /ws/live untuk push live data ke dashboard
  (menggantikan HTTP polling yang inefficient)
- Logging terpusat menggantikan print()

Perbaikan v3 (Blueprint Perbaikan):
- Tambah field occupancy_metode dan confidence_note di response status
- Endpoint info-sistem menampilkan jumlah kamera aktif dan kapasitas computed
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

# Pastikan root proyek ada di sys.path agar import 'src.*' berfungsi
# baik saat dijalankan dengan 'python src/api_server.py' maupun 'python -m src.api_server'
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.config_loader import load_config
from src.database import Database
from src.logger import setup_logging, get_logger

logger = get_logger(__name__)

# --- State global untuk WebSocket manager ---
config = load_config("config/config.yaml")


class WebSocketManager:
    """
    Mengelola daftar koneksi WebSocket aktif dan broadcast data ke semua klien.
    Menggantikan HTTP polling dengan push-based updates yang lebih efisien.
    """

    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.debug(f"WebSocket terhubung. Total klien aktif: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        logger.debug(f"WebSocket terputus. Total klien aktif: {len(self.active)}")

    async def broadcast(self, data: dict):
        """Kirim data ke semua klien yang terhubung, buang koneksi yang sudah mati."""
        koneksi_mati = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                koneksi_mati.append(ws)
        for ws in koneksi_mati:
            self.disconnect(ws)


ws_manager = WebSocketManager()
db: Database = None  # Diinisialisasi di startup event


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle handler FastAPI. Kode sebelum 'yield' = startup, setelah = shutdown.
    Menggantikan @app.on_event yang deprecated di versi FastAPI terbaru.
    """
    global db
    setup_logging(
        level_str=config.get("logging.level", "INFO"),
        log_file_path=config.get("logging.file_path", "data/logs/sistem.log"),
    )
    logger.info("=" * 70)
    logger.info("API SERVER - Dashboard Sitinjau Lauik")
    logger.info("Dashboard tersedia di: http://localhost:8000")
    logger.info("=" * 70)

    db = Database(config)
    db.hubungkan()

    # Mulai task background: push data ke semua WebSocket client setiap 5 detik
    task = asyncio.create_task(_ws_broadcast_loop())

    yield  # <- Server berjalan di sini

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    db.tutup()
    logger.info("API Server dimatikan.")


app = FastAPI(title="Sitinjau Lauik Traffic API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # untuk prototipe/demo - persempit di produksi
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------
# Helper: build response status terkini
# -----------------------------------------------------------------------

def _build_status_response() -> dict:
    """Membangun response status terkini. Dipakai oleh HTTP endpoint dan WebSocket."""
    status = db.ambil_status_terbaru()
    if status is None:
        return {
            "tersedia": False,
            "pesan": "Belum ada data. Pastikan src/main.py dan src/mqtt_consumer.py sudah berjalan.",
        }

    import datetime
    from decimal import Decimal
    
    status_dict = dict(status)
    for k, v in status_dict.items():
        if isinstance(v, datetime.datetime):
            status_dict[k] = v.isoformat()
        elif isinstance(v, Decimal):
            status_dict[k] = float(v)
            
    hitungan = db.ambil_hitungan_terbaru(menit_terakhir=5)
    rincian = {"mobil": 0, "truk": 0, "bus": 0, "motor": 0}
    for row in hitungan:
        kelas = row["jenis_kendaraan"]
        rincian[kelas] = rincian.get(kelas, 0) + (row["total"] or 0)

    status_dict["rincian"] = rincian

    # Tambahkan info metodologi occupancy untuk transparansi di dashboard
    jumlah_kamera_aktif = len([k for k in config.get("kamera", []) if k.get("aktif")])
    if jumlah_kamera_aktif >= 2:
        metode = "flow_in_minus_out"
        confidence_note = "Estimasi berbasis selisih flow masuk (Gerbang A) - keluar (Gerbang B) aktual. Metode multi-kamera."
    else:
        panjang_km = float(config.get("ruas_jalan.panjang_meter", 16500)) / 1000.0
        kec = float(config.get("ruas_jalan.kecepatan_referensi_kmh", 42.0))
        waktu_tempuh_menit = round(panjang_km / kec * 60)
        metode = "flow_x_traveltime"
        confidence_note = (
            f"Estimasi berbasis 1 kamera (Gerbang A) - occupancy dihitung dari "
            f"flow masuk x estimasi waktu tempuh (~{waktu_tempuh_menit} menit). "
            "Akurasi meningkat setelah kamera Gerbang B aktif."
        )
    status_dict["occupancy_metode"] = metode
    status_dict["confidence_note"] = confidence_note

    # Tambahkan field MKJI (Tahap 9) — backward compatible, field lama tetap ada
    # Field ini diisi dari kolom MKJI di status_ruas jika tersedia
    status_dict.setdefault("volume_smp_per_jam_mkji", status_dict.get("volume_smp_jam_mkji"))
    status_dict.setdefault("kapasitas_smp_per_jam_mkji", status_dict.get("kapasitas_smp_jam_mkji"))
    status_dict.setdefault("rasio_vc_mkji", status_dict.get("rasio_vc_mkji"))
    status_dict.setdefault("level_of_service_mkji", status_dict.get("level_of_service_mkji"))
    status_dict.setdefault("status_label_mkji", status_dict.get("status_label_mkji"))

    return {"tersedia": True, "data": status_dict}


async def _ws_broadcast_loop():
    """
    Task background yang berjalan selama server aktif.
    Setiap 5 detik, mengambil data terbaru dari DB dan push ke semua
    WebSocket klien yang aktif.
    """
    while True:
        await asyncio.sleep(5)
        if ws_manager.active:
            try:
                data = _build_status_response()
                await ws_manager.broadcast(data)
            except Exception as e:
                logger.warning(f"[WS Broadcast] Error: {e}")


# -----------------------------------------------------------------------
# HTTP Endpoints
# -----------------------------------------------------------------------

@app.get("/api/status-terkini")
def status_terkini():
    """Endpoint utama - dipanggil dashboard secara berkala (polling fallback)."""
    return _build_status_response()


@app.get("/api/riwayat")
def riwayat(jam: int = 24):
    """Riwayat status untuk grafik tren di dashboard."""
    data = db.ambil_riwayat_status(jam_terakhir=jam)
    return {"jumlah_data": len(data), "data": [dict(d) for d in data]}


@app.get("/api/gerbang-status")
def gerbang_status():
    """
    Mengembalikan status gerbang kamera dari database (BUKAN hardcode).
    Dipakai dashboard untuk menampilkan status sensor yang akurat.
    """
    try:
        gerbang_list = db.ambil_status_gerbang()
        return {"gerbang": [dict(g) for g in gerbang_list]}
    except Exception as e:
        logger.warning(f"Gagal ambil status gerbang: {e}")
        return {"gerbang": []}


@app.get("/api/info-sistem")
def info_sistem():
    """Info konfigurasi dasar untuk ditampilkan di dashboard (mode prototipe, dsb)."""
    gerbang_list = []
    try:
        gerbang_list = [dict(g) for g in db.ambil_status_gerbang()]
    except Exception:
        pass

    jumlah_gerbang_aktif = sum(
        1 for g in gerbang_list if g.get("status_perangkat") == "aktif"
    )

    # Hitung berapa kamera yang aktif dari config (bukan dari DB)
    kamera_list = config.get("kamera", []) or []
    jumlah_kamera_aktif = len([k for k in kamera_list if k.get("aktif")])
    jumlah_kamera_total = len(kamera_list)

    mode_str = (
        f"PROTOTIPE {jumlah_gerbang_aktif} GERBANG"
        if jumlah_gerbang_aktif > 0
        else "PROTOTIPE - BELUM ADA GERBANG AKTIF"
    )

    # Gunakan kapasitas yang sudah dihitung (bukan nilai config mentah)
    kapasitas = (
        config.get("kapasitas_meter_lajur_computed")
        or config.get("sistem_pakar.kapasitas_meter_lajur")
    )

    return {
        "nama_ruas": "Sitinjau Lauik (Padang Basi - Jembatan Timbang Oto)",
        "mode": mode_str,
        "jumlah_gerbang_aktif": jumlah_gerbang_aktif,
        "jumlah_kamera_aktif": jumlah_kamera_aktif,
        "jumlah_kamera_total": jumlah_kamera_total,
        "catatan": (
            f"Prototipe {jumlah_kamera_aktif} dari {jumlah_kamera_total} kamera aktif. "
            "Occupancy dihitung dari flow masuk × estimasi waktu tempuh (metode 1 kamera). "
            "Untuk akurasi penuh diperlukan Gerbang A dan Gerbang B keduanya aktif."
        ),
        "kapasitas_meter_lajur": kapasitas,
        "panjang_ruas_km": float(config.get("ruas_jalan.panjang_meter", 16500)) / 1000.0,
        "kecepatan_referensi_kmh": config.get("ruas_jalan.kecepatan_referensi_kmh", 42.0),
    }


@app.get("/api/health")
def health_check():
    """
    Health check endpoint untuk monitoring (uptime robot, load balancer, dsb).
    Mengembalikan 200 OK jika server dan database bisa berkomunikasi.
    """
    try:
        db._ensure_pool()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "degraded", "database": "disconnected", "error": str(e)}


# -----------------------------------------------------------------------
# WebSocket Endpoint
# -----------------------------------------------------------------------

@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """
    WebSocket endpoint untuk live data push ke dashboard.
    Menggantikan HTTP polling yang membuat N request per detik per klien.

    Klien cukup connect sekali, data di-push server setiap 5 detik otomatis.
    """
    await ws_manager.connect(websocket)
    try:
        # Kirim data segera saat connect (tidak perlu tunggu 5 detik pertama)
        initial_data = _build_status_response()
        await websocket.send_json(initial_data)

        # Keep alive: tunggu pesan dari klien (ping/pong atau close)
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Tidak ada pesan 30 detik — kirim ping untuk cek koneksi
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# -----------------------------------------------------------------------
# Static Files & Dashboard
# -----------------------------------------------------------------------

_DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"

# Serve static assets (PNG, JS, CSS) langsung dari folder dashboard
app.mount("/static", StaticFiles(directory=str(_DASHBOARD_DIR)), name="static")

@app.get("/")
def index():
    """Root — langsung ke dashboard."""
    return FileResponse(_DASHBOARD_DIR / "index.html")

@app.get("/dashboard")
def dashboard():
    """Alias /dashboard → index.html (sesuai dokumentasi README)."""
    return FileResponse(_DASHBOARD_DIR / "index.html")

# Serve file statis secara langsung (mis. logo, gambar)
@app.get("/{filename:path}")
def serve_static(filename: str):
    """Fallback: serve file apapun dari folder dashboard jika ada."""
    file_path = _DASHBOARD_DIR / filename
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return {"error": f"File '{filename}' tidak ditemukan"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
