import time
import threading
import cv2
from flask import Flask, Response
import logging

app = Flask(__name__)
_global_frame = None
_global_frame_lock = threading.Lock()

def update_frame(frame):
    global _global_frame
    with _global_frame_lock:
        _global_frame = frame.copy() if frame is not None else None

def generate_frames():
    while True:
        with _global_frame_lock:
            frame_copy = _global_frame.copy() if _global_frame is not None else None

        if frame_copy is None:
            time.sleep(0.05)
            continue

        ret, buffer = cv2.imencode(".jpg", frame_copy)
        if not ret:
            time.sleep(0.05)
            continue

        frame_bytes = buffer.tobytes()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )
        time.sleep(0.05)

@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

def run_flask(port: int):
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def start_stream_server(port: int):
    threading.Thread(target=run_flask, args=(port,), daemon=True).start()
