# Q&A — Map System
### Swachh Boudhik Yantra

---

## Q1. Does the map work? Can you view it?

**Yes. A real map has already been saved and can be viewed.**

### What exists on disk right now

```
~/maps/
└── stage4/
    ├── map.pgm   (6.2 MB — greyscale occupancy image of the apartment)
    └── map.yaml  (7 lines — metadata: resolution, origin, thresholds)
```

### What map.yaml contains

```yaml
image: map.pgm
mode: trinary
resolution: 0.050        # 5 cm per pixel
origin: [-8.328, -37.484, 0]
occupied_thresh: 0.65
free_thresh: 0.196
```

### How to view it — right now, without launching anything

```bash
./view_map.sh
```

This opens `~/maps/stage4/map.pgm` using `xdg-open` (your desktop's default image viewer).
No ROS, no Gazebo, no simulation required.

### How to view it live inside RViz2 (while mapping)

While `./run_mapping.sh` is running, RViz2 automatically subscribes to `/map`
(published by RTABMap) and renders it as a colour-coded occupancy grid in real time.

---

## Q2. Can you overwrite with a new map?

**Yes. Every time you run `./save_map.sh`, it overwrites the previous map at the same path.**

### Default behaviour (no arguments)

```bash
./save_map.sh
```

Saves to → `~/maps/stage4/map.pgm` and `~/maps/stage4/map.yaml`

If these files already exist, `nav2_map_server map_saver_cli` **silently overwrites** them.
There is no prompt, no backup, no version history.

> **Warning:** If you run a new mapping session and then call `./save_map.sh` without
> a name argument, your previous map is **permanently replaced**.

### How to avoid accidental overwrite

Give the map a name:

```bash
./save_map.sh apartment_v2
```

This saves to `~/maps/stage5/apartment_v2.pgm` (a different path, Stage 5 folder).
The Stage 4 default map is untouched.

---

## Q3. Can you independently store a different map for each run?

**Yes. The save script supports named maps out of the box.**

### How it works

The [`save_map.sh`](file:///home/bmscecse/Swachh_Boudhik_Yantra/save_map.sh) script
accepts an optional environment name as the first argument.

| Command | Saves to |
|---|---|
| `./save_map.sh` | `~/maps/stage4/map.pgm` + `.yaml` (default, gets overwritten) |
| `./save_map.sh apartment` | `~/maps/stage5/apartment.pgm` + `.yaml` |
| `./save_map.sh office` | `~/maps/stage5/office.pgm` + `.yaml` |
| `./save_map.sh corridor` | `~/maps/stage5/corridor.pgm` + `.yaml` |
| `./save_map.sh run1` | `~/maps/stage5/run1.pgm` + `.yaml` |
| `./save_map.sh run2` | `~/maps/stage5/run2.pgm` + `.yaml` |

Each named map is an independent file. They do not overwrite each other.

### How to use a specific saved map in Nav2

After saving, the script itself tells you the next step:

```bash
./start.sh navigate apartment
```

The Nav2 launch files pick up the named map via a `map_path` launch argument —
the `yaml_filename` parameter in `map_server_params.yaml` is intentionally left
blank and filled at runtime, so no YAML file needs to be edited between runs.

### What is currently missing (per-run timestamped storage)

There is no automatic timestamping. If you run `./save_map.sh apartment` twice,
the second run overwrites the first.

To keep every run independently, either:

1. Add a timestamp yourself:
   ```bash
   ./save_map.sh apartment_$(date +%Y%m%d_%H%M%S)
   ```

2. Or copy the file after saving:
   ```bash
   cp ~/maps/stage5/apartment.pgm ~/maps/stage5/apartment_backup.pgm
   ```

---

## Summary Table

| Question | Answer |
|---|---|
| Does the map exist and can you see it? | ✅ Yes — 6.2 MB `.pgm` saved, `./view_map.sh` opens it |
| Can you view the map live in RViz2? | ✅ Yes — subscribe to `/map` topic while SLAM is running |
| Does `./save_map.sh` overwrite old maps? | ✅ Yes — same path = silent overwrite, no prompt |
| Can you save maps with different names? | ✅ Yes — `./save_map.sh <name>` saves to a unique file |
| Are maps saved per-run automatically? | ❌ No — you must provide a unique name manually each time |

---

## Q4. Does autonomous movement exist? To what extent? What algorithm does it use?

**Yes — autonomous movement exists at two distinct levels. The code is fully written and structured. It has NOT yet been validated end-to-end in a running simulation.**

---

### Level 1 — Point-to-Point Autonomous Navigation (Nav2)

**What it does:** You click a goal point on the RViz2 map. The robot plans a path and drives there by itself, avoiding obstacles.

**Status:** Configuration complete. Not yet run end-to-end.

**How it works (algorithm stack):**

| Layer | Component | Algorithm |
|---|---|---|
| Path planner | Nav2 `planner_server` | `GridBased` (NavFn / Dijkstra by default) |
| Path follower | Nav2 `controller_server` | `FollowPath` (DWB / MPPI configurable) |
| Localization | AMCL | Particle Filter (Monte Carlo) on saved map |
| Costmaps | Local + Global costmap | Inflation layer around obstacles |
| Replanning | Behavior tree `RateController` | Recomputes path at **1 Hz** while driving |

**Recovery sequence when stuck** (`navigate.xml`):
1. Clear local + global costmaps
2. Spin 90° in place
3. Wait 5 seconds for sensor update
4. Retry up to **6 times total** before reporting failure

---

### Level 2 — Autonomous Frontier Exploration (vacuum_exploration)

**What it does:** The robot explores an unknown environment completely by itself — no human driving, no pre-built map. It finds unvisited areas, navigates to them, builds the map as it goes, and stops when coverage is complete.

**Status:** All nodes fully written. Not yet run end-to-end (depends on Nav2 being validated first).

---

### The Exploration Algorithm: Wavefront Frontier Detection (WFD)

**File:** [`frontier_detector.py`](file:///home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/src/vacuum_exploration/vacuum_exploration/frontier_detector.py)

A frontier is a **free cell that has at least one unknown neighbour** — the edge between what the robot knows and what it hasn't seen yet.

**Steps (run at 2 Hz):**

```
1. Scan every free cell (value = 0) in the occupancy grid
2. Check its 4 neighbours (up/down/left/right)
3. If any neighbour is unknown (value = -1) → mark as frontier cell
4. BFS-cluster nearby frontier cells within 0.5 m radius
5. Discard clusters smaller than 5 cells (noise filter)
6. Compute world-frame centroid of each surviving cluster
7. Publish centroids as PoseArray → picked up by ExplorationManager
```

**Result:** A list of "frontier centroids" — candidate goal points in the real world.

---

### Goal Selection Algorithm: Utility Scoring

**File:** [`goal_selector.py`](file:///home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/src/vacuum_exploration/vacuum_exploration/goal_selector.py)

Once frontiers are detected, the robot must pick the **best** one to visit next.
It uses a **weighted utility function**:

```
score(frontier) = w_info  × log(1 + cluster_size)       ← bigger frontier = more info gain
                - w_dist  × distance(robot, frontier)    ← closer frontier = cheaper to reach
                - w_obs   × obstacle_proximity_penalty   ← penalise frontiers near walls
```

Default weights: `w_info = 1.0`, `w_dist = 1.5`, `w_obs = 0.8`

The frontier with the **highest score** wins and becomes the next Nav2 goal.

---

### Orchestration: Finite State Machine (FSM)

**File:** [`exploration_manager.py`](file:///home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/src/vacuum_exploration/vacuum_exploration/exploration_manager.py)

The FSM runs at **10 Hz** and manages the full exploration lifecycle:

```
IDLE
  ↓
WAITING_FOR_MAP     ← waits until RTABMap publishes a map with free cells
  ↓
DETECT_FRONTIERS    ← checks latest WFD output
  ↓
SELECT_GOAL         ← runs scoring, picks best non-blacklisted frontier
  ↓
SEND_GOAL           ← sends NavigateToPose action to Nav2
  ↓
NAVIGATING          ← waits for result, monitors timeout + oscillation
  ↓ success              ↓ failure / timeout / stuck
GOAL_REACHED        RECOVERING → blacklist frontier → back to DETECT
  ↓
DETECT_FRONTIERS    ← loop
  ↓ (when all done)
FINISHED
```

**Recovery/blacklisting logic:**
- If Nav2 aborts → frontier blacklisted for **60 seconds**
- If goal takes > **30 seconds** → timeout, frontier blacklisted
- If robot doesn't move for > **15 seconds** while navigating → oscillation detected, frontier blacklisted
- After 5 consecutive failures → frontier size filter is **tightened** (ignores tiny frontiers)
- Blacklisted frontiers automatically **expire and become eligible again** after 60 s

**Exploration done when all 3 conditions are true simultaneously:**
1. No new frontiers detected for **5 consecutive cycles**
2. Map free-cell count has not grown by > 10 cells in the last **15 seconds**
3. Robot velocity < **0.02 m/s** (stationary)

---

### Exploration Behavior Tree (`explore.xml`)

For each frontier nav goal, the BT adds an extra recovery step vs. normal navigation:
- **BackUp 0.15 m** at 0.08 m/s — specifically for escaping dead-end corners that happen at exploration frontiers near walls

Recovery order: Clear costmaps → Spin 90° → Back up 0.15 m → Wait 3 s → Retry

---

### Summary

| Capability | Algorithm | Code Written | End-to-End Tested |
|---|---|---|---|
| Manual teleop | Arrow keys → cmd_vel | ✅ | ✅ |
| Point-to-point nav | Dijkstra path + DWB follow + AMCL | ✅ | 🔶 not yet |
| Autonomous exploration | WFD + Utility scoring + FSM | ✅ | 🔶 not yet |
| Recovery behaviors | Spin, BackUp, Clear costmap (BT.CPP) | ✅ | 🔶 not yet |
| Exploration completion | Triple-condition termination | ✅ | 🔶 not yet |

---

*Last updated: October 2026*
