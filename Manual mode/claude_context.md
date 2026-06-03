# Swachh Boudhik Yantra: Project Context & Pipeline Architecture

This document provides the complete context of the "Swachh Boudhik Yantra" autonomous cleaning robot project. It details the hardware, the software environment, and the step-by-step vision and navigation pipeline.

---

## 1. Hardware Architecture
*   **Compute Board:** Raspberry Pi 5 (ARM64). *(Note: The project was recently migrated from a crashed NVIDIA Jetson Orin Nano, meaning all GPU-heavy code has been refactored for CPU).*
*   **Vision Sensors:** 2x Logitech C270 Webcams (Stereo Pair).
*   **Other Sensors:** None currently. (No LiDAR, no IMU, no depth cameras like RealSense). All spatial awareness must be derived from the stereo webcams.
*   **Low-Level Control:** Arduino (connected via USB Serial) attached to motor drivers.

## 2. Software & OS Environment
Because Debian 13 is too new for ROS Humble, we use a containerized approach.
*   **Host OS:** Debian 13 (Trixie).
*   **ROS Environment:** **ROS 2 Humble Desktop** running inside an Ubuntu 22.04 container managed by **Distrobox** (container name: `ros-dev`).
*   **Environment Entry:** A script (`./ros.sh`) drops the user directly into the fully sourced ROS 2 terminal.
*   **AI Framework:** **ONNX Runtime (CPU)**. The original YOLOv8s TensorRT (`.engine`) implementation was completely rewritten to use ONNX so it can run efficiently on the RPi 5 CPU.

---

## 3. The Vision & Navigation Pipeline
The robot relies entirely on a custom Python stereo-vision pipeline located in the `vision/` directory. Here is the sequence of how it works:

### A. Stereo Calibration
Because the C270 webcams are independent, they must be mathematically aligned.
1.  **`calib.sh`**: Launches two `usb_cam` ROS 2 nodes and the ROS `camera_calibration` GUI. The user captures 30-40 samples of a physical checkerboard (Standard 8x6 squares, 25mm).
2.  **`save_calib.py`**: Extracts the generated intrinsic and extrinsic matrices (focal length, baseline distance, distortion) from the ROS tarball and saves them as a numpy array: `vision/calib/stereo_calib.npz`.

### B. Runtime Execution (`vision/main.py`)
When the robot is active, `main.py` orchestrates the following loop at roughly 10 FPS:

1.  **Capture (`camera.py`)**: Opens `/dev/video*` streams using OpenCV/V4L2. Captures MJPEG frames and decodes them to BGR.
2.  **Object Detection (`detector.py`)**: 
    *   Loads `models/yolov8s.onnx`.
    *   Runs inference on the Left camera frame.
    *   Filters results using a confidence threshold (>0.50) and a specific whitelist of COCO classes (Bottle, Cup, Remote, Cell phone, etc.).
    *   Returns 2D bounding boxes and centroids (pixel X, Y).
3.  **Depth Mapping (`depth.py`)**:
    *   Loads the `stereo_calib.npz` file to mathematically "rectify" (align) the left and right frames.
    *   Uses OpenCV's `StereoSGBM` (Semi-Global Block Matching) to calculate the "disparity" (pixel shift) between the left and right images.
    *   Uses the calibration baseline and focal length to convert the disparity at the bounding box centroid into a real-world 3D coordinate **(X, Y, Z in meters)**.
4.  **Hardware Execution (`serial_comm.py`)**:
    *   If an object is stable across multiple frames, it formats a command string: `ARM:PICK <X>,<Y>,<Z>`.
    *   Sends this string over `/dev/ttyACM0` or `/dev/ttyUSB0` to the Arduino to trigger the physical collection mechanism.

---

## 4. Human-Machine Interface (HMI)
*   **Directory:** `hmi/`
*   **Tech Stack:** C++ using **GTK4**.
*   **Purpose:** A native desktop application compiled via CMake on the host Debian OS. It provides a graphical dashboard to monitor the robot's status, view logs, and manually override controls.

## 5. Helper Scripts
*   **`ros.sh`**: Instantly enters the Distrobox ROS 2 environment.
*   **`vision/run.sh`**: Sets up camera V4L2 parameters (disabling auto-exposure, fixing brightness) and launches the Python virtual environment for `main.py`.
*   **`stats.sh`**: A custom monitoring script to track RPi 5 CPU usage, RAM, and Temperature (crucial, as the RPi 5 runs hot under ONNX load without an active cooler).

---

## 6. Immediate Next Steps / Roadmap Context
*   **ROS Integration:** The current vision pipeline is a standalone Python script. To utilize ROS navigation (Nav2), `main.py` needs to be converted into a proper ROS 2 Node that publishes `geometry_msgs/Point` or custom messages.
*   **Visual Odometry:** Because there is no LiDAR or IMU, future navigation will require implementing Visual SLAM (e.g., RTAB-Map or ORB-SLAM3) using the calibrated stereo cameras to map the room and track the robot's position.
*   **Motor Control Node:** The Arduino currently handles `ARM:PICK`. We need a ROS 2 node to translate `cmd_vel` (velocity commands) into wheel motor speeds for the Arduino to execute.
