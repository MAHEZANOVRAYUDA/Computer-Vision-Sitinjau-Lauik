"""
mjpeg_streamer.py
==================
Server MJPEG streaming yang efisien untuk feed video dari edge node.
Menggunakan frame rate limiter untuk mencegah CPU terbebani hanya untuk encode.

Optimasi:
- Frame rate dibatasi maksimal 8 FPS untuk streaming (tidak perlu lebih)
- JPEG quality 50 (cukup untuk monitoring, jauh lebih ringan dari 85+)
- Thread-safe frame sharing dengan lock
"""
import time
import threading
import asyncio
import cv2
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import logging

app = FastAPI()
_global_frame = None
_global_frame_lock = threading.Lock()
_last_encode_time = 0.0

# Batas FPS untuk stream (tidak perlu lebih dari 8 FPS untuk monitoring)
_STREAM_MAX_FPS = 8
_STREAM_MIN_INTERVAL = 1.0 / _STREAM_MAX_FPS  # ~0.125 detik


def update_frame(frame):
    """Update frame terbaru (dipanggil dari main loop setiap frame diproses)."""
    global _global_frame
    with _global_frame_lock:
        _global_frame = frame.copy() if frame is not None else None


async def generate_frames():
    """Generator async untuk MJPEG stream dengan frame rate limiter."""
    global _last_encode_time
    while True:
        now = time.time()
        elapsed = now - _last_encode_time

        # Batasi frame rate — jika terlalu cepat, tunggu dulu
        if elapsed < _STREAM_MIN_INTERVAL:
            await asyncio.sleep(_STREAM_MIN_INTERVAL - elapsed)
            continue

        with _global_frame_lock:
            frame_copy = _global_frame.copy() if _global_frame is not None else None

        if frame_copy is None:
            await asyncio.sleep(0.1)
            continue

        # Encode JPEG dengan quality 50 — cukup untuk monitoring, hemat bandwidth
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
        ret, buffer = cv2.imencode(".jpg", frame_copy, encode_param)
        if not ret:
            await asyncio.sleep(0.05)
            continue

        _last_encode_time = time.time()
        frame_bytes = buffer.tobytes()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )


@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/health")
async def health():
    return {"status": "ok", "streaming": _global_frame is not None}


def run_server(port: int):
    # Kurangi noise logging dari uvicorn
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["loggers"]["uvicorn.access"]["level"] = "WARNING"
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=log_config)


def start_stream_server(port: int):
    threading.Thread(target=run_server, args=(port,), daemon=True).start()
