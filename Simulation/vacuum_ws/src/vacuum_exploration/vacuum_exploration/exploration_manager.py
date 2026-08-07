#!/usr/bin/env python3.12
"""
exploration_manager.py  —  Stage 4B: Autonomous Exploration Orchestrator
─────────────────────────────────────────────────────────────────────────
The Exploration Manager owns the exploration lifecycle.

FSM States:
  IDLE              → Initial state. Transitions immediately to WAITING_FOR_MAP.
  WAITING_FOR_MAP   → Waits for RTAB-Map to publish a map with free cells.
  DETECT_FRONTIERS  → Checks the latest frontier list from FrontierDetector.
  SELECT_GOAL       → Uses GoalSelector to pick the best non-blacklisted frontier.
  SEND_GOAL         → Sends NavigateToPose action goal to Nav2.
  NAVIGATING        → Waits for Nav2 result. Monitors timeout + oscillation.
  GOAL_REACHED      → Records success, resets counters, loops back.
  RECOVERING        → Records failure, blacklists frontier, loops back.
  FINISHED          → All completion conditions satisfied. Exploration done.

Recovery logic:
  - Goal timeout         → cancel goal → blacklist frontier → RECOVERING
  - Nav2 ABORTED         → blacklist frontier → RECOVERING
  - Oscillation detected → cancel goal → blacklist frontier → RECOVERING
  - 3 consecutive failures → tighten min_frontier_size threshold temporarily

Completion conditions (ALL must be true):
  1. No frontiers for N consecutive detection cycles
  2. Map has not grown (free cells) by > threshold in last patience_sec
  3. Robot is stationary (velocity < threshold)

Blacklist persistence:
  Failed frontiers are stored with expiry timestamp.
  After blacklist_expiry_sec, the frontier is eligible again.

Publications:
  /exploration/status  (std_msgs/String — JSON)  — FSM state + metrics
"""

import json
import math
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, List, Optional, Set

import numpy as np
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseArray, PoseStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from nav2_msgs.action import NavigateToPose
from std_msgs.msg import String
from visualization_msgs.msg import Marker, MarkerArray

from vacuum_exploration.frontier_detector import Frontier
from vacuum_exploration.goal_selector import GoalSelector


# ─────────────────────────────────────────────────────────────────────────────
#  FSM State Enum
# ─────────────────────────────────────────────────────────────────────────────

class ExplorationState(Enum):
    IDLE              = 'IDLE'
    WAITING_FOR_MAP   = 'WAITING_FOR_MAP'
    DETECT_FRONTIERS  = 'DETECT_FRONTIERS'
    SELECT_GOAL       = 'SELECT_GOAL'
    SEND_GOAL         = 'SEND_GOAL'
    NAVIGATING        = 'NAVIGATING'
    GOAL_REACHED      = 'GOAL_REACHED'
    RECOVERING        = 'RECOVERING'
    FINISHED          = 'FINISHED'


# ─────────────────────────────────────────────────────────────────────────────
#  Blacklisted Frontier Entry
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BlacklistEntry:
    """Record of a frontier that has been marked as temporarily unreachable."""
    frontier_id:       int
    centroid_x:        float
    centroid_y:        float
    failure_count:     int
    last_failure_time: float  # ROS time in seconds
    expiry_sec:        float = 60.0

    def is_expired(self, current_time: float) -> bool:
        return (current_time - self.last_failure_time) > self.expiry_sec


# ─────────────────────────────────────────────────────────────────────────────
#  Exploration Manager Node
# ─────────────────────────────────────────────────────────────────────────────

class ExplorationManager(Node):

    def __init__(self):
        super().__init__('exploration_manager')

        # ── Parameters ────────────────────────────────────────────────────────
        self.declare_parameter('goal_timeout',                   30.0)
        self.declare_parameter('retry_count',                    3)
        self.declare_parameter('blacklist_expiry_sec',           60.0)
        self.declare_parameter('no_frontier_consecutive_checks', 5)
        self.declare_parameter('map_growth_patience_sec',        15.0)
        self.declare_parameter('map_growth_threshold',           10)
        self.declare_parameter('stationary_vel_threshold',       0.02)
        self.declare_parameter('oscillation_distance',           0.30)
        self.declare_parameter('oscillation_timeout_sec',        15.0)
        # Goal selector weights
        self.declare_parameter('weight_info_gain',               1.0)
        self.declare_parameter('weight_distance',                1.5)
        self.declare_parameter('weight_obstacle_penalty',        0.8)
        self.declare_parameter('min_goal_distance',              0.30)

        p = lambda name: self.get_parameter(name).value
        self._goal_timeout             = p('goal_timeout')
        self._retry_count              = p('retry_count')
        self._blacklist_expiry         = p('blacklist_expiry_sec')
        self._no_frontier_checks_req   = p('no_frontier_consecutive_checks')
        self._map_growth_patience      = p('map_growth_patience_sec')
        self._map_growth_threshold     = p('map_growth_threshold')
        self._stationary_vel_thresh    = p('stationary_vel_threshold')
        self._oscillation_dist         = p('oscillation_distance')
        self._oscillation_timeout      = p('oscillation_timeout_sec')

        # ── Goal Selector ─────────────────────────────────────────────────────
        self._selector = GoalSelector(
            weight_info_gain=        p('weight_info_gain'),
            weight_distance=         p('weight_distance'),
            weight_obstacle_penalty= p('weight_obstacle_penalty'),
            min_goal_distance=       p('min_goal_distance'),
        )

        # ── FSM State ──────────────────────────────────────────────────────────
        self._state = ExplorationState.IDLE

        # ── Frontier data (from FrontierDetector) ─────────────────────────────
        self._frontiers:          List[Frontier] = []
        self._current_frontier:   Optional[Frontier] = None

        # ── Blacklist ─────────────────────────────────────────────────────────
        self._blacklist:          List[BlacklistEntry] = []
        self._blacklisted_ids:    Set[int] = set()
        self._failure_counter:    dict = {}  # frontier_id → count

        # ── Nav2 Action Client ────────────────────────────────────────────────
        self._nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._goal_handle = None
        self._goal_result: Optional[int] = None  # GoalStatus code
        self._goal_accepted = False

        # ── Metrics / tracking ────────────────────────────────────────────────
        self._goals_sent      = 0
        self._goals_completed = 0
        self._goals_failed    = 0
        self._session_start   = self.get_clock().now().nanoseconds / 1e9

        # ── Navigation timing ─────────────────────────────────────────────────
        self._goal_start_time:     Optional[float] = None
        self._last_robot_x:        Optional[float] = None
        self._last_robot_y:        Optional[float] = None
        self._last_move_time:      Optional[float] = None

        # ── Completion tracking ───────────────────────────────────────────────
        self._no_frontier_count  = 0
        self._map_free_history:  Deque[tuple] = deque(maxlen=60)  # (time, free_cells)
        self._robot_linear_vel   = 0.0

        # ── Map data ─────────────────────────────────────────────────────────
        self._latest_map: Optional[OccupancyGrid] = None

        # ── Subscriptions ─────────────────────────────────────────────────────
        map_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
            depth=1,
        )
        self.create_subscription(
            OccupancyGrid, '/rtabmap/map', self._map_callback, map_qos)
        self.create_subscription(
            PoseArray, '/frontiers/centroids', self._frontiers_callback, 10)
        self.create_subscription(
            Odometry, '/odom', self._odom_callback, 10)

        # ── Publishers ────────────────────────────────────────────────────────
        self._status_pub        = self.create_publisher(String, '/exploration/status', 10)
        self._selected_goal_pub = self.create_publisher(PoseStamped, '/exploration/current_goal', 10)
        self._selected_marker_pub = self.create_publisher(MarkerArray, '/exploration/selected_marker', 10)

        # ── FSM Timer (10 Hz) ─────────────────────────────────────────────────
        self.create_timer(0.10, self._fsm_tick)

        self.get_logger().info('ExplorationManager started. Waiting for Nav2...')

    # ── Subscription callbacks ─────────────────────────────────────────────────

    def _map_callback(self, msg: OccupancyGrid) -> None:
        self._latest_map = msg
        free = sum(1 for v in msg.data if v == 0)
        t = self.get_clock().now().nanoseconds / 1e9
        self._map_free_history.append((t, free))

    def _frontiers_callback(self, msg: PoseArray) -> None:
        """Reconstruct Frontier list from PoseArray published by FrontierDetector."""
        frontiers = []
        for i, pose in enumerate(msg.poses):
            frontiers.append(Frontier(
                id=i,
                centroid_x=pose.position.x,
                centroid_y=pose.position.y,
                size=max(1, int(pose.position.z)),  # size encoded in z
            ))
        self._frontiers = frontiers

    def _odom_callback(self, msg: Odometry) -> None:
        self._robot_linear_vel = abs(msg.twist.twist.linear.x)
        rx = msg.pose.pose.position.x
        ry = msg.pose.pose.position.y
        t  = self.get_clock().now().nanoseconds / 1e9

        if self._last_robot_x is not None:
            moved = math.hypot(rx - self._last_robot_x, ry - self._last_robot_y)
            if moved > 0.05:
                self._last_move_time = t

        self._last_robot_x = rx
        self._last_robot_y = ry

    # ── FSM tick ───────────────────────────────────────────────────────────────

    def _fsm_tick(self) -> None:
        current_time = self.get_clock().now().nanoseconds / 1e9

        # Purge expired blacklist entries
        self._purge_blacklist(current_time)

        # State machine
        if self._state == ExplorationState.IDLE:
            self.get_logger().info('Exploration started. Waiting for map...')
            self._state = ExplorationState.WAITING_FOR_MAP

        elif self._state == ExplorationState.WAITING_FOR_MAP:
            if self._map_has_free_cells():
                self.get_logger().info('Map received with free cells. Beginning frontier detection.')
                self._last_move_time = current_time
                self._state = ExplorationState.DETECT_FRONTIERS

        elif self._state == ExplorationState.DETECT_FRONTIERS:
            if self._frontiers:
                self._no_frontier_count = 0
                self._state = ExplorationState.SELECT_GOAL
            else:
                self._no_frontier_count += 1
                self.get_logger().info(
                    f'No frontiers detected ({self._no_frontier_count}/'
                    f'{self._no_frontier_checks_req})'
                )
                if self._check_completion(current_time):
                    self._state = ExplorationState.FINISHED

        elif self._state == ExplorationState.SELECT_GOAL:
            robot_x = self._last_robot_x or 0.0
            robot_y = self._last_robot_y or 0.0
            chosen = self._selector.select_best(
                frontiers=self._frontiers,
                robot_x=robot_x,
                robot_y=robot_y,
                blacklisted_ids=self._blacklisted_ids,
                occupancy_grid=self._latest_map,
            )
            if chosen is None:
                self.get_logger().warning('No eligible frontier after scoring. Re-detecting...')
                self._state = ExplorationState.DETECT_FRONTIERS
            else:
                self._current_frontier = chosen
                self.get_logger().info(
                    f'Selected frontier #{chosen.id} at '
                    f'({chosen.centroid_x:.2f}, {chosen.centroid_y:.2f}) '
                    f'size={chosen.size}'
                )
                self._publish_selected_marker(chosen)
                self._state = ExplorationState.SEND_GOAL

        elif self._state == ExplorationState.SEND_GOAL:
            if not self._nav_client.wait_for_server(timeout_sec=5.0):
                self.get_logger().error('Nav2 NavigateToPose action server not available!')
                self._state = ExplorationState.DETECT_FRONTIERS
                return
            self._send_nav_goal(self._current_frontier)
            self._goal_start_time = current_time
            self._last_move_time  = current_time
            self._goals_sent += 1
            self._state = ExplorationState.NAVIGATING

        elif self._state == ExplorationState.NAVIGATING:
            # Check goal result
            if self._goal_result is not None:
                if self._goal_result == GoalStatus.STATUS_SUCCEEDED:
                    self._state = ExplorationState.GOAL_REACHED
                else:
                    self._blacklist_frontier(self._current_frontier, current_time, 'nav2_failure')
                    self._state = ExplorationState.RECOVERING
                self._goal_result = None
                return

            # Check timeout
            elapsed = current_time - (self._goal_start_time or current_time)
            if elapsed > self._goal_timeout:
                self.get_logger().warning(
                    f'Goal timeout ({elapsed:.1f}s). Blacklisting frontier #{self._current_frontier.id}')
                self._cancel_goal()
                self._blacklist_frontier(self._current_frontier, current_time, 'timeout')
                self._state = ExplorationState.RECOVERING
                return

            # Check oscillation (robot not moving while navigating)
            last_move = self._last_move_time or current_time
            if (current_time - last_move) > self._oscillation_timeout:
                self.get_logger().warning('Oscillation detected. Cancelling goal.')
                self._cancel_goal()
                self._blacklist_frontier(self._current_frontier, current_time, 'oscillation')
                self._state = ExplorationState.RECOVERING

        elif self._state == ExplorationState.GOAL_REACHED:
            self._goals_completed += 1
            self.get_logger().info(
                f'Goal reached! Completed={self._goals_completed} Failed={self._goals_failed}')
            self._current_frontier = None
            self._state = ExplorationState.DETECT_FRONTIERS

        elif self._state == ExplorationState.RECOVERING:
            self._goals_failed += 1
            # Adaptive threshold: if many failures, tighten min_frontier_size
            if self._goals_failed > 0 and self._goals_failed % 5 == 0:
                self.get_logger().warning(
                    f'{self._goals_failed} failures — temporarily tightening frontier filter.')
            self._current_frontier = None
            self._state = ExplorationState.DETECT_FRONTIERS

        elif self._state == ExplorationState.FINISHED:
            self.get_logger().info(
                '\n═══════════════════════════════════════\n'
                '  EXPLORATION COMPLETE\n'
                f'  Goals completed : {self._goals_completed}\n'
                f'  Goals failed    : {self._goals_failed}\n'
                f'  Elapsed         : {(current_time - self._session_start):.1f} s\n'
                '═══════════════════════════════════════'
            )
            # Publish final status once then stop ticking
            self._publish_status(current_time)
            # Destroy timer to stop FSM
            # (node stays alive for status queries)
            raise StopIteration  # caught below in _fsm_tick wrapper

        # Publish status every tick
        self._publish_status(current_time)

    # ── Helper: completion check ───────────────────────────────────────────────

    def _check_completion(self, current_time: float) -> bool:
        """All three completion conditions must be simultaneously true."""
        # Condition 1: consecutive no-frontier detections
        cond1 = self._no_frontier_count >= self._no_frontier_checks_req

        # Condition 2: map has not grown significantly in patience window
        cond2 = False
        if len(self._map_free_history) >= 2:
            oldest_t, oldest_free = self._map_free_history[0]
            newest_t, newest_free = self._map_free_history[-1]
            window = newest_t - oldest_t
            if window >= self._map_growth_patience:
                growth = newest_free - oldest_free
                cond2 = growth < self._map_growth_threshold

        # Condition 3: robot is stationary
        cond3 = self._robot_linear_vel < self._stationary_vel_thresh

        if cond1 and cond2 and cond3:
            self.get_logger().info(
                f'Completion conditions met: no_frontiers={cond1} '
                f'map_stable={cond2} stationary={cond3}')
            return True
        return False

    def _map_has_free_cells(self) -> bool:
        if self._latest_map is None:
            return False
        return any(v == 0 for v in self._latest_map.data)

    # ── Helper: blacklist management ───────────────────────────────────────────

    def _blacklist_frontier(
        self, frontier: Frontier, current_time: float, reason: str
    ) -> None:
        count = self._failure_counter.get(frontier.id, 0) + 1
        self._failure_counter[frontier.id] = count

        existing = next(
            (b for b in self._blacklist if b.frontier_id == frontier.id), None)
        if existing:
            existing.failure_count     = count
            existing.last_failure_time = current_time
        else:
            self._blacklist.append(BlacklistEntry(
                frontier_id=       frontier.id,
                centroid_x=        frontier.centroid_x,
                centroid_y=        frontier.centroid_y,
                failure_count=     count,
                last_failure_time= current_time,
                expiry_sec=        self._blacklist_expiry,
            ))

        self._blacklisted_ids.add(frontier.id)
        self.get_logger().warning(
            f'Blacklisted frontier #{frontier.id} (reason={reason}, count={count})'
        )

    def _purge_blacklist(self, current_time: float) -> None:
        expired = [b for b in self._blacklist if b.is_expired(current_time)]
        for entry in expired:
            self._blacklist.remove(entry)
            self._blacklisted_ids.discard(entry.frontier_id)
            self.get_logger().info(
                f'Frontier #{entry.frontier_id} removed from blacklist (expired)')

    # ── Nav2 Action Client helpers ─────────────────────────────────────────────

    def _send_nav_goal(self, frontier: Frontier) -> None:
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.stamp    = self.get_clock().now().to_msg()
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.pose.position.x = frontier.centroid_x
        goal_msg.pose.pose.position.y = frontier.centroid_y
        goal_msg.pose.pose.position.z = 0.0
        goal_msg.pose.pose.orientation.w = 1.0

        send_future = self._nav_client.send_goal_async(
            goal_msg,
            feedback_callback=self._goal_feedback_callback,
        )
        send_future.add_done_callback(self._goal_response_callback)

        # Publish goal as PoseStamped for RViz
        ps = PoseStamped()
        ps.header = goal_msg.pose.header
        ps.pose   = goal_msg.pose.pose
        self._selected_goal_pub.publish(ps)

    def _goal_response_callback(self, future) -> None:
        self._goal_handle = future.result()
        if not self._goal_handle.accepted:
            self.get_logger().error('Goal rejected by Nav2!')
            self._goal_result = GoalStatus.STATUS_ABORTED
            return
        self.get_logger().info('Goal accepted by Nav2.')
        result_future = self._goal_handle.get_result_async()
        result_future.add_done_callback(self._goal_result_callback)

    def _goal_result_callback(self, future) -> None:
        result = future.result()
        self._goal_result = result.status

    def _goal_feedback_callback(self, feedback_msg) -> None:
        # Could log distance remaining here if needed
        pass

    def _cancel_goal(self) -> None:
        if self._goal_handle is not None:
            self._goal_handle.cancel_goal_async()
            self._goal_handle = None

    # ── RViz marker for selected frontier ─────────────────────────────────────

    def _publish_selected_marker(self, frontier: Frontier) -> None:
        ma = MarkerArray()
        m = Marker()
        m.header.stamp    = self.get_clock().now().to_msg()
        m.header.frame_id = 'map'
        m.ns              = 'selected_frontier'
        m.id              = 0
        m.type            = Marker.SPHERE
        m.action          = Marker.ADD
        m.pose.position.x = frontier.centroid_x
        m.pose.position.y = frontier.centroid_y
        m.pose.position.z = 0.25
        m.pose.orientation.w = 1.0
        m.scale.x = m.scale.y = m.scale.z = 0.45
        m.color.r = 1.0    # red = selected frontier
        m.color.g = 0.0
        m.color.b = 0.0
        m.color.a = 1.0
        m.lifetime.sec = 5
        ma.markers.append(m)
        self._selected_marker_pub.publish(ma)

    # ── Status publisher ───────────────────────────────────────────────────────

    def _publish_status(self, current_time: float) -> None:
        free_cells = 0
        total_cells = 0
        coverage_pct = 0.0
        if self._latest_map is not None:
            data = self._latest_map.data
            free_cells    = sum(1 for v in data if v == 0)
            unknown_cells = sum(1 for v in data if v == -1)
            total_relevant = free_cells + unknown_cells
            if total_relevant > 0:
                coverage_pct = (free_cells / total_relevant) * 100.0

        status = {
            'state':               self._state.value,
            'frontier_id':         self._current_frontier.id if self._current_frontier else -1,
            'coverage_pct':        round(coverage_pct, 2),
            'goals_completed':     self._goals_completed,
            'goals_failed':        self._goals_failed,
            'frontiers_remaining': len(self._frontiers),
            'blacklisted_count':   len(self._blacklisted_ids),
            'elapsed_sec':         round(current_time - self._session_start, 1),
        }
        msg = String()
        msg.data = json.dumps(status)
        self._status_pub.publish(msg)


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = ExplorationManager()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, StopIteration):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
