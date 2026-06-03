"""
app.py
======
Streamlit YOLOv8s object detection app using ONNX Runtime.
No PyTorch / CUDA required - runs on Raspberry Pi.

Run:
  venv/bin/streamlit run app.py

Requires:
  pip install streamlit onnxruntime opencv-python-headless pillow numpy
"""

import streamlit as st
import cv2
import numpy as np
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
HERE       = Path(__file__).parent
ONNX_MODEL = HERE / "new_yolov8_best.onnx"

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="YOLOv8s | Object Detector",
    page_icon="[CAM]",
    layout="wide",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp {
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    color: #ffffff;
}

[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.07);
    backdrop-filter: blur(16px);
    border-right: 1px solid rgba(255,255,255,0.12);
}

.metric-card {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 16px;
    padding: 1rem 1.4rem;
    margin-bottom: 0.7rem;
    backdrop-filter: blur(8px);
}

.model-badge {
    background: linear-gradient(90deg, #7928CA, #FF0080);
    color: white;
    border-radius: 20px;
    padding: 4px 18px;
    font-weight: 700;
    font-size: 0.9rem;
    display: inline-block;
    margin-bottom: 1rem;
}

.detection-title {
    font-size: 2rem;
    font-weight: 900;
    background: linear-gradient(90deg, #a78bfa, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

h1,h2,h3 { color: #e2e8f0; }

.stButton>button {
    background: linear-gradient(90deg, #7928CA, #FF0080);
    color: white;
    border: none;
    border-radius: 10px;
    font-weight: 600;
    padding: 0.5rem 1.5rem;
}
.stButton>button:hover { opacity: 0.85; }
</style>
""", unsafe_allow_html=True)

# ── Colour palette ────────────────────────────────────────────────────────────
PALETTE = [
    (255,  82,  82), (255, 165,   0), (255, 215,   0), ( 50, 205,  50),
    (  0, 191, 255), (138,  43, 226), (255,  20, 147), (  0, 250, 154),
    (255, 140,   0), ( 30, 144, 255), (220,  20,  60), (124, 252,   0),
    (255,  69,   0), ( 64, 224, 208), (148,   0, 211), (  0, 128, 128),
]

def get_colour(cls_id: int):
    return PALETTE[cls_id % len(PALETTE)]

# ── ONNX model loader ─────────────────────────────────────────────────────────
@st.cache_resource
def load_model():
    import onnxruntime as ort
    if not ONNX_MODEL.exists():
        st.error(f"ONNX model not found: {ONNX_MODEL}")
        st.stop()
    session = ort.InferenceSession(
        str(ONNX_MODEL),
        providers=["CPUExecutionProvider"]
    )
    return session

# ── Pre/post-processing ───────────────────────────────────────────────────────
INPUT_SIZE = 640

def preprocess(frame_bgr):
    img = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]
    scale = INPUT_SIZE / max(h, w)
    nh, nw = int(h * scale), int(w * scale)
    img = cv2.resize(img, (nw, nh))
    canvas = np.full((INPUT_SIZE, INPUT_SIZE, 3), 114, dtype=np.uint8)
    pad_y, pad_x = (INPUT_SIZE - nh) // 2, (INPUT_SIZE - nw) // 2
    canvas[pad_y:pad_y+nh, pad_x:pad_x+nw] = img
    inp = canvas.astype(np.float32) / 255.0
    inp = np.transpose(inp, (2, 0, 1))[np.newaxis]
    return inp, scale, pad_x, pad_y

def postprocess(outputs, scale, pad_x, pad_y, conf_thresh, class_names):
    preds = outputs[0][0].T          # [8400, 4+nc]
    boxes_raw = preds[:, :4]
    scores    = preds[:, 4:]
    cls_ids   = scores.argmax(axis=1)
    cls_confs = scores.max(axis=1)
    mask = cls_confs >= conf_thresh
    boxes_raw = boxes_raw[mask]
    cls_ids   = cls_ids[mask]
    cls_confs = cls_confs[mask]
    detections = []
    for box, cls_id, conf in zip(boxes_raw, cls_ids, cls_confs):
        cx, cy, bw, bh = box
        x1 = int((cx - bw / 2 - pad_x) / scale)
        y1 = int((cy - bh / 2 - pad_y) / scale)
        x2 = int((cx + bw / 2 - pad_x) / scale)
        y2 = int((cy + bh / 2 - pad_y) / scale)
        label = class_names[cls_id] if cls_id < len(class_names) else str(cls_id)
        detections.append((x1, y1, x2, y2, label, float(conf), int(cls_id)))
    return detections

def draw_detections(frame_bgr, detections):
    counts = {}
    for x1, y1, x2, y2, label, conf, cls_id in detections:
        colour = get_colour(cls_id)
        cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), colour, 2)
        text = f"{label} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(frame_bgr, (x1, y1 - th - 8), (x1 + tw + 6, y1), colour, -1)
        cv2.putText(frame_bgr, text, (x1 + 3, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        counts[label] = counts.get(label, 0) + 1
    return frame_bgr, counts

def run_inference(frame_bgr, session, conf_thresh, class_names):
    inp, scale, pad_x, pad_y = preprocess(frame_bgr)
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: inp})
    detections = postprocess(outputs, scale, pad_x, pad_y, conf_thresh, class_names)
    return draw_detections(frame_bgr, detections)

def get_class_names(session):
    try:
        import ast
        meta = session.get_modelmeta().custom_metadata_map
        names_dict = ast.literal_eval(meta.get("names", "{}"))
        return [names_dict[i] for i in sorted(names_dict.keys())]
    except Exception:
        return [f"class_{i}" for i in range(80)]

# ── Main UI ───────────────────────────────────────────────────────────────────
def main():
    with st.sidebar:
        st.markdown('<div class="model-badge">YOLOv8s ONNX</div>', unsafe_allow_html=True)
        st.markdown("### Settings")
        conf   = st.slider("Confidence threshold", 0.10, 0.95, 0.40, 0.05)
        cam_id = st.number_input("Camera index", 0, 4, 0, 1)
        run    = st.toggle("Start camera", value=False)
        st.markdown("---")
        st.markdown(f"**Model:** `{ONNX_MODEL.name}`")
        st.markdown(f"**Exists:** {'Yes' if ONNX_MODEL.exists() else 'NOT FOUND'}")

    st.markdown('<div class="detection-title">YOLOv8s Detector</div>', unsafe_allow_html=True)
    st.caption("Real-time object detection -- ONNX Runtime -- Raspberry Pi")

    with st.spinner("Loading ONNX model..."):
        session = load_model()
    class_names = get_class_names(session)

    frame_col, stats_col = st.columns([3, 1])
    with frame_col:
        frame_ph = st.empty()
    with stats_col:
        st.markdown("### Detections")
        stats_ph = st.empty()
        st.markdown("---")
        st.markdown("### Classes")
        for i, name in enumerate(class_names[:20]):
            r, g, b = get_colour(i)
            hex_c = f"#{r:02x}{g:02x}{b:02x}"
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
                f'<div style="width:12px;height:12px;border-radius:3px;background:{hex_c}"></div>'
                f'<span style="font-size:0.8rem">{name}</span></div>',
                unsafe_allow_html=True,
            )

    if not run:
        frame_ph.markdown(
            '<div style="background:rgba(255,255,255,0.05);border:2px dashed rgba(255,255,255,0.2);'
            'border-radius:16px;height:400px;display:flex;align-items:center;justify-content:center;'
            'font-size:1.2rem;color:rgba(255,255,255,0.4);">[CAM] Enable camera in sidebar to start</div>',
            unsafe_allow_html=True,
        )
        return

    cap = cv2.VideoCapture(int(cam_id))
    if not cap.isOpened():
        st.error(f"Could not open camera {cam_id}.")
        return

    stop_btn = st.button("Stop camera")
    try:
        while not stop_btn:
            ret, frame = cap.read()
            if not ret:
                st.warning("Camera read failed.")
                break
            annotated, counts = run_inference(frame.copy(), session, conf, class_names)
            rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
            frame_ph.image(rgb, channels="RGB", use_container_width=True)
            if counts:
                md = "".join(
                    f'<div class="metric-card"><b>{cls}</b> &nbsp;--&nbsp; {cnt}</div>\n'
                    for cls, cnt in sorted(counts.items(), key=lambda x: -x[1])
                )
                stats_ph.markdown(md, unsafe_allow_html=True)
            else:
                stats_ph.markdown(
                    '<div class="metric-card" style="color:rgba(255,255,255,0.5);">No detections</div>',
                    unsafe_allow_html=True,
                )
    finally:
        cap.release()


if __name__ == "__main__":
    main()
