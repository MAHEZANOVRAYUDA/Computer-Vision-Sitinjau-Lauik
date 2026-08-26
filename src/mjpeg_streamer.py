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

def update_frame(frame):
    global _global_frame
    with _global_frame_lock:
        _global_frame = frame.copy() if frame is not None else None

async def generate_frames():
    while True:
        with _global_frame_lock:
            frame_copy = _global_frame.copy() if _global_frame is not None else None

        if frame_copy is None:
            await asyncio.sleep(0.05)
            continue

        ret, buffer = cv2.imencode(".jpg", frame_copy)
        if not ret:
            await asyncio.sleep(0.05)
            continue

        frame_bytes = buffer.tobytes()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )
        await asyncio.sleep(0.05)

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

def run_server(port: int):
    # Mengurangi noise logging dari uvicorn agar tidak menumpuk saat melayani banyak frame
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["loggers"]["uvicorn.access"]["level"] = "WARNING"
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=log_config)

def start_stream_server(port: int):
    threading.Thread(target=run_server, args=(port,), daemon=True).start()

