# How To Do Everything — Q1 Paper Experiments
### Exact commands + code for all 8 phases

---

# PHASE 1 — Build Your Test Worlds

## 1.1 Create worlds folder
```bash
mkdir -p ~/paper_ws/worlds ~/paper_ws/maps ~/paper_ws/bags ~/paper_ws/results
```

## 1.2 Simple Room World
Save as `~/paper_ws/worlds/simple_room.world`:
```xml
<?xml version="1.0"?>
<sdf version="1.9">
  <world name="simple_room">
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <light name="sun" type="directional">
      <pose>0 0 10 0 0 0</pose><diffuse>1 1 1 1</diffuse><specular>0.5 0.5 0.5 1</specular>
    </light>
    <model name="ground_plane"><static>true</static>
      <link name="link"><collision name="c"><geometry><plane><normal>0 0 1</normal><size>50 50</size></plane></geometry></collision>
      <visual name="v"><geometry><plane><normal>0 0 1</normal><size>50 50</size></plane></geometry></visual></link>
    </model>
    <!-- 4 walls: 10x10m room -->
    <model name="wall_n"><static>true</static><pose>0 5 1 0 0 0</pose>
      <link name="l"><collision name="c"><geometry><box><size>10.2 0.2 2</size></box></geometry></collision>
      <visual name="v"><geometry><box><size>10.2 0.2 2</size></box></geometry></visual></link></model>
    <model name="wall_s"><static>true</static><pose>0 -5 1 0 0 0</pose>
      <link name="l"><collision name="c"><geometry><box><size>10.2 0.2 2</size></box></geometry></collision>
      <visual name="v"><geometry><box><size>10.2 0.2 2</size></box></geometry></visual></link></model>
    <model name="wall_e"><static>true</static><pose>5 0 1 0 0 1.5708</pose>
      <link name="l"><collision name="c"><geometry><box><size>10.2 0.2 2</size></box></geometry></collision>
      <visual name="v"><geometry><box><size>10.2 0.2 2</size></box></geometry></visual></link></model>
    <model name="wall_w"><static>true</static><pose>-5 0 1 0 0 1.5708</pose>
      <link name="l"><collision name="c"><geometry><box><size>10.2 0.2 2</size></box></geometry></collision>
      <visual name="v"><geometry><box><size>10.2 0.2 2</size></box></geometry></visual></link></model>
  </world>
</sdf>
```

## 1.3 Static Obstacle Room — add these inside `<world>`:
```xml
<!-- Cylinder obstacles -->
<model name="obs_1"><static>true</static><pose>2 1 0.5 0 0 0</pose>
  <link name="l"><collision name="c"><geometry><cylinder><radius>0.2</radius><length>1</length></cylinder></geometry></collision>
  <visual name="v"><geometry><cylinder><radius>0.2</radius><length>1</length></cylinder></geometry></visual></link></model>
<model name="obs_2"><static>true</static><pose>-2 -1 0.5 0 0 0</pose>
  <link name="l"><collision name="c"><geometry><box><size>0.5 0.5 1</size></box></geometry></collision>
  <visual name="v"><geometry><box><size>0.5 0.5 1</size></box></geometry></visual></link></model>
<!-- Add more by copying and changing pose -->
```

## 1.4 Dynamic Obstacles (Moving Actor)
```xml
<actor name="walking_person">
  <pose>0 2 1.0 0 0 0</pose>
  <skin><filename>https://fuel.gazebosim.org/1.0/Mingfei/models/actor/tip/files/meshes/walk.dae</filename></skin>
  <animation name="walk"><filename>walk.dae</filename><interpolate_x>true</interpolate_x></animation>
  <script>
    <loop>true</loop>
    <trajectory id="0" type="walk">
      <waypoint><time>0</time><pose>0 2 1.0 0 0 0</pose></waypoint>
      <waypoint><time>4</time><pose>0 -2 1.0 0 0 0</pose></waypoint>
      <waypoint><time>8</time><pose>0 2 1.0 0 0 0</pose></waypoint>
    </trajectory>
  </script>
</actor>
```

## 1.5 Launch Gazebo with your world
```bash
export TURTLEBOT3_MODEL=waffle
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py \
    world:=$HOME/paper_ws/worlds/simple_room.world
```

---

# PHASE 2 — Run Each SLAM Algorithm

## Every SLAM test: open 3 terminals

### Terminal 1 — always (Gazebo)
```bash
export TURTLEBOT3_MODEL=waffle
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py \
    world:=$HOME/paper_ws/worlds/YOUR_WORLD.world
```

### Terminal 2 — choose ONE SLAM:

**SLAM Toolbox (async — recommended):**
```bash
ros2 launch slam_toolbox online_async_launch.py \
    use_sim_time:=true \
    slam_params_file:=/opt/ros/jazzy/share/slam_toolbox/config/mapper_params_online_async.yaml
```

**SLAM Toolbox (sync):**
```bash
ros2 launch slam_toolbox online_sync_launch.py use_sim_time:=true
```

**Cartographer:**
```bash
ros2 launch turtlebot3_cartographer cartographer.launch.py use_sim_time:=true
```

**RTAB-Map (LiDAR only):**
```bash
ros2 launch rtabmap_launch rtabmap.launch.py \
    use_sim_time:=true \
    scan_topic:=/scan \
    frame_id:=base_footprint \
    subscribe_depth:=false \
    subscribe_rgb:=false \
    args:="--delete_db_on_start"
```

**RTAB-Map (RGB-D only — D435i):**
```bash
ros2 launch rtabmap_launch rtabmap.launch.py \
    use_sim_time:=true \
    rgb_topic:=/camera/image_raw \
    depth_topic:=/camera/depth/image_raw \
    camera_info_topic:=/camera/camera_info \
    frame_id:=base_footprint \
    args:="--delete_db_on_start"
```

**RTAB-Map (LiDAR + RGB-D fusion):**
```bash
ros2 launch rtabmap_launch rtabmap.launch.py \
    use_sim_time:=true \
    scan_topic:=/scan \
    rgb_topic:=/camera/image_raw \
    depth_topic:=/camera/depth/image_raw \
    camera_info_topic:=/camera/camera_info \
    frame_id:=base_footprint \
    args:="--delete_db_on_start"
```

### Terminal 3 — Record bag + teleoperate
```bash
# Start recording
ros2 bag record /odom /scan /tf /tf_static /map \
    -o ~/paper_ws/bags/slam_toolbox_simple_room_run1

# In another terminal — drive the robot
ros2 run turtlebot3_teleop teleop_keyboard
```

### Save the map when done:
```bash
ros2 run nav2_map_server map_saver_cli \
    -f ~/paper_ws/maps/slam_toolbox_simple_room
```

---

# PHASE 3 — Switch Path Planners in Nav2

## 3.1 Copy Nav2 params and edit planner
```bash
cp /opt/ros/jazzy/share/nav2_bringup/params/nav2_params.yaml \
   ~/paper_ws/nav2_params_hybrid_astar.yaml
```

Edit `~/paper_ws/nav2_params_hybrid_astar.yaml`:

**For NavFn (Dijkstra):**
```yaml
planner_server:
  ros__parameters:
    planner_plugins: ["GridBased"]
    GridBased:
      plugin: "nav2_navfn_planner/NavfnPlanner"
      use_astar: false          # <-- Dijkstra
      allow_unknown: true
```

**For NavFn (A*):**
```yaml
      use_astar: true           # <-- A*
```

**For SMAC Hybrid A*:**
```yaml
planner_server:
  ros__parameters:
    planner_plugins: ["GridBased"]
    GridBased:
      plugin: "nav2_smac_planner/SmacPlannerHybrid"
      motion_model_for_search: "REEDS_SHEPP"
      angle_quantization_bins: 72
      analytic_expansion_ratio: 3.5
      minimum_turning_radius: 0.40
```

**For Theta*:**
```yaml
    GridBased:
      plugin: "nav2_theta_star_planner/ThetaStarPlanner"
      how_many_corners: 8
      w_euc_cost: 1.0
      w_traversal_cost: 2.0
```

**For local planner — DWB:**
```yaml
controller_server:
  ros__parameters:
    controller_plugins: ["FollowPath"]
    FollowPath:
      plugin: "dwb_core::DWBLocalPlanner"
      max_vel_x: 0.26
      min_vel_x: -0.26
      max_vel_theta: 1.0
```

**For local planner — MPPI:**
```yaml
    FollowPath:
      plugin: "nav2_mppi_controller::MPPIController"
      time_steps: 56
      model_dt: 0.05
      batch_size: 2000
      vx_std: 0.2
      vy_std: 0.0
      wz_std: 0.4
      vx_max: 0.5
      vx_min: -0.35
      wz_max: 1.9
```

## 3.2 Launch Nav2 with your params
```bash
ros2 launch nav2_bringup bringup_launch.py \
    use_sim_time:=true \
    map:=$HOME/paper_ws/maps/YOUR_MAP.yaml \
    params_file:=$HOME/paper_ws/nav2_params_hybrid_astar.yaml
```

## 3.3 Send goals automatically (Python)
Save as `~/paper_ws/scripts/send_goals.py`:
```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from nav2_simple_commander.robot_navigator import BasicNavigator
from geometry_msgs.msg import PoseStamped
import time, csv, math

# Define your test goals (x, y, yaw)
GOALS = [
    (1.0,  1.0,  0.0),
    (2.0, -1.0,  1.57),
    (-1.0, 2.0,  3.14),
    (-2.0, -2.0, -1.57),
    (0.0,  0.0,  0.0),   # return to start
]

def make_pose(x, y, yaw):
    pose = PoseStamped()
    pose.header.frame_id = 'map'
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.orientation.w = math.cos(yaw / 2)
    pose.pose.orientation.z = math.sin(yaw / 2)
    return pose

def main():
    rclpy.init()
    nav = BasicNavigator()
    nav.waitUntilNav2Active()

    results = []
    for i, (x, y, yaw) in enumerate(GOALS):
        print(f"Goal {i+1}: ({x}, {y})")
        t_start = time.time()
        nav.goToPose(make_pose(x, y, yaw))

        while not nav.isTaskComplete():
            pass

        t_end = time.time()
        result = nav.getResult()
        success = str(result) == 'TaskResult.SUCCEEDED'

        results.append({
            'goal': i+1,
            'x': x, 'y': y,
            'success': success,
            'time_s': round(t_end - t_start, 2)
        })
        print(f"  Result: {result} | Time: {t_end-t_start:.1f}s")
        time.sleep(1.0)

    # Save to CSV
    with open('/tmp/nav_results.csv', 'w') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print("Results saved to /tmp/nav_results.csv")

if __name__ == '__main__':
    main()
```

```bash
python3 ~/paper_ws/scripts/send_goals.py
```

---

# PHASE 4 — Obstacle Avoidance Tests

## 4.1 Test narrow gap — add to world SDF
```xml
<!-- Narrow corridor: two walls with 0.8m gap -->
<model name="gap_left"><static>true</static><pose>1 0.6 0.5 0 0 0</pose>
  <link name="l"><collision name="c"><geometry><box><size>2 0.2 1</size></box></geometry></collision>
  <visual name="v"><geometry><box><size>2 0.2 1</size></box></geometry></visual></link></model>
<model name="gap_right"><static>true</static><pose>1 -0.6 0.5 0 0 0</pose>
  <link name="l"><collision name="c"><geometry><box><size>2 0.2 1</size></box></geometry></collision>
  <visual name="v"><geometry><box><size>2 0.2 1</size></box></geometry></visual></link></model>
```

## 4.2 Monitor minimum obstacle distance during run
```python
# Save as monitor_distance.py
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
import csv, time

class Monitor(Node):
    def __init__(self):
        super().__init__('monitor')
        self.sub = self.create_subscription(LaserScan, '/scan', self.cb, 10)
        self.log = []

    def cb(self, msg):
        valid = [r for r in msg.ranges if 0.1 < r < 10.0]
        if valid:
            self.log.append({'time': time.time(), 'min_dist': min(valid), 'mean_dist': sum(valid)/len(valid)})

def main():
    rclpy.init()
    node = Monitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        with open('/tmp/distance_log.csv', 'w') as f:
            writer = csv.DictWriter(f, fieldnames=['time','min_dist','mean_dist'])
            writer.writeheader()
            writer.writerows(node.log)
        print(f"Min distance ever: {min(r['min_dist'] for r in node.log):.3f}m")

if __name__ == '__main__':
    main()
```

## 4.3 Count recovery behaviour triggers
```bash
# Watch Nav2 behavior tree status
ros2 topic echo /behavior_server/transition_event | grep -c "ACTIVATE"

# Or watch for recovery actions specifically
ros2 topic echo /spin/_action/status
ros2 topic echo /backup/_action/status
```

---

# PHASE 5 — Sensor Configuration Tests

## 5.1 Add noise to LiDAR in URDF (for noise tests)
```xml
<!-- In your robot URDF, add noise to laser plugin -->
<gazebo reference="base_scan">
  <sensor type="ray" name="noisy_lidar">
    <ray>
      <noise>
        <type>gaussian</type>
        <mean>0.0</mean>
        <stddev>0.05</stddev>   <!-- Change this: 0.01, 0.05, 0.10 -->
      </noise>
    </ray>
  </sensor>
</gazebo>
```

## 5.2 Switch sensor configs at launch time
```bash
# LiDAR only — disable camera in launch
ros2 launch rtabmap_launch rtabmap.launch.py \
    subscribe_depth:=false subscribe_rgb:=false \
    scan_topic:=/scan use_sim_time:=true

# D435i depth only — disable scan
ros2 launch rtabmap_launch rtabmap.launch.py \
    subscribe_scan:=false \
    rgb_topic:=/camera/image_raw \
    depth_topic:=/camera/depth/image_raw \
    use_sim_time:=true
```

---

# PHASE 6 — Metrics Extraction

## 6.1 Compute ATE and RPE with evo

```bash
# Step 1: Get ground truth from Gazebo
ros2 bag record /model/turtlebot3_waffle/pose \
    -o ~/paper_ws/bags/ground_truth_run1

# Step 2: Get estimated trajectory from odom
ros2 bag record /odom -o ~/paper_ws/bags/odom_run1

# Step 3: Convert to TUM format
evo_traj bag2 ~/paper_ws/bags/odom_run1 /odom \
    --save_as_tum -o /tmp/odom_est.tum

evo_traj bag2 ~/paper_ws/bags/ground_truth_run1 /model/turtlebot3_waffle/pose \
    --save_as_tum -o /tmp/ground_truth.tum

# Step 4: Compute ATE
evo_ape tum /tmp/ground_truth.tum /tmp/odom_est.tum \
    -va --plot --save_results /tmp/ate_results.zip

# Step 5: Compute RPE
evo_rpe tum /tmp/ground_truth.tum /tmp/odom_est.tum \
    -va --plot --save_results /tmp/rpe_results.zip
```

## 6.2 CPU and RAM logger (run during every experiment)
```python
# Save as ~/paper_ws/scripts/log_resources.py
import psutil, time, csv, sys

output_file = sys.argv[1] if len(sys.argv) > 1 else '/tmp/resources.csv'
duration = int(sys.argv[2]) if len(sys.argv) > 2 else 300  # seconds

with open(output_file, 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['time_s', 'cpu_percent', 'ram_mb', 'ram_percent'])
    for i in range(duration):
        writer.writerow([
            i,
            psutil.cpu_percent(interval=1),
            psutil.virtual_memory().used / 1e6,
            psutil.virtual_memory().percent
        ])
        print(f"t={i}s CPU={psutil.cpu_percent()}% RAM={psutil.virtual_memory().used/1e6:.0f}MB")
```

```bash
# Run alongside your experiment
python3 ~/paper_ws/scripts/log_resources.py \
    ~/paper_ws/results/rtabmap_hybrid_dynamic_run1_resources.csv \
    300 &
```

## 6.3 Path length from odometry bag
```python
# Save as ~/paper_ws/scripts/path_length.py
import sys, math
from rosbags.rosbag2 import Reader
from rosbags.typesys import Stores, get_typestore

bag_path = sys.argv[1]
typestore = get_typestore(Stores.ROS2_JAZZY)

total_dist = 0.0
prev = None
timestamps = []

with Reader(bag_path) as reader:
    odom_conns = [c for c in reader.connections if c.topic == '/odom']
    for conn, ts, rawdata in reader.messages(connections=odom_conns):
        msg = typestore.deserialize_cdr(rawdata, conn.msgtype)
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        if prev:
            total_dist += math.hypot(x - prev[0], y - prev[1])
        prev = (x, y)
        timestamps.append(ts)

duration = (timestamps[-1] - timestamps[0]) / 1e9
print(f"Path length:  {total_dist:.3f} m")
print(f"Duration:     {duration:.1f} s")
print(f"Avg speed:    {total_dist/duration:.3f} m/s")
```

```bash
python3 ~/paper_ws/scripts/path_length.py ~/paper_ws/bags/odom_run1
```

## 6.4 Map quality (SSIM) vs ground truth
```python
# Save as ~/paper_ws/scripts/map_quality.py
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim
import sys

gt_path   = sys.argv[1]   # ground truth map .pgm
slam_path = sys.argv[2]   # your SLAM map .pgm

gt   = cv2.imread(gt_path, cv2.IMREAD_GRAYSCALE)
slam = cv2.imread(slam_path, cv2.IMREAD_GRAYSCALE)

# Resize to same shape
slam = cv2.resize(slam, (gt.shape[1], gt.shape[0]))

# SSIM
score, _ = ssim(gt, slam, full=True)

# IoU (treat free space as foreground)
gt_bin   = (gt > 200).astype(np.uint8)
slam_bin = (slam > 200).astype(np.uint8)
intersection = np.logical_and(gt_bin, slam_bin).sum()
union        = np.logical_or(gt_bin, slam_bin).sum()
iou = intersection / union if union > 0 else 0

print(f"SSIM: {score:.4f}")
print(f"IoU:  {iou:.4f}")
```

```bash
python3 ~/paper_ws/scripts/map_quality.py \
    ~/paper_ws/maps/ground_truth.pgm \
    ~/paper_ws/maps/slam_toolbox_simple_room.pgm
```

---

# PHASE 7 — Full Automation Script

Save as `~/paper_ws/scripts/run_experiment.sh`:
```bash
#!/bin/bash
# Usage: ./run_experiment.sh <world> <slam_algo> <planner> <run_number>
# Example: ./run_experiment.sh simple_room slam_toolbox hybrid_astar 1

WORLD=$1
SLAM=$2
PLANNER=$3
RUN=$4
TAG="${SLAM}_${PLANNER}_${WORLD}_run${RUN}"
BAG_DIR="$HOME/paper_ws/bags/${TAG}"
RESULT_DIR="$HOME/paper_ws/results"

echo "=== Starting experiment: $TAG ==="

# 1. Start resource logger in background
python3 ~/paper_ws/scripts/log_resources.py \
    "${RESULT_DIR}/${TAG}_resources.csv" 400 &
RESOURCE_PID=$!

# 2. Record bag
ros2 bag record /odom /scan /tf /tf_static /map \
    -o "$BAG_DIR" &
BAG_PID=$!

sleep 5  # Let everything start

# 3. Send navigation goals
python3 ~/paper_ws/scripts/send_goals.py \
    > "${RESULT_DIR}/${TAG}_nav.log" 2>&1

# 4. Stop recording
kill $BAG_PID $RESOURCE_PID
sleep 2

# 5. Extract metrics
python3 ~/paper_ws/scripts/path_length.py "$BAG_DIR" \
    > "${RESULT_DIR}/${TAG}_path.txt"

echo "=== Done: $TAG ==="
echo "Results in: $RESULT_DIR"
```

```bash
chmod +x ~/paper_ws/scripts/run_experiment.sh
./run_experiment.sh simple_room slam_toolbox hybrid_astar 1
```

---

# PHASE 8 — Compile Results Table

```python
# Save as ~/paper_ws/scripts/compile_results.py
import os, csv, json, glob
import pandas as pd

results = []
for result_file in glob.glob('~/paper_ws/results/*_nav.log'):
    tag = os.path.basename(result_file).replace('_nav.log', '')
    parts = tag.split('_')

    # Read nav success/time
    # Read resource CSV
    resource_file = result_file.replace('_nav.log', '_resources.csv')
    if os.path.exists(resource_file):
        df = pd.read_csv(resource_file)
        cpu_mean = df['cpu_percent'].mean()
        ram_mean = df['ram_mb'].mean()
    else:
        cpu_mean = ram_mean = None

    results.append({
        'tag': tag,
        'cpu_mean': cpu_mean,
        'ram_mean_mb': ram_mean,
    })

df_all = pd.DataFrame(results)
df_all.to_csv('~/paper_ws/results/FINAL_RESULTS.csv', index=False)
print(df_all.to_string())
```

---

# Quick Reference — All Commands at a Glance

```bash
# ── Start Gazebo ──────────────────────────────────────────
export TURTLEBOT3_MODEL=waffle
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py world:=~/paper_ws/worlds/simple_room.world

# ── SLAM Toolbox ──────────────────────────────────────────
ros2 launch slam_toolbox online_async_launch.py use_sim_time:=true

# ── Cartographer ──────────────────────────────────────────
ros2 launch turtlebot3_cartographer cartographer.launch.py use_sim_time:=true

# ── RTAB-Map (LiDAR) ──────────────────────────────────────
ros2 launch rtabmap_launch rtabmap.launch.py use_sim_time:=true scan_topic:=/scan subscribe_depth:=false

# ── RTAB-Map (D435i RGB-D) ────────────────────────────────
ros2 launch rtabmap_launch rtabmap.launch.py use_sim_time:=true rgb_topic:=/camera/image_raw depth_topic:=/camera/depth/image_raw camera_info_topic:=/camera/camera_info

# ── Save Map ──────────────────────────────────────────────
ros2 run nav2_map_server map_saver_cli -f ~/paper_ws/maps/my_map

# ── Nav2 with custom params ───────────────────────────────
ros2 launch nav2_bringup bringup_launch.py use_sim_time:=true map:=~/paper_ws/maps/my_map.yaml params_file:=~/paper_ws/nav2_params_hybrid_astar.yaml

# ── Teleop ────────────────────────────────────────────────
ros2 run turtlebot3_teleop teleop_keyboard

# ── Record bag ────────────────────────────────────────────
ros2 bag record /odom /scan /tf /tf_static /map -o ~/paper_ws/bags/run1

# ── ATE metric ────────────────────────────────────────────
evo_ape tum ground_truth.tum estimated.tum -va --plot

# ── RPE metric ────────────────────────────────────────────
evo_rpe tum ground_truth.tum estimated.tum -va --plot

# ── RViz2 ─────────────────────────────────────────────────
ros2 launch nav2_bringup rviz_launch.py
```
