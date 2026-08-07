#!/usr/bin/env python3.12
"""
frontier_detector.py  —  Stage 4B: Wavefront Frontier Detection
────────────────────────────────────────────────────────────────
Subscribes to /rtabmap/map (nav_msgs/OccupancyGrid) and detects frontier
regions: boundaries between known-free space and unknown space.

Algorithm: Wavefront Frontier Detection (WFD)
  1. For every free cell (value == 0), check 4-connected neighbours.
  2. If any neighbour is unknown (value == -1), mark as frontier cell.
  3. BFS-cluster nearby frontier cells (within cluster_radius).
  4. Discard clusters smaller than min_frontier_size.
  5. Compute centroid in world coordinates for each surviving cluster.
  6. Publish results.

Publications:
  /frontiers/markers   (visualization_msgs/MarkerArray)  — green spheres for RViz
  /frontiers/centroids (geometry_msgs/PoseArray)         — used by exploration_manager

Parameters (from exploration_params.yaml):
  map_topic           — source occupancy grid topic
  publish_rate        — Hz, detection frequency
  cluster_radius      — m, BFS cluster merge radius
  min_frontier_size   — cells, minimum cluster size threshold
"""

import math
from collections import deque
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy

from geometry_msgs.msg import Pose, PoseArray, Point
from nav_msgs.msg import OccupancyGrid
from std_msgs.msg import Header
from visualization_msgs.msg import Marker, MarkerArray


# ─────────────────────────────────────────────────────────────────────────────
#  Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Frontier:
    """One clustered frontier region in the occupancy grid."""
    id: int
    centroid_x: float           # world frame, metres
    centroid_y: float           # world frame, metres
    size: int                   # number of frontier cells in this cluster
    cells: List[Tuple[int, int]] = field(default_factory=list)  # (row, col)


# ─────────────────────────────────────────────────────────────────────────────
#  Frontier Detector Node
# ─────────────────────────────────────────────────────────────────────────────

class FrontierDetector(Node):

    def __init__(self):
        super().__init__('frontier_detector')

        # ── Parameters ────────────────────────────────────────────────────────
        self.declare_parameter('map_topic',        '/rtabmap/map')
        self.declare_parameter('publish_rate',     2.0)
        self.declare_parameter('cluster_radius',   0.50)
        self.declare_parameter('min_frontier_size', 5)

        self._map_topic        = self.get_parameter('map_topic').value
        self._publish_rate     = self.get_parameter('publish_rate').value
        self._cluster_radius   = self.get_parameter('cluster_radius').value
        self._min_size         = self.get_parameter('min_frontier_size').value

        # ── State ─────────────────────────────────────────────────────────────
        self._latest_map: OccupancyGrid | None = None
        self._frontiers:  List[Frontier] = []

        # ── Map subscription (transient_local to catch the last published map) ─
        map_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
            depth=1,
        )
        self.create_subscription(
            OccupancyGrid,
            self._map_topic,
            self._map_callback,
            map_qos,
        )

        # ── Publishers ────────────────────────────────────────────────────────
        self._marker_pub = self.create_publisher(
            MarkerArray, '/frontiers/markers', 10)
        self._centroid_pub = self.create_publisher(
            PoseArray, '/frontiers/centroids', 10)

        # ── Detection timer ───────────────────────────────────────────────────
        self.create_timer(1.0 / self._publish_rate, self._detect_and_publish)

        self.get_logger().info(
            f'FrontierDetector started | rate={self._publish_rate:.1f} Hz | '
            f'min_size={self._min_size} cells | cluster_r={self._cluster_radius:.2f} m'
        )

    # ── Map callback ──────────────────────────────────────────────────────────

    def _map_callback(self, msg: OccupancyGrid) -> None:
        self._latest_map = msg

    # ── Main detection timer ──────────────────────────────────────────────────

    def _detect_and_publish(self) -> None:
        if self._latest_map is None:
            return

        grid = self._latest_map
        frontiers = self._extract_frontiers(grid)
        self._frontiers = frontiers

        header = Header(
            stamp=self.get_clock().now().to_msg(),
            frame_id='map',
        )
        self._publish_markers(frontiers, header)
        self._publish_centroids(frontiers, header)

        self.get_logger().debug(
            f'Detected {len(frontiers)} frontier clusters'
        )

    # ── Frontier extraction ────────────────────────────────────────────────────

    def _extract_frontiers(self, grid: OccupancyGrid) -> List[Frontier]:
        """Full WFD pipeline: find cells → cluster → filter → convert."""
        width  = grid.info.width
        height = grid.info.height
        data   = np.array(grid.data, dtype=np.int8)

        # Step 1: find all frontier cells (free adjacent to unknown)
        frontier_set = self._find_frontier_cells(data, width, height)
        if not frontier_set:
            return []

        # Step 2: BFS cluster
        clusters = self._bfs_cluster(frontier_set, grid.info.resolution)

        # Step 3: filter small clusters and convert to world coordinates
        frontiers: List[Frontier] = []
        for idx, cells in enumerate(clusters):
            if len(cells) < self._min_size:
                continue
            cx, cy = self._cells_to_world(cells, grid.info)
            frontiers.append(Frontier(
                id=idx,
                centroid_x=cx,
                centroid_y=cy,
                size=len(cells),
                cells=cells,
            ))

        return frontiers

    def _find_frontier_cells(
        self, data: np.ndarray, width: int, height: int
    ) -> set:
        """Return set of (row, col) that are free with at least one unknown neighbour."""
        frontier_cells: set = set()
        # 4-connected neighbour offsets
        neighbours = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        for row in range(1, height - 1):
            for col in range(1, width - 1):
                idx = row * width + col
                if data[idx] != 0:          # not free
                    continue
                for dr, dc in neighbours:
                    nidx = (row + dr) * width + (col + dc)
                    if data[nidx] == -1:    # unknown neighbour
                        frontier_cells.add((row, col))
                        break

        return frontier_cells

    def _bfs_cluster(
        self, frontier_cells: set, resolution: float
    ) -> List[List[Tuple[int, int]]]:
        """Group frontier cells into clusters using BFS within cluster_radius."""
        radius_cells = max(1, int(self._cluster_radius / resolution))
        clusters: List[List[Tuple[int, int]]] = []
        unvisited = set(frontier_cells)

        while unvisited:
            seed = next(iter(unvisited))
            cluster: List[Tuple[int, int]] = []
            queue = deque([seed])
            unvisited.discard(seed)

            while queue:
                cell = queue.popleft()
                cluster.append(cell)
                row, col = cell
                # Check grid neighbourhood within radius_cells
                for dr in range(-radius_cells, radius_cells + 1):
                    for dc in range(-radius_cells, radius_cells + 1):
                        neighbour = (row + dr, col + dc)
                        if neighbour in unvisited:
                            unvisited.discard(neighbour)
                            queue.append(neighbour)

            clusters.append(cluster)

        return clusters

    def _cells_to_world(
        self,
        cells: List[Tuple[int, int]],
        info,
    ) -> Tuple[float, float]:
        """Convert grid cell list centroid to world coordinates."""
        res = info.resolution
        ox  = info.origin.position.x
        oy  = info.origin.position.y
        avg_col = sum(c[1] for c in cells) / len(cells)
        avg_row = sum(c[0] for c in cells) / len(cells)
        cx = ox + (avg_col + 0.5) * res
        cy = oy + (avg_row + 0.5) * res
        return cx, cy

    # ── Publishers ─────────────────────────────────────────────────────────────

    def _publish_markers(
        self, frontiers: List[Frontier], header: Header
    ) -> None:
        """Publish green sphere markers for all frontier centroids."""
        markers = MarkerArray()

        # Clear old markers first
        delete_all = Marker()
        delete_all.header = header
        delete_all.action = Marker.DELETEALL
        markers.markers.append(delete_all)

        for f in frontiers:
            m = Marker()
            m.header       = header
            m.ns           = 'frontiers'
            m.id           = f.id
            m.type         = Marker.SPHERE
            m.action       = Marker.ADD
            m.pose.position.x = f.centroid_x
            m.pose.position.y = f.centroid_y
            m.pose.position.z = 0.15
            m.pose.orientation.w = 1.0
            # Scale proportional to cluster size, capped for visibility
            scale = min(0.15 + 0.01 * f.size, 0.40)
            m.scale.x = m.scale.y = m.scale.z = scale
            m.color.r = 0.0
            m.color.g = 1.0   # green = candidate frontier
            m.color.b = 0.0
            m.color.a = 0.85
            m.lifetime.sec = 1  # auto-expire if not refreshed
            markers.markers.append(m)

        self._marker_pub.publish(markers)

    def _publish_centroids(
        self, frontiers: List[Frontier], header: Header
    ) -> None:
        """Publish frontier centroids as PoseArray for exploration_manager."""
        pa = PoseArray(header=header)
        for f in frontiers:
            p = Pose()
            p.position.x = f.centroid_x
            p.position.y = f.centroid_y
            p.position.z = float(f.size)   # encode size in z for selector
            p.orientation.w = 1.0
            pa.poses.append(p)
        self._centroid_pub.publish(pa)

    # ── Public accessor (for other nodes in same process if needed) ───────────

    @property
    def frontiers(self) -> List[Frontier]:
        return self._frontiers


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = FrontierDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
