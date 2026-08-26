import os
import argparse
import logging
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(asctime)s - MODEL OPTIMIZER - %(levelname)s - %(message)s")

def optimize_model(weights_path: str, format: str = "onnx", imgsz: int = 416, int8: bool = False):
    """
    Export a YOLOv8 .pt model to an optimized format for Edge inference.
    Recommended for Raspberry Pi: 'onnx' or 'ncnn'.
    """
    if not os.path.exists(weights_path):
        logging.error(f"Weights file not found: {weights_path}")
        return

    logging.info(f"Loading model: {weights_path}")
    model = YOLO(weights_path)

    logging.info(f"Exporting to format: {format} with imgsz: {imgsz}, int8: {int8}")
    try:
        exported_path = model.export(
            format=format,
            imgsz=imgsz,
            half=not int8,  # Use FP16 if not INT8
            int8=int8,      # Quantize to INT8 for extreme CPU performance
            simplify=True   # Simplify ONNX model
        )
        logging.info(f"Export successful. Optimized model saved to: {exported_path}")
    except Exception as e:
        logging.error(f"Export failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimize YOLO models for Edge/Raspberry Pi")
    parser.add_argument("--weights", type=str, default="models/yolov8n.pt", help="Path to input .pt model")
    parser.add_argument("--format", type=str, default="ncnn", choices=["onnx", "ncnn", "tflite", "engine"], help="Export format")
    parser.add_argument("--imgsz", type=int, default=416, help="Inference size")
    parser.add_argument("--int8", action="store_true", help="Enable INT8 quantization")

    args = parser.parse_args()
    optimize_model(args.weights, args.format, args.imgsz, args.int8)
