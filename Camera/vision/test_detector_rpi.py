import sys
import os
import numpy as np
import logging

# Add current dir to path
sys.path.append(os.getcwd())

from detector import Detector

logging.basicConfig(level=logging.INFO)

def test():
    cfg = {
        "onnx_path": "models/yolov8s.onnx",
        "use_color": False,
        "conf_threshold": 0.5,
        "iou_threshold": 0.6,
        "input_size": 640
    }
    
    print("Loading detector...")
    try:
        detector = Detector(cfg["onnx_path"], cfg)
        print("Detector loaded successfully!")
        
        # Dummy frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        print("Running inference on dummy frame...")
        results = detector.detect(frame)
        print(f"Inference complete. Found {len(results)} objects.")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test()
