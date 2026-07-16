# Swachh Boudhik Yantra - User Documentation Guide

Welcome to the Swachh Boudhik Yantra software stack! This guide explains how to use the automated scripts to run the robot, control it in simulation, and export maps.

---

## 1. Running the SLAM Mapping System

To launch the complete mapping stack (Gazebo simulation, robot controllers, RTAB-Map SLAM, and RViz), run:

```bash
cd ~/Swachh_Boudhik_Yantra
./run_mapping.sh
```

**What it does:**
* Launches Gazebo Harmonic with the apartment world.
* Spawns the vacuum robot with its RealSense depth camera and differential drive.
* Starts `ros2_control` diff-drive and joint state broadcasters.
* Launches RTAB-Map in mapping mode to build a 2D occupancy grid and a 3D point cloud map.
* Opens RViz2 pre-configured to visualize the robot model, camera streams, and the live map.
* Opens a keyboard teleop terminal window to let you drive the robot manually.

---

## 2. Controlling the Robot (Teleop)

When you run `./run_mapping.sh`, a new terminal pane or window runs the teleop node. 

**How to use:**
1. **Focus the teleop window** by clicking inside it.
2. Use the following keys to drive:
   * **`U` / `I` / `O`**: Forward Left / Forward / Forward Right
   * **`J` / `K` / `L`**: Rotate Left / Stop / Rotate Right
   * **`M` / `,` / `.`**: Reverse Left / Reverse / Reverse Right
3. The robot will move in Gazebo and RViz, scanning the room to build the map.

*Note: The `cmd_vel_relay.py` script automatically wraps your keystrokes into timestamped commands so the robot's hardware controllers receive them reliably.*

---

## 3. Saving the Map

Once you have driven the robot around and the map in RViz looks complete, you need to save it.

Open a *new* terminal and run:

```bash
cd ~/Swachh_Boudhik_Yantra
./save_map.sh
```

**What it does:**
* Uses the `nav2_map_server` to request the map from RTAB-Map.
* Saves the resulting map image (`map.pgm`) and metadata configuration (`map.yaml`).
* Moves these files to `~/maps/stage4/` so they are safely stored and organized for the next navigation phase.

---

## 4. Viewing the Saved Map

To quickly inspect the map image you just saved without having to navigate through folders:

```bash
cd ~/Swachh_Boudhik_Yantra
./view_map.sh
```

**What it does:**
* Checks `~/maps/stage4/` for the most recently saved `map.pgm`.
* Opens the PGM image file using the standard Linux image viewer (`eog`), allowing you to easily verify the scanned walls and obstacles.

---

## 5. Troubleshooting & Tips

* **Missing Obstacles:** The RealSense depth sensor relies on features within 4 meters. If an obstacle doesn't appear in the map, drive the robot closer to it.
* **Map Drift:** Avoid aggressive spinning. Smooth, steady movements help RTAB-Map stitch the depth scans together more accurately via loop closures.
* **Next Steps:** The exported map will be used in Stage 5 for Autonomous Navigation (Nav2), where the robot will plan its own paths around these mapped obstacles.
