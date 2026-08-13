"""
tests/unit/exploration/test_frontier_detector.py
──────────────────────────────────────────────────
Unit tests for the WFD (Wavefront Frontier Detection) algorithm
in frontier_detector.py.

All tests are pure logic — no ROS 2 installation needed.
Tests operate directly on FrontierDetector's private methods.

Coverage:
  - _find_frontier_cells: basic 3×3 grid with one free-unknown boundary
  - _find_frontier_cells: fully occupied grid → no frontiers
  - _find_frontier_cells: fully unknown grid → no frontiers (no free cells)
  - _find_frontier_cells: fully free grid → no frontiers (no unknown neighbours)
  - _find_frontier_cells: border cells are skipped (edges not checked)
  - _bfs_cluster: single cluster from connected frontier cells
  - _bfs_cluster: two disconnected clusters remain separate
  - _bfs_cluster: minimum size filter removes small clusters
  - _cells_to_world: correct coordinate transform with origin and resolution
  - _extract_frontiers: end-to-end with known grid → expected centroid
  - _extract_frontiers: empty grid → empty list (no crash)
  - _extract_frontiers: all-occupied → empty list
  - _extract_frontiers: all-unknown → empty list
"""

import sys
import math
import numpy as np
import pytest
import types
import os

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def inject_ros_stubs():
    """Inject all ROS stubs so frontier_detector.py can be imported."""
    from tests.conftest import _mock_rclpy, _mock_ros_msgs, _mock_cv2
    rclpy_stub = _mock_rclpy()
    cv2_stub   = _mock_cv2()
    gm, nm, sm, sens, diag, vis, nav2 = _mock_ros_msgs()

    mods = {
        "rclpy":              rclpy_stub,
        "rclpy.node":         rclpy_stub.node,
        "rclpy.qos":          rclpy_stub.qos,
        "cv2":                cv2_stub,
        "geometry_msgs":      gm,
        "geometry_msgs.msg":  gm.msg,
        "nav_msgs":           nm,
        "nav_msgs.msg":       nm.msg,
        "std_msgs":           sm,
        "std_msgs.msg":       sm.msg,
        "visualization_msgs": vis,
        "visualization_msgs.msg": vis.msg,
    }
    old = {}
    for k, v in mods.items():
        old[k] = sys.modules.get(k)
        sys.modules[k] = v
    yield
    for k, v in old.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def _get_detector():
    """Import FrontierDetector and create an instance bypassing __init__."""
    src = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "Simulation", "vacuum_ws", "src",
            "vacuum_exploration", "vacuum_exploration"
        )
    )
    if src not in sys.path:
        sys.path.insert(0, src)
    if "frontier_detector" in sys.modules:
        del sys.modules["frontier_detector"]
    import frontier_detector as fd_mod

    # Create instance without calling __init__ (avoids ROS node setup)
    node = fd_mod.FrontierDetector.__new__(fd_mod.FrontierDetector)
    node._cluster_radius = 0.5
    node._min_size       = 2

    # Minimal logger stub
    class _Logger:
        def debug(self, *a): pass
        def info(self, *a): pass
    node._logger = _Logger()
    node.get_logger = lambda: node._logger

    return node, fd_mod


def _make_grid(width, height, data, resolution=0.05, ox=0.0, oy=0.0):
    """
    Build a synthetic OccupancyGrid-like object.
    data: list of int8 values (0=free, -1=unknown, 100=occupied)
    """
    class _Info:
        def __init__(self):
            self.width = width
            self.height = height
            self.resolution = resolution
            class _Origin:
                class _Pos: pass
                position = _Pos()
            self.origin = _Origin()
            self.origin.position.x = ox
            self.origin.position.y = oy

    class _Grid:
        def __init__(self):
            self.info = _Info()
            self.data = data

    return _Grid()


# ─────────────────────────────────────────────────────────────────────────────
# _find_frontier_cells tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFindFrontierCells:

    def test_basic_free_adjacent_to_unknown_is_frontier(self):
        """
        3×3 grid:
          [ -1, -1, -1 ]
          [ -1,  0, -1 ]
          [ -1, -1, -1 ]
        Center cell (1,1) is free with all unknown neighbours → frontier.
        """
        node, fd = _get_detector()
        data = np.array([-1, -1, -1, -1, 0, -1, -1, -1, -1], dtype=np.int8)
        result = node._find_frontier_cells(data, width=3, height=3)
        assert (1, 1) in result, "Center free cell bordered by unknowns must be a frontier"

    def test_fully_occupied_returns_empty(self):
        node, fd = _get_detector()
        data = np.full(25, 100, dtype=np.int8)
        result = node._find_frontier_cells(data, width=5, height=5)
        assert len(result) == 0

    def test_fully_unknown_returns_empty(self):
        node, fd = _get_detector()
        data = np.full(25, -1, dtype=np.int8)
        result = node._find_frontier_cells(data, width=5, height=5)
        assert len(result) == 0, "No free cells → no frontiers possible"

    def test_fully_free_returns_empty(self):
        """No unknown neighbours → no frontiers."""
        node, fd = _get_detector()
        data = np.zeros(25, dtype=np.int8)
        result = node._find_frontier_cells(data, width=5, height=5)
        assert len(result) == 0, "Fully free grid has no unknown neighbours"

    def test_border_cells_excluded(self):
        """
        Row 0 and row N-1 are borders and should never be frontier cells
        (the algorithm loops from range(1, height-1)).
        """
        node, fd = _get_detector()
        # 5×5: border free, interior unknown
        data = np.full(25, -1, dtype=np.int8)
        for col in range(5):
            data[col] = 0           # row 0 free
            data[20 + col] = 0      # row 4 free
        result = node._find_frontier_cells(data, width=5, height=5)
        # No interior free cells → no frontier
        assert all(r != 0 and r != 4 for r, c in result), "Border-row cells must not be frontiers"

    def test_multiple_frontier_cells_detected(self):
        """
        10×10 grid: left half free (0), right half unknown (-1).
        Column 4 (free) adjacent to column 5 (unknown) → all rows 1-8 at col 4 are frontiers.
        """
        node, fd = _get_detector()
        data = np.zeros(100, dtype=np.int8)
        for row in range(10):
            for col in range(5, 10):
                data[row * 10 + col] = -1
        result = node._find_frontier_cells(data, width=10, height=10)
        assert len(result) >= 6, f"Expected ≥6 frontier cells on boundary, got {len(result)}"
        for row, col in result:
            assert col == 4, f"All frontier cells should be in column 4, found col={col}"


# ─────────────────────────────────────────────────────────────────────────────
# _bfs_cluster tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBfsCluster:

    def test_single_connected_cluster(self):
        node, fd = _get_detector()
        node._cluster_radius = 0.5
        cells = {(5, 4), (5, 5), (6, 4), (6, 5)}
        clusters = node._bfs_cluster(cells, resolution=0.05)
        assert len(clusters) == 1, "Connected cells must form one cluster"
        assert sum(len(c) for c in clusters) == 4

    def test_two_disconnected_clusters(self):
        node, fd = _get_detector()
        node._cluster_radius = 0.05  # tiny radius so far-apart cells stay separate
        # Two groups far apart
        cells = {(1, 1), (1, 2), (50, 50), (50, 51)}
        clusters = node._bfs_cluster(cells, resolution=0.05)
        assert len(clusters) == 2, f"Should get 2 clusters, got {len(clusters)}"

    def test_single_cell_cluster(self):
        node, fd = _get_detector()
        node._cluster_radius = 0.05
        cells = {(5, 5)}
        clusters = node._bfs_cluster(cells, resolution=0.05)
        assert len(clusters) == 1
        assert clusters[0] == [(5, 5)]

    def test_all_cells_visited(self):
        """Total cells across all clusters must equal input count."""
        node, fd = _get_detector()
        node._cluster_radius = 0.5
        cells = {(i, j) for i in range(3) for j in range(3)}
        clusters = node._bfs_cluster(cells, resolution=0.05)
        total = sum(len(c) for c in clusters)
        assert total == len(cells)


# ─────────────────────────────────────────────────────────────────────────────
# _cells_to_world tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCellsToWorld:

    def test_origin_zero_single_cell(self):
        node, fd = _get_detector()
        grid = _make_grid(10, 10, list(range(100)), resolution=0.1, ox=0.0, oy=0.0)
        cx, cy = node._cells_to_world([(2, 3)], grid.info)
        # avg_col=3, avg_row=2 → cx = 0 + (3+0.5)*0.1 = 0.35; cy = (2+0.5)*0.1 = 0.25
        assert cx == pytest.approx(0.35, abs=1e-4)
        assert cy == pytest.approx(0.25, abs=1e-4)

    def test_nonzero_origin(self):
        node, fd = _get_detector()
        grid = _make_grid(10, 10, list(range(100)), resolution=0.05, ox=1.0, oy=2.0)
        cx, cy = node._cells_to_world([(0, 0)], grid.info)
        # cx = 1.0 + 0.5*0.05 = 1.025; cy = 2.0 + 0.5*0.05 = 2.025
        assert cx == pytest.approx(1.025, abs=1e-4)
        assert cy == pytest.approx(2.025, abs=1e-4)

    def test_centroid_of_two_cells(self):
        node, fd = _get_detector()
        grid = _make_grid(10, 10, list(range(100)), resolution=0.1, ox=0.0, oy=0.0)
        # avg_col = (2+4)/2 = 3; avg_row = (1+3)/2 = 2
        cx, cy = node._cells_to_world([(1, 2), (3, 4)], grid.info)
        assert cx == pytest.approx((3 + 0.5) * 0.1, abs=1e-4)
        assert cy == pytest.approx((2 + 0.5) * 0.1, abs=1e-4)


# ─────────────────────────────────────────────────────────────────────────────
# _extract_frontiers end-to-end tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractFrontiers:

    def test_known_grid_returns_frontiers(self):
        """Left-half free, right-half unknown → one or more frontier clusters."""
        node, fd = _get_detector()
        node._min_size = 2
        data = np.zeros(100, dtype=np.int8)
        for row in range(10):
            for col in range(5, 10):
                data[row * 10 + col] = -1
        grid = _make_grid(10, 10, data.tolist(), resolution=0.05)
        frontiers = node._extract_frontiers(grid)
        assert len(frontiers) >= 1, "Known half-free, half-unknown grid must produce frontiers"

    def test_empty_data_returns_empty_list(self):
        node, fd = _get_detector()
        grid = _make_grid(0, 0, [], resolution=0.05)
        frontiers = node._extract_frontiers(grid)
        assert frontiers == []

    def test_all_occupied_returns_empty_list(self):
        node, fd = _get_detector()
        data = [100] * 100
        grid = _make_grid(10, 10, data, resolution=0.05)
        frontiers = node._extract_frontiers(grid)
        assert frontiers == []

    def test_all_unknown_returns_empty_list(self):
        node, fd = _get_detector()
        data = [-1] * 100
        grid = _make_grid(10, 10, data, resolution=0.05)
        frontiers = node._extract_frontiers(grid)
        assert frontiers == []

    def test_min_size_filter_removes_small_clusters(self):
        """Single isolated frontier cell should be removed if min_size > 1."""
        node, fd = _get_detector()
        node._min_size = 5  # high threshold
        # Only one frontier cell exists
        data = np.full(25, -1, dtype=np.int8)
        data[12] = 0  # center cell free, surrounded by unknown
        grid = _make_grid(5, 5, data.tolist(), resolution=0.05)
        frontiers = node._extract_frontiers(grid)
        assert frontiers == [], "Single-cell frontier must be removed by min_size filter"

    def test_frontier_has_valid_centroid_coordinates(self):
        node, fd = _get_detector()
        node._min_size = 1
        data = np.zeros(100, dtype=np.int8)
        for row in range(10):
            for col in range(5, 10):
                data[row * 10 + col] = -1
        grid = _make_grid(10, 10, data.tolist(), resolution=0.05, ox=0.0, oy=0.0)
        frontiers = node._extract_frontiers(grid)
        for f in frontiers:
            assert math.isfinite(f.centroid_x), "centroid_x must be finite"
            assert math.isfinite(f.centroid_y), "centroid_y must be finite"
            assert f.size > 0, "Frontier size must be positive"

    def test_frontier_ids_are_unique(self):
        node, fd = _get_detector()
        node._min_size = 1
        # Two disconnected frontier regions
        data = np.full(100, -1, dtype=np.int8)
        # Region 1: row 2, cols 1-2 free
        data[2*10+1] = 0; data[2*10+2] = 0
        # Region 2: row 7, cols 7-8 free
        data[7*10+7] = 0; data[7*10+8] = 0
        grid = _make_grid(10, 10, data.tolist(), resolution=0.05)
        frontiers = node._extract_frontiers(grid)
        ids = [f.id for f in frontiers]
        assert len(ids) == len(set(ids)), "Frontier IDs must be unique"
