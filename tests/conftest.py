"""
conftest.py — Shared fixtures and mocking infrastructure for the entire
Swachh Boudhik Yantra test suite.

All fixtures here are available to every test file without import.
"""

import sys
import types
import pytest
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
#  Mock heavy optional dependencies so unit tests run without them installed
# ─────────────────────────────────────────────────────────────────────────────

def _mock_cv2():
    """Provide a minimal cv2 stub so vision tests run without OpenCV."""
    cv2 = types.ModuleType("cv2")
    cv2.COLOR_BGR2GRAY  = 6
    cv2.COLOR_BGR2RGB   = 4
    cv2.INTER_LINEAR    = 1
    cv2.BORDER_CONSTANT = 0
    cv2.CAP_V4L2        = 200
    cv2.CAP_PROP_FRAME_WIDTH  = 3
    cv2.CAP_PROP_FRAME_HEIGHT = 4
    cv2.CAP_PROP_BUFFERSIZE   = 38
    cv2.CAP_PROP_FOURCC       = 6

    def cvtColor(img, code):
        if img.ndim == 3 and code == cv2.COLOR_BGR2GRAY:
            return img[:, :, 0]
        if img.ndim == 2:
            return np.stack([img, img, img], axis=-1)
        return img

    def resize(img, dsize, interpolation=None):
        return np.zeros((*dsize[::-1], img.shape[2]) if img.ndim == 3 else dsize[::-1], dtype=img.dtype)

    def copyMakeBorder(img, top, bottom, left, right, borderType, value=None):
        if img.ndim == 3:
            h, w, c = img.shape
            out = np.full((h + top + bottom, w + left + right, c),
                          fill_value=114, dtype=np.uint8)
        else:
            h, w = img.shape
            out = np.zeros((h + top + bottom, w + left + right), dtype=img.dtype)
        out[top:top+h, left:left+w] = img
        return out

    # cv2.dnn stub
    dnn = types.ModuleType("cv2.dnn")
    def NMSBoxes(boxes, scores, score_thr, nms_thr):
        """Simple greedy NMS stub returning indices sorted by score.
        boxes: list of [x1,y1,x2,y2] (xyxy format from detector._nms)
        """
        if not boxes or len(boxes) == 0:
            return []
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        kept = []
        suppressed = set()
        for i in order:
            if i in suppressed:
                continue
            kept.append(i)
            b1 = boxes[i]  # [x1,y1,x2,y2]
            for j in order:
                if j == i or j in suppressed:
                    continue
                b2 = boxes[j]
                # compute intersection in xyxy space
                ix1 = max(b1[0], b2[0]); iy1 = max(b1[1], b2[1])
                ix2 = min(b1[2], b2[2]); iy2 = min(b1[3], b2[3])
                inter_w = max(0.0, ix2 - ix1)
                inter_h = max(0.0, iy2 - iy1)
                inter   = inter_w * inter_h
                a1 = max(0.0, b1[2]-b1[0]) * max(0.0, b1[3]-b1[1])
                a2 = max(0.0, b2[2]-b2[0]) * max(0.0, b2[3]-b2[1])
                union = a1 + a2 - inter
                iou = inter / union if union > 1e-9 else 0.0
                if iou > nms_thr:
                    suppressed.add(j)
        return np.array(kept, dtype=np.int32) if kept else []

    dnn.NMSBoxes = NMSBoxes
    cv2.dnn = dnn

    cv2.cvtColor        = cvtColor
    cv2.resize          = resize
    cv2.copyMakeBorder  = copyMakeBorder

    def VideoWriter_fourcc(*args): return 0
    cv2.VideoWriter_fourcc = VideoWriter_fourcc

    return cv2


def _mock_rclpy():
    """Minimal rclpy stub for pure-logic node tests."""
    rclpy_mod = types.ModuleType("rclpy")

    class _Node:
        def __init__(self, name):
            self._name = name
            self._params = {}
            self._clock = _Clock()
        def declare_parameter(self, name, default):
            self._params[name] = default
        def get_parameter(self, name):
            class _Param:
                def __init__(self, val): self.value = val
            return _Param(self._params.get(name))
        def get_logger(self):
            class _Logger:
                def info(self, *a): pass
                def warn(self, *a): pass
                def warning(self, *a): pass
                def error(self, *a): pass
                def debug(self, *a): pass
            return _Logger()
        def get_clock(self): return self._clock
        def create_subscription(self, *a, **kw): return None
        def create_publisher(self, *a, **kw): return _Publisher()
        def create_timer(self, *a, **kw): return None
        def destroy_node(self): pass

    class _Clock:
        def now(self):
            class _T:
                def to_msg(self):
                    class _Stamp:
                        sec = 1; nanosec = 0
                    return _Stamp()
            return _T()

    class _Publisher:
        def __init__(self): self.published = []
        def publish(self, msg): self.published.append(msg)

    rclpy_mod.node = types.ModuleType("rclpy.node")
    rclpy_mod.node.Node = _Node
    rclpy_mod.init  = lambda *a, **kw: None
    rclpy_mod.ok    = lambda: True
    rclpy_mod.spin  = lambda *a, **kw: None
    rclpy_mod.shutdown = lambda: None

    # rclpy.qos stub
    qos = types.ModuleType("rclpy.qos")
    class _QoS:
        def __init__(self, **kw): pass
    qos.QoSProfile = _QoS
    qos.QoSReliabilityPolicy = type("QRP", (), {"RELIABLE": 1, "BEST_EFFORT": 2})()
    qos.QoSDurabilityPolicy  = type("QDP", (), {"VOLATILE": 1, "TRANSIENT_LOCAL": 2})()
    qos.ReliabilityPolicy    = qos.QoSReliabilityPolicy
    qos.DurabilityPolicy     = qos.QoSDurabilityPolicy
    rclpy_mod.qos = qos

    return rclpy_mod


def _mock_ros_msgs():
    """Stub for geometry_msgs, nav_msgs, std_msgs, sensor_msgs."""
    class _Twist:
        class _Vec:
            x = 0.0; y = 0.0; z = 0.0
        linear = _Vec(); angular = _Vec()

    class _TwistStamped:
        class _Header:
            stamp = None; frame_id = ""
        header = _Header()
        twist  = None

    class _Odometry:
        class _Header:
            stamp = None; frame_id = ""
        class _Pose:
            class _Pose2:
                class _Position:
                    x = 0.0; y = 0.0; z = 0.0
                class _Orientation:
                    x = 0.0; y = 0.0; z = 0.0; w = 1.0
                position = _Position(); orientation = _Orientation()
            pose = _Pose2()
            covariance = [0.0] * 36
        class _Twist2:
            class _Twist3:
                class _Vec:
                    x = 0.0; y = 0.0; z = 0.0
                linear = _Vec(); angular = _Vec()
            twist = _Twist3()
        header = _Header()
        child_frame_id = ""
        pose  = _Pose()
        twist = _Twist2()

    class _String:
        def __init__(self, data=""): self.data = data

    class _OccupancyGrid:
        class _Info:
            width = 0; height = 0; resolution = 0.05
            class _Origin:
                class _Position:
                    x = 0.0; y = 0.0; z = 0.0
                position = _Position()
            origin = _Origin()
        info = _Info()
        data = []

    # geometry_msgs
    gm = types.ModuleType("geometry_msgs")
    gm_msg = types.ModuleType("geometry_msgs.msg")
    gm_msg.Twist        = _Twist
    gm_msg.TwistStamped = _TwistStamped
    gm_msg.Pose         = type("Pose", (), {"position": type("P", (), {"x":0.0,"y":0.0,"z":0.0})(), "orientation": type("O", (), {"x":0.0,"y":0.0,"z":0.0,"w":1.0})()})
    gm_msg.PoseArray    = type("PoseArray", (), {"header": None, "poses": []})
    gm_msg.Point        = type("Point", (), {"x":0.0,"y":0.0,"z":0.0})
    gm_msg.Quaternion   = type("Quaternion", (), {"x":0.0,"y":0.0,"z":0.0,"w":1.0})
    gm.msg = gm_msg

    # nav_msgs
    nm = types.ModuleType("nav_msgs")
    nm_msg = types.ModuleType("nav_msgs.msg")
    nm_msg.Odometry      = _Odometry
    nm_msg.OccupancyGrid = _OccupancyGrid
    nm.msg = nm_msg

    # std_msgs
    sm = types.ModuleType("std_msgs")
    sm_msg = types.ModuleType("std_msgs.msg")
    sm_msg.String = _String
    sm_msg.Header = type("Header", (), {"stamp": None, "frame_id": ""})
    sm.msg = sm_msg

    # sensor_msgs
    sens = types.ModuleType("sensor_msgs")
    sens_msg = types.ModuleType("sensor_msgs.msg")
    sens_msg.JointState = type("JointState", (), {})
    sens.msg = sens_msg

    # diagnostic_msgs
    diag = types.ModuleType("diagnostic_msgs")
    diag_msg = types.ModuleType("diagnostic_msgs.msg")
    diag_msg.DiagnosticArray  = type("DiagnosticArray", (), {})
    diag_msg.DiagnosticStatus = type("DiagnosticStatus", (), {"OK":0,"WARN":1,"ERROR":2,"STALE":3})
    diag_msg.KeyValue         = type("KeyValue", (), {"key":"","value":""})
    diag.msg = diag_msg

    # visualization_msgs
    vis = types.ModuleType("visualization_msgs")
    vis_msg = types.ModuleType("visualization_msgs.msg")
    vis_msg.Marker      = type("Marker", (), {"SPHERE":2,"ADD":0,"DELETEALL":3,"header":None,"ns":"","id":0,"type":0,"action":0,"pose":None,"scale":None,"color":None,"lifetime":None})
    vis_msg.MarkerArray = type("MarkerArray", (), {"markers": []})
    vis.msg = vis_msg

    # nav2_msgs
    nav2 = types.ModuleType("nav2_msgs")
    nav2_msg = types.ModuleType("nav2_msgs.msg")
    nav2_msg.ParticleCloud = type("ParticleCloud", (), {"particles": []})
    nav2.msg = nav2_msg

    return gm, nm, sm, sens, diag, vis, nav2


@pytest.fixture(autouse=False)
def mock_ros_env():
    """
    Inject minimal ROS 2 mocks into sys.modules so any test that imports
    a ROS node can do so without a running ROS 2 installation.

    Usage:
        def test_something(mock_ros_env):
            from vacuum_controller.vacuum_controller.cmd_vel_relay import CmdVelRelay
            ...
    """
    rclpy_stub = _mock_rclpy()
    cv2_stub   = _mock_cv2()
    gm, nm, sm, sens, diag, vis, nav2 = _mock_ros_msgs()

    mods = {
        "rclpy":            rclpy_stub,
        "rclpy.node":       rclpy_stub.node,
        "rclpy.qos":        rclpy_stub.qos,
        "cv2":              cv2_stub,
        "geometry_msgs":    gm,
        "geometry_msgs.msg": gm.msg,
        "nav_msgs":         nm,
        "nav_msgs.msg":     nm.msg,
        "std_msgs":         sm,
        "std_msgs.msg":     sm.msg,
        "sensor_msgs":      sens,
        "sensor_msgs.msg":  sens.msg,
        "diagnostic_msgs":  diag,
        "diagnostic_msgs.msg": diag.msg,
        "visualization_msgs": vis,
        "visualization_msgs.msg": vis.msg,
        "nav2_msgs":        nav2,
        "nav2_msgs.msg":    nav2.msg,
        "onnxruntime":      types.ModuleType("onnxruntime"),
    }

    # Inject
    old = {}
    for k, v in mods.items():
        old[k] = sys.modules.get(k)
        sys.modules[k] = v

    yield rclpy_stub, cv2_stub

    # Restore
    for k, v in old.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


@pytest.fixture
def make_flat_cov():
    """Factory: create a 36-element flat covariance vector with given xx, yy, zz_rot."""
    def _make(xx=0.0, yy=0.0, zz_rot=0.0):
        cov = [0.0] * 36
        cov[0]  = xx       # x-x
        cov[7]  = yy       # y-y
        cov[35] = zz_rot   # yaw-yaw
        return cov
    return _make


@pytest.fixture
def make_occupancy_grid():
    """Factory: build a synthetic OccupancyGrid-like object for WFD tests."""
    class _Info:
        def __init__(self, w, h, res, ox=0.0, oy=0.0):
            self.width = w; self.height = h; self.resolution = res
            class _O:
                class _P:
                    x = ox; y = oy
                position = _P()
            self.origin = _O()

    class _Grid:
        def __init__(self, w, h, data, res=0.05, ox=0.0, oy=0.0):
            self.info = _Info(w, h, res, ox, oy)
            self.data = data

    return _Grid
