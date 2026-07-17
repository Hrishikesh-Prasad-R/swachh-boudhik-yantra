#!/usr/bin/env python3.12
"""
goal_selector.py  —  Stage 4B: Frontier Goal Selector (Utility Class)
──────────────────────────────────────────────────────────────────────
This module provides the GoalSelector class, imported by exploration_manager.py.
It is NOT a standalone ROS 2 node.

Scoring function:
  score(f) = w_info * size(f)
           - w_dist * distance(robot_pose, f)
           - w_obs  * obstacle_proximity_penalty(f, occupancy_grid)

A higher score is better. The selector returns the highest-scoring
non-blacklisted frontier. If all frontiers are blacklisted, returns None.

Obstacle proximity penalty:
  Searches a small neighbourhood around the frontier centroid in the
  occupancy grid. Returns a penalty inversely proportional to the
  minimum distance to any obstacle cell.
"""

import math
from typing import List, Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from nav_msgs.msg import OccupancyGrid


# ─────────────────────────────────────────────────────────────────────────────
#  GoalSelector
# ─────────────────────────────────────────────────────────────────────────────

class GoalSelector:
    """
    Scores frontier candidates and selects the best non-blacklisted goal.

    Parameters are loaded once at construction; call update_weights() to
    change them at runtime (e.g., from a ROS parameter update callback).
    """

    def __init__(
        self,
        weight_info_gain:        float = 1.0,
        weight_distance:         float = 1.5,
        weight_obstacle_penalty: float = 0.8,
        min_goal_distance:       float = 0.30,
        obstacle_search_radius:  float = 0.50,  # m — radius to search for obstacles
    ):
        self._w_info    = weight_info_gain
        self._w_dist    = weight_distance
        self._w_obs     = weight_obstacle_penalty
        self._min_dist  = min_goal_distance
        self._obs_radius = obstacle_search_radius

    def update_weights(
        self,
        weight_info_gain:        float,
        weight_distance:         float,
        weight_obstacle_penalty: float,
    ) -> None:
        """Allow runtime tuning of scoring weights."""
        self._w_info = weight_info_gain
        self._w_dist = weight_distance
        self._w_obs  = weight_obstacle_penalty

    def select_best(
        self,
        frontiers: list,             # List[Frontier] from frontier_detector
        robot_x: float,
        robot_y: float,
        blacklisted_ids: set,        # set of frontier IDs to skip
        occupancy_grid=None,         # OccupancyGrid or None (obstacle check)
    ) -> Optional[object]:           # Returns Frontier or None
        """
        Score all frontiers and return the highest-scoring non-blacklisted one.

        Returns None if no eligible frontiers exist.
        """
        best_frontier  = None
        best_score     = float('-inf')

        for f in frontiers:
            # Skip blacklisted frontiers
            if f.id in blacklisted_ids:
                continue

            # Compute distance, skip if too close
            dist = math.hypot(f.centroid_x - robot_x, f.centroid_y - robot_y)
            if dist < self._min_dist:
                continue

            # Score
            score = self._compute_score(f, dist, occupancy_grid)

            if score > best_score:
                best_score    = score
                best_frontier = f

        return best_frontier

    def score_all(
        self,
        frontiers: list,
        robot_x: float,
        robot_y: float,
        blacklisted_ids: set,
        occupancy_grid=None,
    ) -> List[tuple]:
        """
        Return a sorted list of (score, frontier) tuples for debugging.
        Includes blacklisted frontiers (marked separately).
        """
        results = []
        for f in frontiers:
            dist  = math.hypot(f.centroid_x - robot_x, f.centroid_y - robot_y)
            score = self._compute_score(f, dist, occupancy_grid)
            results.append((score, f, f.id in blacklisted_ids))
        results.sort(key=lambda x: x[0], reverse=True)
        return results

    # ── Internal scoring ──────────────────────────────────────────────────────

    def _compute_score(self, frontier, dist: float, occupancy_grid) -> float:
        """
        Compute the composite score for one frontier.

        score = w_info * normalized_size
              - w_dist * dist
              - w_obs  * obstacle_proximity_penalty
        """
        # Information gain: normalise size to 0..1 using log scale
        info_gain = math.log(1 + frontier.size)

        # Obstacle proximity penalty
        if occupancy_grid is not None:
            obs_penalty = self._obstacle_penalty(
                frontier.centroid_x, frontier.centroid_y, occupancy_grid
            )
        else:
            obs_penalty = 0.0

        return (
            self._w_info * info_gain
            - self._w_dist * dist
            - self._w_obs  * obs_penalty
        )

    def _obstacle_penalty(
        self, cx: float, cy: float, grid
    ) -> float:
        """
        Penalty based on how close the frontier centroid is to obstacle cells.

        Returns a value in [0, 1]:
          0.0 = no nearby obstacles (safe frontier)
          1.0 = obstacle immediately adjacent (dangerous frontier)
        """
        res    = grid.info.resolution
        ox     = grid.info.origin.position.x
        oy     = grid.info.origin.position.y
        width  = grid.info.width
        height = grid.info.height
        data   = grid.data

        # Convert centroid to grid coordinates
        col_c = int((cx - ox) / res)
        row_c = int((cy - oy) / res)

        search_r = max(1, int(self._obs_radius / res))
        min_obs_dist = float('inf')

        for dr in range(-search_r, search_r + 1):
            for dc in range(-search_r, search_r + 1):
                r = row_c + dr
                c = col_c + dc
                if 0 <= r < height and 0 <= c < width:
                    idx = r * width + c
                    # Obstacle: occupancy > 50 (0..100 range)
                    if data[idx] > 50:
                        d = math.hypot(dr * res, dc * res)
                        min_obs_dist = min(min_obs_dist, d)

        if min_obs_dist == float('inf'):
            return 0.0

        # Normalise: 0 distance → penalty 1, obs_radius distance → penalty 0
        return max(0.0, 1.0 - (min_obs_dist / self._obs_radius))
