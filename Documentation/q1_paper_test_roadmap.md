# Exhaustive Test Roadmap — Q1 Robotics Paper
### Gazebo Harmonic | ROS 2 Jazzy | TurtleBot3 + D435i

---

## PHASE 1 — Environment Design
*What world you test in changes everything. Test in multiple.*

### 1.1 World Types to Create
| World | Description | What it tests |
|-------|-------------|---------------|
| **Simple room** | 10×10m, 4 walls, no obstacles | Baseline, bare minimum |
| **Static obstacle room** | Boxes, cylinders scattered | Basic obstacle avoidance |
| **Narrow corridors** | 0.8m-wide passages | Local planner stress test |
| **Dynamic obstacles** | Moving boxes/people (use Gazebo actors) | Real-world robustness |
| **Open space** | Large 20×20m, sparse obstacles | Long-range planning |
| **Complex maze** | Many rooms, dead ends | Loop closure for SLAM |
| **Cluttered room** | High obstacle density | Extreme avoidance test |
| **Download from Fuel** | Office, warehouse, hospital | Realistic benchmarks |

### 1.2 Obstacle Configurations
- **Density:** 5%, 15%, 30%, 50% obstacle fill
- **Shape:** cubes, cylinders, L-shapes, irregular
- **Height:** partial (0.5m), full (2m) — tests depth sensor vs LiDAR
- **Colour/Texture:** matters for RGB-D SLAM

---

## PHASE 2 — SLAM Comparison
*The core contribution of most navigation papers.*

### 2.1 SLAM Algorithms to Compare

| Algorithm | Mode | Sensor |
|-----------|------|--------|
| SLAM Toolbox (async) | 2D LiDAR | /scan |
| SLAM Toolbox (sync) | 2D LiDAR | /scan |
| Cartographer | 2D LiDAR | /scan |
| RTAB-Map (LiDAR mode) | LiDAR only | /scan |
| RTAB-Map (RGB-D mode) | Depth camera | /camera |
| RTAB-Map (LiDAR + RGB-D) | Sensor fusion | /scan + /camera |
| RTAB-Map (IMU fusion) | D435i full | depth + IMU |

### 2.2 SLAM Metrics to Measure

| Metric | Tool | What it tells you |
|--------|------|------------------|
| **ATE (Absolute Trajectory Error)** | `evo_ape` | Global drift |
| **RPE (Relative Pose Error)** | `evo_rpe` | Local accuracy |
| **Map SSIM** | skimage | Map quality vs ground truth |
| **Map IoU** | OpenCV | How much map overlaps GT |
| **Mapping time** | wall clock | Speed |
| **CPU usage during mapping** | psutil | Computational cost |
| **RAM usage** | psutil | Memory footprint |
| **Loop closure count** | rtabmap stats | Consistency |
| **Map completeness %** | pixel count | Coverage |

### 2.3 Test Conditions for SLAM
- Slow teleoperation (0.1 m/s) vs fast (0.3 m/s)
- Full room coverage vs partial coverage
- With and without loop closure
- Known starting pose vs unknown

---

## PHASE 3 — Path Planning Comparison

### 3.1 Global Planners to Compare
| Planner | Nav2 Plugin | Notes |
|---------|------------|-------|
| **NavFn Dijkstra** | `nav2_navfn_planner` | Classic baseline |
| **NavFn A*** | `nav2_navfn_planner` (use_astar: true) | Compare with Dijkstra |
| **SMAC Hybrid A*** | `nav2_smac_planner/SmacPlannerHybrid` | Best for non-holonomic |
| **SMAC 2D A*** | `nav2_smac_planner/SmacPlanner2D` | Grid-based |
| **Theta*** | `nav2_theta_star_planner` | Any-angle paths |

### 3.2 Local Planners to Compare
| Planner | Notes |
|---------|-------|
| **DWB (DWA)** | Classic, stable, well-cited |
| **MPPI** | Modern, model predictive |
| **RPP (Regulated Pure Pursuit)** | Simple, smooth |
| **Graceful Controller** | Smooth curves |

### 3.3 Path Planning Metrics
| Metric | How to measure |
|--------|---------------|
| **Path length (m)** | Integrate /odom |
| **Path smoothness** | Curvature variance |
| **Planning time (ms)** | Timer around planner call |
| **Replanning count** | Count /plan topic publishes |
| **Goal success rate (%)** | Goals reached / total goals |
| **Time to goal (s)** | Start to action complete |
| **Energy proxy (∫v²dt)** | Integrate velocity squared |
| **Deviation from ideal path** | Compare planned vs actual |

### 3.4 Goal Configurations
- **Single goal:** A to B straight line
- **Multi-goal:** Waypoint sequence (5 points)
- **Random goals:** 20 random positions, measure success rate
- **Near-obstacle goals:** Goals close to walls
- **Long-range goals:** Cross the entire map

---

## PHASE 4 — Obstacle Avoidance Testing

### 4.1 Static Obstacle Tests
| Test | Description |
|------|-------------|
| Head-on obstacle | Robot drives directly at wall — must stop/reroute |
| Narrow gap | 0.5m gap between boxes — can robot fit? |
| Dead end | Corridor with no exit — recovery needed |
| Concave obstacle | U-shape — traps simple planners |
| Moving through cluster | Many boxes close together |

### 4.2 Dynamic Obstacle Tests (Gazebo Actors)
| Test | Description |
|------|-------------|
| Person crossing path | Actor walks across robot's path |
| Person following robot | Actor behind robot |
| Multiple actors | 3-5 people moving randomly |
| Sudden appearance | Actor spawns in front of robot |

### 4.3 Recovery Behaviour Tests
| Scenario | Expected Recovery |
|----------|-----------------|
| Robot stuck (no path) | Spin recovery → clear costmap → replan |
| Localization lost | Return to last known pose |
| Goal blocked | Wait, then replan |
| Oscillation detected | Stop, backup, replan |

### 4.4 Avoidance Metrics
| Metric | How |
|--------|-----|
| Min distance to obstacle | /scan min range during run |
| Collision count | Count /bumper events |
| Recovery trigger count | Monitor BT nodes |
| Clearance maintained | Average distance to nearest obstacle |
| Avoidance path extra length | vs straight-line path |

---

## PHASE 5 — Sensor Configuration Tests

### 5.1 D435i vs LiDAR Comparison
| Config | Sensor | SLAM algo | Expected result |
|--------|--------|-----------|----------------|
| LiDAR only | 360° scan | SLAM Toolbox | Best 2D maps |
| Depth only | D435i depth | RTAB-Map | Good 3D, no blind spots at floor level |
| RGB-D only | D435i full | RTAB-Map | Feature-rich SLAM |
| IMU + Depth | D435i full | RTAB-Map | Best odometry |
| LiDAR + Depth | Both | RTAB-Map fusion | Best overall — compare cost vs accuracy |

### 5.2 Sensor Noise Tests
- Add Gaussian noise to /scan (stddev: 0.01, 0.05, 0.1)
- Add noise to camera (test RTAB-Map robustness)
- Test at different lighting (Gazebo light intensity)

### 5.3 Sensor Failure Tests
- Drop /scan topic → Nav2 with depth only
- Drop depth → Nav2 with LiDAR only
- IMU dropout → pure wheel odometry

---

## PHASE 6 — System-Level / Stress Tests

### 6.1 Long-Run Tests
| Test | Duration | What breaks |
|------|----------|-------------|
| Continuous navigation (50 goals) | 30 min | Memory leaks, drift accumulation |
| Map building large area | 20×20m | SLAM scalability |
| Re-localisation after restart | — | Persistence of map |

### 6.2 Computational Load Tests
| Test | What to measure |
|------|----------------|
| Run SLAM + Nav2 simultaneously | CPU/RAM peak |
| Add RViz2 (visualisation overhead) | Frame rate impact |
| Run with rosbag recording | I/O impact |
| Multi-goal with dynamic obstacles | Combined stress |

### 6.3 Localisation Accuracy Tests
| Test | Method |
|------|--------|
| Known start pose | Compare estimated vs Gazebo ground truth |
| Kidnapped robot | Teleport robot, measure recovery time |
| Symmetrical environment | Does SLAM get confused? |
| Re-localisation on saved map | Load old map, boot up, localise |

---

## PHASE 7 — Paper Metrics Master Table

Run every combination, fill this table:

| # | World | SLAM | Global Planner | Local Planner | Sensor | ATE↓ | RPE↓ | Path Len↓ | Time↓ | CPU↓ | RAM↓ | Success↑ |
|---|-------|------|---------------|--------------|--------|------|------|----------|------|------|------|---------|
| 1 | Static | SLAM Toolbox | A* | DWB | LiDAR | | | | | | | |
| 2 | Static | SLAM Toolbox | Hybrid A* | MPPI | LiDAR | | | | | | | |
| 3 | Static | RTAB-Map | Hybrid A* | MPPI | D435i | | | | | | | |
| 4 | Static | RTAB-Map | Hybrid A* | MPPI | LiDAR+D435i | | | | | | | |
| 5 | Maze | SLAM Toolbox | A* | DWB | LiDAR | | | | | | | |
| 6 | Maze | RTAB-Map | Hybrid A* | MPPI | D435i | | | | | | | |
| 7 | Dynamic | SLAM Toolbox | Hybrid A* | MPPI | LiDAR | | | | | | | |
| 8 | Dynamic | RTAB-Map | Hybrid A* | MPPI | LiDAR+D435i | | | | | | | |
| ... | ... | ... | ... | ... | ... | | | | | | | |

**Minimum for Q1 paper:** 15-20 rows. More = stronger.

---

## PHASE 8 — What to Claim in the Paper

Based on what you test, your paper can claim:

| Contribution | What experiments prove it |
|-------------|--------------------------|
| "D435i outperforms LiDAR for 3D SLAM" | Phase 5.1 comparison |
| "MPPI reduces path length vs DWB" | Phase 3 planner comparison |
| "Sensor fusion improves robustness" | Phase 5.1 fusion configs |
| "RTAB-Map achieves lower ATE in complex environments" | Phase 2 + Phase 1.1 |
| "Nav2 with Hybrid A* succeeds in cluttered spaces" | Phase 3 + Phase 1.1 |
| "Recovery behaviours enable operation in dynamic environments" | Phase 4.2 |

---

## Summary — Minimum Exhaustive Test Set

```
Worlds:          3 minimum (simple, maze, dynamic)
SLAM algos:      3 (SLAM Toolbox, Cartographer, RTAB-Map)
Global planners: 3 (A*, Hybrid A*, Theta*)
Local planners:  2 (DWB, MPPI)
Sensor configs:  3 (LiDAR, D435i, Fusion)
Repeat each:     3 runs (for statistical significance → mean ± std)

Total minimum runs = 3 × 3 × 3 × 2 × 3 × 3 = 486 runs
(Use scripting to automate — don't do manually!)
```

> **Pro tip:** Write a Python script that sends goals, records bags, extracts metrics automatically. Otherwise you'll spend 3 months just running experiments.
