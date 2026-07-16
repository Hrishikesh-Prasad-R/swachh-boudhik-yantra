# ROS 2 Jazzy — Complete Gazebo SLAM + Navigation Roadmap
### For Q1 Paper Research | Ubuntu 26.04 | Gazebo Harmonic

---

## 📚 Official Documentation Links

| Topic | Link |
|-------|------|
| **Nav2 Getting Started** | https://docs.nav2.org/getting_started/index.html |
| **Nav2 First-Time Robot Setup** | https://docs.nav2.org/setup_guides/index.html |
| **SLAM Toolbox** | https://github.com/stevemacenski/slam_toolbox |
| **RTAB-Map ROS2** | https://github.com/introlab/rtabmap_ros/tree/ros2 |
| **RTAB-Map TurtleBot3 Demo** | https://wiki.ros.org/rtabmap_ros/Tutorials/SetupOnYourRobot |
| **TurtleBot3 Simulation** | https://emanual.robotis.com/docs/en/platform/turtlebot3/simulation/ |
| **Gazebo Harmonic + ROS2** | https://gazebosim.org/docs/harmonic/ros2_integration |
| **evo Trajectory Evaluation** | https://github.com/MichaelGrupp/evo |

---

## 🗺️ ROADMAP — Phases

---

## PHASE 1 — Environment Setup (Once)

### Step 1.1 — Set TurtleBot3 model
```bash
echo "export TURTLEBOT3_MODEL=waffle" >> ~/.bashrc
echo "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp" >> ~/.bashrc   # better Nav2 perf
source ~/.bashrc
```

### Step 1.2 — Install CycloneDDS (recommended for Nav2)
```bash
sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp
```

### Step 1.3 — Source everything (add to .bashrc if not done)
```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
```

---

## PHASE 2 — Run Gazebo Simulation

### Step 2.1 — Launch TurtleBot3 world in Gazebo Harmonic
```bash
# Terminal 1
export TURTLEBOT3_MODEL=waffle
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py
```

> This spawns TurtleBot3 Waffle in a pre-built obstacle world with:
> - LiDAR (360° scan)
> - RGB-D camera
> - IMU
> - Differential drive odometry

### Step 2.2 — Verify topics are publishing
```bash
# Terminal 2
ros2 topic list | grep -E 'scan|odom|camera|imu'
```

Expected:
```
/scan
/odom
/camera/image_raw
/camera/camera_info
/imu
```

---

## PHASE 3A — SLAM with SLAM Toolbox (2D LiDAR SLAM)

> **Best for:** 2D maps, fast, low CPU, good for navigation

### Step 3A.1 — Launch SLAM Toolbox
```bash
# Terminal 3
ros2 launch slam_toolbox online_async_launch.py \
    slam_params_file:=/opt/ros/jazzy/share/slam_toolbox/config/mapper_params_online_async.yaml \
    use_sim_time:=true
```

### Step 3A.2 — Launch RViz2 to watch mapping
```bash
# Terminal 4
ros2 launch nav2_bringup rviz_launch.py
```

### Step 3A.3 — Drive robot to build map (teleoperation)
```bash
# Terminal 5
ros2 run turtlebot3_teleop teleop_keyboard
```

### Step 3A.4 — Save the map
```bash
# When map looks good:
ros2 run nav2_map_server map_saver_cli -f ~/maps/my_map
```

---

## PHASE 3B — SLAM with RTAB-Map (3D RGB-D + LiDAR SLAM)

> **Best for:** 3D maps, loop closure, RGB-D cameras, rich for paper comparison

### Step 3B.1 — Launch RTAB-Map TurtleBot3 demo (built-in launch)
```bash
# Terminal 3
ros2 launch rtabmap_demos turtlebot3_sim_fusioncore_icp_demo.launch.py \
    use_sim_time:=true
```

### Step 3B.2 — Or launch manually with remaps
```bash
ros2 launch rtabmap_launch rtabmap.launch.py \
    use_sim_time:=true \
    rgb_topic:=/camera/image_raw \
    depth_topic:=/camera/depth/image_raw \
    camera_info_topic:=/camera/camera_info \
    scan_topic:=/scan \
    frame_id:=base_footprint
```

### Step 3B.3 — Re-localize on saved map (localization mode)
```bash
ros2 launch rtabmap_demos turtlebot3_sim_fusioncore_icp_demo.launch.py \
    localization:=true \
    use_sim_time:=true
```

---

## PHASE 3C — SLAM with Cartographer (for paper comparison)

```bash
ros2 launch turtlebot3_cartographer cartographer.launch.py \
    use_sim_time:=true
```

---

## PHASE 4 — Navigation (Nav2) — Path Planning + Obstacle Avoidance

> Run AFTER you have a saved map from Phase 3

### Step 4.1 — Launch Nav2 full stack
```bash
# Terminal 6
ros2 launch nav2_bringup bringup_launch.py \
    use_sim_time:=true \
    map:=$HOME/maps/my_map.yaml \
    params_file:=/opt/ros/jazzy/share/nav2_bringup/params/nav2_params.yaml
```

### Step 4.2 — Set initial pose in RViz2
1. Open RViz2
2. Click **"2D Pose Estimate"**
3. Click on the robot's position in the map

### Step 4.3 — Send navigation goals
**Option A — RViz2 (manual)**
- Click **"Nav2 Goal"** → click anywhere on map

**Option B — Command line**
```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
    "pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.5, z: 0.0}, orientation: {w: 1.0}}}"
```

**Option C — Python script (for automated testing)**
```python
from nav2_simple_commander.robot_navigator import BasicNavigator
from geometry_msgs.msg import PoseStamped

navigator = BasicNavigator()
goal = PoseStamped()
goal.header.frame_id = 'map'
goal.pose.position.x = 1.0
goal.pose.position.y = 0.5
goal.pose.orientation.w = 1.0

navigator.goToPose(goal)
while not navigator.isTaskComplete():
    pass
```

### Step 4.4 — Change path planner (for paper comparison)

Edit `nav2_params.yaml` → `planner_server` section:

| Planner | YAML value | Paper notes |
|---------|-----------|-------------|
| NavFn (Dijkstra/A*) | `plugin: "nav2_navfn_planner/NavfnPlanner"` | Classic baseline |
| SMAC Hybrid A* | `plugin: "nav2_smac_planner/SmacPlannerHybrid"` | Best for paper |
| Theta* | `plugin: "nav2_theta_star_planner/ThetaStarPlanner"` | Smooth paths |

### Step 4.5 — Change local planner

| Planner | YAML value |
|---------|-----------|
| DWB (DWA) | `plugin: "dwb_core::DWBLocalPlanner"` |
| MPPI | `plugin: "nav2_mppi_controller::MPPIController"` |

---

## PHASE 5 — Data Recording for Metrics

### Step 5.1 — Record all relevant topics
```bash
ros2 bag record \
    /odom \
    /scan \
    /map \
    /tf \
    /tf_static \
    /camera/image_raw \
    /diagnostics \
    /navigate_to_pose/_action/status \
    -o ~/bags/experiment_01
```

### Step 5.2 — Record ground truth (Gazebo pose)
```bash
# Ground truth from simulator
ros2 bag record /model/turtlebot3_waffle/pose -o ~/bags/ground_truth_01
```

---

## PHASE 6 — Metrics Extraction (Q1 Paper)

### Metric 1 — Trajectory Error (ATE / RPE)
```bash
# Convert bag to TUM format
evo_traj bag2 ~/bags/experiment_01 /odom --save_as_tum

# Compute ATE vs ground truth
evo_ape tum ground_truth.tum odom_estimate.tum -va --plot

# Compute RPE
evo_rpe tum ground_truth.tum odom_estimate.tum -va --plot
```

### Metric 2 — CPU / RAM during SLAM
```bash
# Run this during your experiment
python3 << 'EOF'
import psutil, time, csv

with open('/tmp/cpu_ram_log.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['time', 'cpu_%', 'ram_mb'])
    for _ in range(300):  # 5 min at 1Hz
        writer.writerow([time.time(), psutil.cpu_percent(), psutil.virtual_memory().used / 1e6])
        time.sleep(1)
EOF
```

### Metric 3 — Path Length
```bash
# Python script to compute path length from odom
python3 << 'EOF'
from rosbags.rosbag2 import Reader
from rosbags.typesys import Stores, get_typestore
import math

typestore = get_typestore(Stores.ROS2_JAZZY)
total_dist = 0
prev = None

with Reader('/home/bmscecse/bags/experiment_01') as reader:
    for conn, ts, rawdata in reader.messages(connections=[c for c in reader.connections if c.topic == '/odom']):
        msg = typestore.deserialize_cdr(rawdata, conn.msgtype)
        x, y = msg.pose.pose.position.x, msg.pose.pose.position.y
        if prev:
            total_dist += math.hypot(x-prev[0], y-prev[1])
        prev = (x, y)

print(f"Total path length: {total_dist:.3f} m")
EOF
```

### Metric 4 — Navigation Success Rate
```bash
# Count successful goals vs total goals from nav action status
ros2 topic echo /navigate_to_pose/_action/status
# Status 4 = SUCCEEDED, 6 = ABORTED, 5 = CANCELED
```

### Metric 5 — Map Quality (vs Ground Truth)
```bash
# Compare occupancy grids with SSIM
python3 << 'EOF'
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

gt_map = cv2.imread('ground_truth_map.pgm', 0)
slam_map = cv2.imread('slam_toolbox_map.pgm', 0)

# Resize to same shape if needed
slam_map = cv2.resize(slam_map, gt_map.shape[::-1])

score, _ = ssim(gt_map, slam_map, full=True)
print(f"Map SSIM score: {score:.4f}")  # 1.0 = perfect
EOF
```

---

## PHASE 7 — Comparison Table (Paper Structure)

Run experiments with each combination and fill this table:

| Config | SLAM | Planner | ATE (m) | RPE (m) | Path Len (m) | CPU % | RAM (MB) | Success Rate |
|--------|------|---------|---------|---------|-------------|-------|----------|-------------|
| 1 | SLAM Toolbox | NavFn (A*) | | | | | | |
| 2 | SLAM Toolbox | SMAC Hybrid A* | | | | | | |
| 3 | SLAM Toolbox | MPPI | | | | | | |
| 4 | RTAB-Map | NavFn (A*) | | | | | | |
| 5 | RTAB-Map | SMAC Hybrid A* | | | | | | |
| 6 | RTAB-Map | MPPI | | | | | | |
| 7 | Cartographer | SMAC Hybrid A* | | | | | | |

---

## ⚠️ Key Tips for Jazzy + Gazebo Harmonic

1. **Always use `use_sim_time:=true`** — Gazebo publishes `/clock`, not wall time
2. **Use CycloneDDS** — better Nav2 performance than FastRTPS
3. **LiDAR min_range** — set to `> 0.2m` or robot detects itself as obstacle
4. **If map drifts** — use `2D Pose Estimate` in RViz to re-localize
5. **RTAB-Map DB** — saved at `~/.ros/rtabmap.db` by default; back it up
6. **evo bags** — use `--ros2` flag: `evo_traj bag2 <bagdir> /odom --ros2`

---

## 📋 Quick Command Cheatsheet

```bash
# 1. Start Gazebo
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py

# 2A. SLAM Toolbox
ros2 launch slam_toolbox online_async_launch.py use_sim_time:=true

# 2B. RTAB-Map
ros2 launch rtabmap_demos turtlebot3_sim_fusioncore_icp_demo.launch.py use_sim_time:=true

# 3. Teleoperate to build map
ros2 run turtlebot3_teleop teleop_keyboard

# 4. Save map
ros2 run nav2_map_server map_saver_cli -f ~/maps/my_map

# 5. Launch Nav2
ros2 launch nav2_bringup bringup_launch.py use_sim_time:=true map:=~/maps/my_map.yaml

# 6. Record bag
ros2 bag record /odom /scan /map /tf /tf_static -o ~/bags/exp01

# 7. Compute ATE
evo_ape tum ground_truth.tum estimated.tum -va --plot
```
