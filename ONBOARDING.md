# Swachh Boudhik Yantra — Onboarding Manual
### Quick-start guide for running simulations

> **All commands are run from the project root:**
> ```bash
> cd ~/Swachh_Boudhik_Yantra
> ```

---

## Table of Contents

1. [Prerequisites — Before Running Anything](#1-prerequisites)
2. [Build the Workspace](#2-build-the-workspace)
3. [Mode 1 — Manual Teleoperation + Live Mapping](#3-mode-1--manual-teleoperation--live-mapping)
4. [Mode 2 — Autonomous Frontier Exploration](#4-mode-2--autonomous-frontier-exploration)
5. [Mode 3 — Autonomous Point-to-Point Navigation](#5-mode-3--autonomous-point-to-point-navigation)
6. [Saving and Viewing Maps](#6-saving-and-viewing-maps)
7. [Stopping Everything](#7-stopping-everything)
8. [Monitoring Commands — What Is the Robot Doing?](#8-monitoring-commands)
9. [Utility and Validation Scripts](#9-utility-and-validation-scripts)
10. [Environment Reference](#10-environment-reference)
11. [Common Problems and Fixes](#11-common-problems-and-fixes)
12. [Workflow Cheatsheet](#12-workflow-cheatsheet)

---

## 1. Prerequisites

Check these once before your first run. You should not need to redo them.

```bash
# Verify ROS 2 CLI is working (ros2 has no --version flag — use this instead)
ros2 topic list

# Verify our packages are installed in the workspace
ros2 pkg list | grep vacuum

# Verify Gazebo is installed
gz sim --version

# Verify workspace is built (install/ directory must exist)
ls ~/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/install/
```

> **Note:** `ros2 --version` does **not** exist in ROS 2 Jazzy — it will error. Use `ros2 topic list` to confirm the CLI is working.

If `ros2 topic list` fails or says command not found, source the environment first:
```bash
source /opt/ros/jazzy/setup.bash
```

> **Note:** The scripts source all environments automatically. You do not need to manually `source` anything before running `./start.sh` or `./run_mapping.sh`.

---

## 2. Build the Workspace

Only needed after changing source code. Skip if just running.

```bash
cd ~/Swachh_Boudhik_Yantra/Simulation/vacuum_ws

source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash      # RTABMap

colcon build --symlink-install
```

**What this does:** Compiles all 10 ROS 2 packages (`vacuum_description`, `vacuum_controller`, `vacuum_gazebo`, `vacuum_slam`, `vacuum_nav2`, `vacuum_localization`, `vacuum_exploration`, `vacuum_bringup`, `vacuum_interfaces`, `vacuum_utils`) and links them into `install/`.

Build time: ~2–4 minutes on first build, seconds on incremental.

---

## 3. Mode 1 — Manual Teleoperation + Live Mapping

**Use this when:** You want to drive the robot yourself and watch it build a map in real time.

### Step 1 — Launch everything

```bash
./start.sh
```

or equivalently:

```bash
./run_mapping.sh
```

**What launches:**
| Window / Process | What it does |
|---|---|
| **Gazebo Harmonic** | 3D physics simulation of the apartment with the robot inside |
| **RTABMap SLAM** | Builds a 2D + 3D map using the camera and wheel odometry |
| **RViz2** | Shows the live map, robot position, camera feed, TF tree |
| **rtabmap_viz** | 3D point cloud viewer + loop closure graph |
| **Steering GUI** | Arrow-key interface to drive the robot |

Startup takes **~15–20 seconds**. Wait until Gazebo and RViz2 windows appear.

### Step 2 — Drive the robot

Focus the **Steering GUI** window, then:

| Key | Action |
|---|---|
| `↑` Arrow | Move forward |
| `↓` Arrow | Move backward |
| `←` Arrow | Turn left |
| `→` Arrow | Turn right |
| `Space` | Stop |

Drive around the whole apartment so the map fills in completely.

### Step 3 — Save the map

While the simulation is still running:

```bash
./save_map.sh
```

Saves to: `~/maps/stage4/map.pgm` + `map.yaml`

### Step 4 — View the saved map

```bash
./view_map.sh
```

Opens the `.pgm` file in your desktop image viewer. No ROS needed.

### Step 5 — Stop

```bash
./stop.sh
```

---

## 4. Mode 2 — Autonomous Frontier Exploration

**Use this when:** You want the robot to explore and map the environment completely on its own — no driving required.

> **Status:** Code fully written. End-to-end runtime validation pending.

### Launch

```bash
./start.sh explore
```

With a specific environment:

```bash
./start.sh explore apartment
./start.sh explore office
./start.sh explore corridor
```

**What launches:**
| Component | What it does |
|---|---|
| **Gazebo Harmonic** | Simulation environment |
| **RTABMap SLAM** | Builds map in real time from camera + odometry |
| **Nav2 stack** | Path planner + controller that physically moves the robot |
| **FrontierDetector** | Scans the map every 0.5 s, finds edges of unknown space |
| **ExplorationManager** | Picks the best frontier, sends it as a Nav2 goal, monitors result |
| **FrontierVisualizer** | Shows frontier candidates as green spheres in RViz2 |

**The robot drives itself.** Do not touch the keyboard.

### Monitor exploration progress

```bash
ros2 topic echo /exploration/status
```

Output example:
```json
{
  "state": "NAVIGATING",
  "frontier_id": 3,
  "coverage_pct": 42.7,
  "goals_completed": 5,
  "goals_failed": 1,
  "frontiers_remaining": 8,
  "blacklisted_count": 1,
  "elapsed_sec": 134.2
}
```

### Save map when exploration finishes

```bash
./save_map.sh apartment
```

Saves to: `~/maps/stage5/apartment.pgm` + `apartment.yaml`

### Stop

```bash
./stop.sh
```

> **Important:** `./stop.sh` also **clears RTABMap's memory database** (`~/.ros/rtabmap.db`). Save the map before stopping if you want to keep it.

---

## 5. Mode 3 — Autonomous Point-to-Point Navigation

**Use this when:** You already have a saved map and you want the robot to navigate to click-to-goal points by itself using AMCL localization.

> **Status:** Configuration complete. End-to-end runtime validation pending.

### Prerequisite: you must have a saved map

```bash
ls ~/maps/stage5/
# Should show: apartment.pgm  apartment.yaml  (or office.*, corridor.*, etc.)
```

If the map is missing, run Mode 2 first (`./start.sh explore apartment`), then `./save_map.sh apartment`.

### Launch

```bash
./start.sh navigate apartment
```

**What launches:**
| Component | What it does |
|---|---|
| **Gazebo Harmonic** | Simulation (robot starts at origin) |
| **Map Server** | Loads `~/maps/stage5/apartment.yaml` and publishes `/map` |
| **AMCL** | Particle filter localizer — figures out where the robot is on the map |
| **Nav2 Planner** | Plans obstacle-free paths using Dijkstra |
| **Nav2 Controller** | Drives the robot along the planned path |
| **Behavior Tree** | Manages replanning, recovery (spin/backup) on failure |
| **RViz2** | Full navigation visualization |

### Workflow inside RViz2

```
1. Wait ~30 seconds for all nodes to start

2. Click "2D Pose Estimate" (top toolbar)
   → Click on the map where the robot is in Gazebo
   → Drag to set the orientation (facing direction)
   → Watch a green particle cloud appear — that is AMCL

3. Wait a few seconds for particles to converge

4. Click "Nav2 Goal" (top toolbar)
   → Click anywhere on the free space of the map
   → The robot will plan a path and drive there
```

### Monitor localization quality

```bash
ros2 topic echo /localization/status
```

### Stop

```bash
./stop.sh
```

---

## 6. Saving and Viewing Maps

### Save the current map

```bash
# Default name — goes to ~/maps/stage4/map.pgm
./save_map.sh

# Named map — goes to ~/maps/stage5/<name>.pgm
./save_map.sh apartment
./save_map.sh office
./save_map.sh corridor

# Timestamped (prevents overwrite)
./save_map.sh apartment_$(date +%Y%m%d_%H%M%S)
```

> **Must run while the simulation and SLAM are still running.** Do not call `./stop.sh` before saving.

### View a saved map

```bash
# View default stage4 map
./view_map.sh

# View any saved map directly
eog ~/maps/stage5/apartment.pgm
xdg-open ~/maps/stage5/apartment.pgm
```

### Where maps are stored

```
~/maps/
├── stage4/
│   ├── map.pgm      ← default manual mapping output
│   └── map.yaml
└── stage5/
    ├── apartment.pgm
    ├── apartment.yaml
    ├── office.pgm
    └── office.yaml
```

---

## 7. Stopping Everything

### Normal stop

```bash
./stop.sh
```

Kills all ROS 2, Gazebo, RTABMap, Nav2, and exploration processes, then clears RTABMap's memory database.

### Emergency stop (same thing via start.sh)

```bash
./start.sh stop
```

### Manual nuclear option (if something is stuck)

```bash
pkill -9 -f "ros2" && pkill -9 -f "gz sim" && pkill -9 -f "rtabmap" && pkill -9 -f "rviz2"
```

---

## 8. Monitoring Commands

Run these in a separate terminal while simulation is running.

### Check what ROS 2 nodes are running

```bash
ros2 node list
```

### Check what topics are publishing

```bash
ros2 topic list
```

### Watch the live map update

```bash
ros2 topic hz /map
```

### Watch odometry

```bash
ros2 topic echo /odom
```

### Check camera FPS

```bash
ros2 topic hz /camera/color/image_raw
```

### Check TF tree (should show: map → odom → base_footprint → base_link → camera)

```bash
ros2 run tf2_tools view_frames
# or
ros2 topic echo /tf --once
```

### Watch exploration FSM state

```bash
ros2 topic echo /exploration/status
```

### Watch Nav2 current goal

```bash
ros2 topic echo /exploration/current_goal
```

### Check controller is active

```bash
ros2 control list_controllers
```

Expected output:
```
joint_state_broadcaster[joint_state_broadcaster/JointStateBroadcaster] active
diff_drive_controller[diff_drive_controller/DiffDriveController] active
```

---

## 9. Utility and Validation Scripts

Located in `Simulation/vacuum_ws/src/vacuum_utils/scripts/`. Run with `python3.12`.

### Validate the URDF (robot model)

```bash
bash Simulation/vacuum_ws/src/vacuum_utils/scripts/validate_urdf.sh
```

What it does: Checks for URDF parse errors, lists all links and joints, confirms the model is valid.

### Validate controllers (robot motion system)

```bash
bash Simulation/vacuum_ws/src/vacuum_utils/scripts/validate_controllers.sh
```

What it does: Checks `controller_manager` is running, confirms `diff_drive_controller` and `joint_state_broadcaster` are active.

### Validate camera output

```bash
bash Simulation/vacuum_ws/src/vacuum_utils/scripts/validate_camera.sh
```

What it does: Checks RGB + depth topics are publishing, measures FPS, verifies resolution.

### Check TF tree health

```bash
python3.12 Simulation/vacuum_ws/src/vacuum_utils/scripts/check_tf.py
```

What it does: Prints all TF frames, shows parent-child chain, reports any broken links.

### Benchmark camera performance

```bash
python3.12 Simulation/vacuum_ws/src/vacuum_utils/scripts/benchmark_camera.py
```

What it does: Measures RGB FPS, depth FPS, latency, and drop rate over 30 seconds.

### Benchmark SLAM performance

```bash
python3.12 Simulation/vacuum_ws/src/vacuum_utils/scripts/benchmark_slam.py
```

What it does: Measures keyframe rate, loop closure count, CPU/RAM usage during mapping.

### Drive the robot programmatically (test path)

```bash
python3.12 Simulation/vacuum_ws/src/vacuum_utils/scripts/drive_robot.py
```

What it does: Sends a pre-programmed sequence of velocity commands to drive the robot in a square — useful for testing odometry without manual driving.

### Record a rosbag of a full mapping session

```bash
bash Simulation/vacuum_ws/src/vacuum_utils/scripts/record_stage4.sh
```

What it does: Records all relevant topics (`/map`, `/odom`, `/camera/*`, `/tf`) to a rosbag file for offline analysis.

### Evaluate trajectory accuracy (ATE / RPE)

```bash
python3.12 Simulation/vacuum_ws/src/vacuum_utils/scripts/evaluate_trajectory.py
```

What it does: Computes Absolute Trajectory Error and Relative Pose Error from a recorded trajectory CSV against ground truth.

---

## 10. Environment Reference

### Available simulation worlds

| Name | File | Description |
|---|---|---|
| `apartment` | `apartment.sdf` | Furnished 2-bedroom apartment with furniture and obstacles — **default** |
| `office` | `office.sdf` | Open-plan office space with desks and partitions |
| `corridor` | `corridor.sdf` | Narrow corridor environment — tests tight navigation |
| `empty` | `empty_world.sdf` | Empty flat world — for unit-level testing |

### Use a specific world

```bash
# In any mode, pass the environment name as the second argument
./start.sh explore office
./start.sh navigate corridor
./start.sh explore apartment   # (default if omitted)
```

---

## 11. Common Problems and Fixes

### Problem: Gazebo opens but robot does not appear

**Fix:** The controller manager is still starting. Wait 10–15 seconds.

### Problem: RViz2 shows no map

**Fix:** RTABMap needs a few seconds to start publishing. Check:
```bash
ros2 topic hz /map
# Should show ~1 Hz after ~10 seconds
```

### Problem: Robot does not move when pressing arrow keys

**Fix 1:** Make sure the Steering GUI window is focused (click it).
**Fix 2:** Check the controller is active:
```bash
ros2 control list_controllers
```
**Fix 3:** Check `cmd_vel_relay` is running:
```bash
ros2 node list | grep relay
```

### Problem: `./save_map.sh` outputs an empty or tiny map

**Cause:** You called `./stop.sh` before saving, which wipes RTABMap memory.
**Fix:** Always save the map first, then stop:
```bash
./save_map.sh apartment   # ← first
./stop.sh                 # ← then stop
```

### Problem: `./start.sh navigate apartment` says "Map not found"

**Fix:** You haven't saved the map for that environment yet. Run:
```bash
./start.sh explore apartment
# ... wait for exploration to finish ...
./save_map.sh apartment
./stop.sh
# Now navigate:
./start.sh navigate apartment
```

### Problem: SLAM does not converge / map looks wrong

**Possible cause:** RTAB-Map memory from a previous session is being reused.
**Fix:** Clear the database:
```bash
rm -rf ~/.ros/rtabmap.db*
```
Then relaunch.

### Problem: `ros2` command not found

**Fix:**
```bash
source /opt/ros/jazzy/setup.bash
```

---

## 12. Workflow Cheatsheet

```
┌─────────────────────────────────────────────────────────────────────┐
│  SCENARIO A: Build a map manually                                   │
│                                                                     │
│  1.  ./start.sh                  ← launch sim + SLAM + steering     │
│  2.  Drive the robot around      ← use arrow keys in GUI            │
│  3.  ./save_map.sh               ← save map while sim is running    │
│  4.  ./view_map.sh               ← inspect the saved image          │
│  5.  ./stop.sh                   ← shut everything down             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  SCENARIO B: Let the robot map autonomously                         │
│                                                                     │
│  1.  ./start.sh explore apartment   ← launch autonomous exploration │
│  2.  Watch in RViz2 (no driving)                                    │
│      ros2 topic echo /exploration/status   ← monitor coverage %    │
│  3.  ./save_map.sh apartment        ← save when done               │
│  4.  ./stop.sh                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  SCENARIO C: Navigate with click-to-goal on a saved map             │
│                                                                     │
│  (Requires Scenario A or B to be done first)                        │
│                                                                     │
│  1.  ./start.sh navigate apartment  ← launch sim + Nav2 + AMCL     │
│  2.  In RViz2: "2D Pose Estimate" → click robot's start position    │
│  3.  In RViz2: "Nav2 Goal"        → click any destination           │
│  4.  ./stop.sh                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  EMERGENCY / ALWAYS SAFE                                            │
│                                                                     │
│  ./stop.sh       ← kills everything cleanly                         │
│                                                                     │
│  ⚠ Save your map BEFORE running stop.sh                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

*Project: Swachh Boudhik Yantra · Stack: ROS 2 Jazzy · Gazebo Harmonic · RTABMap · Nav2*
*Last updated: October 2026*
