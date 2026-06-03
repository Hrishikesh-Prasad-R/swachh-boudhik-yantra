# Vision Module — Swachh Boudhik Yantra

Self-contained vision inference package. Drop this entire folder into the `Navigation/` directory.

## Folder Structure
```
vision/
├── run.sh            ← Entry point: launches the full pipeline
├── config.yaml       ← All tunable parameters
├── main.py           ← Orchestrator: camera → detect → depth → serial
├── camera.py         ← Dual stereo camera capture (MJPEG, 10 FPS)
├── detector.py       ← YOLOv8s TensorRT inference + class filter
├── depth.py          ← Stereo disparity → depth (Z in metres)
├── serial_comm.py    ← Arduino serial handshake (ARM:PICK command)
├── models/
│   ├── yolov8s.engine  ← TensorRT compiled model (runs on Jetson)
│   └── yolov8s.onnx    ← Original ONNX model (for reference)
└── calib/
    └── stereo_calib.npz  ← Stereo calibration data (from calib.sh)
```

## Classes Detected
| Class | COCO ID | Notes |
|-------|---------|-------|
| Bottle | 39 | Most common litter |
| Cup | 41 | Plastic cups |
| Remote | 65 | Small object |
| Cell phone | 67 | Common dropped item |
| Book | 73 | Paper litter |
| Scissors | 76 | Hazardous sharp |
| Toothbrush | 79 | Hygiene waste |

## Confidence / Stability Rules
- **conf_threshold: 0.50** — Detection must score > 50% confidence
- **stable_frames: 2** — Must appear in 2 consecutive frames before sending  
  `ARM:PICK x,y,z` to Arduino

## Usage
```bash
cd Navigation/vision
chmod +x run.sh
./run.sh
```

## Re-calibration
If cameras are moved, run `../mvp/calib.sh` and copy the new `calib/stereo_calib.npz` here.
