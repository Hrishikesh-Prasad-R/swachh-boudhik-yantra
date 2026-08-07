#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  stop.sh — Swachh Boudhik Yantra Emergency Stop & Clean Script
# ═══════════════════════════════════════════════════════════════

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "╔══════════════════════════════════════════════════════╗"
echo "║        Swachh Boudhik Yantra — STOP                  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "Stopping all Gazebo, ROS 2, RTAB-Map, and Nav2 processes..."

# Kill ROS 2 launch processes, Gazebo, RTAB-Map, Nav2 and nodes
pkill -9 -f "ros2 launch" 2>/dev/null || true
pkill -9 -f "gz sim" 2>/dev/null || true
pkill -9 -f "rtabmap" 2>/dev/null || true
pkill -9 -f "nav2" 2>/dev/null || true
pkill -9 -f "bt_navigator" 2>/dev/null || true
pkill -9 -f "planner_server" 2>/dev/null || true
pkill -9 -f "controller_server" 2>/dev/null || true
pkill -9 -f "behavior_server" 2>/dev/null || true
pkill -9 -f "smoother_server" 2>/dev/null || true
pkill -9 -f "velocity_smoother" 2>/dev/null || true
pkill -9 -f "exploration_manager" 2>/dev/null || true
pkill -9 -f "frontier_detector" 2>/dev/null || true
pkill -9 -f "frontier_visualizer" 2>/dev/null || true
pkill -9 -f "exploration_metrics" 2>/dev/null || true
pkill -9 -f "robot_state_publisher" 2>/dev/null || true
pkill -9 -f "parameter_bridge" 2>/dev/null || true
pkill -9 -f "rviz2" 2>/dev/null || true

# Always erase RTAB-Map memory database so next run starts with a completely blank map
echo "Clearing RTAB-Map memory database (~/.ros/rtabmap.db*)..."
rm -rf ~/.ros/rtabmap.db*

echo "✅ All processes stopped and map memory cleared."
