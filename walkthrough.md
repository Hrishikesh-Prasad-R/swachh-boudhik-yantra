# Stage 4 Walkthrough — SLAM Mapping & Map Export
### Swachh Boudhik Yantra | ROS 2 Jazzy | Gazebo Harmonic | RTAB-Map

---

## 1. Summary of Stage 4 SLAM Mapping ✅
In this stage, we resolved several critical dependencies and middleware errors to bring up a fully integrated manual SLAM mapping workspace. The robot was successfully driven in Gazebo Harmonic, and a high-resolution 2D occupancy grid map was exported for path planning.

---

## 2. Technical Milestones Completed

### A. C++ shared library pointer segfault resolved
Patched system configuration target redirects for `tinyxml2` inside the compilation workspace to prevent node initialization crashes on Ubuntu 26.04.

### B. CycloneDDS Middleware integration
Configured CycloneDDS (`rmw_cyclonedds_cpp`) to avoid standard middleware symbol collisions when running simulated D435i depth nodes.

### C. Custom Python command velocity stamp relay (`cmd_vel_relay.py`)
Fitted a lightweight ROS 2 Python node that wraps standard `geometry_msgs/msg/Twist` commands (emitted from keyboard/teleop controllers) with header details and simulation clocks before republishing them as `geometry_msgs/msg/TwistStamped` to the `diff_drive_controller`.

### D. Automated utility scripts
* **[run_mapping.sh](file:///home/bmscecse/Swachh_Boudhik_Yantra/run_mapping.sh):** Starts simulation, SLAM, RViz, and keyboard teleop.
* **[save_map.sh](file:///home/bmscecse/Swachh_Boudhik_Yantra/save_map.sh):** Automatically saves map configurations to the proper home subfolder.
* **[view_map.sh](file:///home/bmscecse/Swachh_Boudhik_Yantra/view_map.sh):** Opens the latest PGM map image in the system viewer.

---

## 3. Saved Occupancy Map
The resulting map files are stored successfully inside the home maps folder:
* **Map Configuration:** [map.yaml](file:///home/bmscecse/maps/stage4/map.yaml)
* **Map Image:** [map.pgm](file:///home/bmscecse/maps/stage4/map.pgm)

```yaml
image: map.pgm
mode: trinary
resolution: 0.050
origin: [-3.474, -3.809, 0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.196
```

---

## 4. Troubleshooting Map Obstacles
* **Resolution/Range:** The RealSense depth sensor relies on features within 4m of the camera link. Driving directly next to room obstacles is necessary to scan them into the map.
* **Ray Tracing:** Avoid quick spinning to prevent map drift or clearing scans before loop closures occur.
