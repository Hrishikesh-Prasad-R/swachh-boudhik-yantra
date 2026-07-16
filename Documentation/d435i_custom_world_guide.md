# D435i + Custom Gazebo World Guide
### ROS 2 Jazzy | Gazebo Harmonic

---

## PART 1 — Replace TurtleBot3 LiDAR + Camera with D435i

### What the D435i gives you
| Sensor | Spec | Use in SLAM |
|--------|------|------------|
| RGB Camera | 1920×1080 @ 30fps, 87° FOV | Visual SLAM, markers |
| Depth Camera (stereo IR) | 0.1m–10m, 87° FOV | Obstacle detection, 3D map |
| IMU (6-DOF) | Accel + Gyro | Odometry fusion |
| ❌ No LiDAR | — | Must use depth as pseudo-LiDAR |

### Step 1 — Install RealSense ROS2 driver (for real hardware later)
```bash
sudo apt install ros-jazzy-realsense2-camera ros-jazzy-realsense2-description
```

### Step 2 — Edit TurtleBot3 URDF to replace sensors

The TurtleBot3 Waffle URDF is at:
```
/opt/ros/jazzy/share/turtlebot3_description/urdf/turtlebot3_waffle.urdf
```

**Copy it to your workspace first** (don't edit the system file):
```bash
mkdir -p ~/robot_ws/src/my_robot/urdf
cp /opt/ros/jazzy/share/turtlebot3_description/urdf/turtlebot3_waffle.urdf \
   ~/robot_ws/src/my_robot/urdf/my_robot.urdf
```

**Remove the default LiDAR sensor block** — find and delete this section:
```xml
<!-- DELETE THIS BLOCK -->
<gazebo reference="base_scan">
  <sensor type="ray" name="lds_lfcd_sensor">
    ...
  </sensor>
</gazebo>
```

**Replace camera block with D435i** — add this:
```xml
<!-- Intel RealSense D435i — RGB-D + IMU -->
<!-- Add this link to your URDF -->
<link name="camera_link">
  <visual>
    <geometry>
      <box size="0.025 0.090 0.025"/>
    </geometry>
    <material name="dark_grey"/>
  </visual>
</link>

<joint name="camera_joint" type="fixed">
  <parent link="base_link"/>
  <child link="camera_link"/>
  <origin xyz="0.073 0 0.084" rpy="0 0 0"/>
</joint>

<!-- Gazebo sensor plugin — RGB-D (simulates depth + color) -->
<gazebo reference="camera_link">
  <sensor name="d435i_rgbd" type="rgbd_camera">
    <update_rate>30</update_rate>
    <topic>camera</topic>
    <camera>
      <horizontal_fov>1.518436</horizontal_fov>  <!-- 87 degrees -->
      <image>
        <width>640</width>
        <height>480</height>
        <format>R8G8B8</format>
      </image>
      <depth_camera>
        <output>depths</output>
      </depth_camera>
      <clip>
        <near>0.1</near>
        <far>10.0</far>
      </clip>
      <noise>
        <type>gaussian</type>
        <mean>0</mean>
        <stddev>0.007</stddev>  <!-- realistic D435i noise -->
      </noise>
    </camera>
  </sensor>
</gazebo>

<!-- IMU sensor (D435i has built-in IMU) -->
<gazebo reference="camera_link">
  <sensor name="d435i_imu" type="imu">
    <update_rate>200</update_rate>
    <topic>camera/imu</topic>
    <imu>
      <angular_velocity>
        <x><noise type="gaussian"><mean>0</mean><stddev>0.0002</stddev></noise></x>
        <y><noise type="gaussian"><mean>0</mean><stddev>0.0002</stddev></noise></y>
        <z><noise type="gaussian"><mean>0</mean><stddev>0.0002</stddev></noise></z>
      </angular_velocity>
      <linear_acceleration>
        <x><noise type="gaussian"><mean>0</mean><stddev>0.017</stddev></noise></x>
        <y><noise type="gaussian"><mean>0</mean><stddev>0.017</stddev></noise></y>
        <z><noise type="gaussian"><mean>0</mean><stddev>0.017</stddev></noise></z>
      </linear_acceleration>
    </imu>
  </sensor>
</gazebo>
```

### Step 3 — Bridge sensor topics to ROS 2

Create `d435i_bridge.launch.py`:
```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            arguments=[
                '/camera/image@sensor_msgs/msg/Image@gz.msgs.Image',
                '/camera/depth_image@sensor_msgs/msg/Image@gz.msgs.Image',
                '/camera/camera_info@sensor_msgs/msg/CameraInfo@gz.msgs.CameraInfo',
                '/camera/points@sensor_msgs/msg/PointCloud2@gz.msgs.PointCloudPacked',
                '/camera/imu@sensor_msgs/msg/Imu@gz.msgs.IMU',
            ],
            output='screen'
        ),
    ])
```

### Step 4 — Use RTAB-Map with D435i (depth-only, no LiDAR)
```bash
ros2 launch rtabmap_launch rtabmap.launch.py \
    rgb_topic:=/camera/image \
    depth_topic:=/camera/depth_image \
    camera_info_topic:=/camera/camera_info \
    imu_topic:=/camera/imu \
    frame_id:=base_footprint \
    use_sim_time:=true \
    approx_sync:=true
```

> **Note:** RTAB-Map works great with D435i depth-only — this is actually its primary use case!

---

## PART 2 — Custom Gazebo Worlds (Rooms + Obstacles)

### Method A — Edit SDF directly (simplest, recommended)

**File format:** `.world` or `.sdf` (both XML)

**TurtleBot3 worlds are at:**
```
/opt/ros/jazzy/share/turtlebot3_gazebo/worlds/
```

**Copy and edit:**
```bash
cp /opt/ros/jazzy/share/turtlebot3_gazebo/worlds/turtlebot3_world.world \
   ~/my_world.world
```

#### Basic room structure (SDF):
```xml
<?xml version="1.0"?>
<sdf version="1.9">
  <world name="my_room">

    <!-- Physics and lighting -->
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <light name="sun" type="directional">
      <pose>0 0 10 0 0 0</pose>
      <diffuse>1 1 1 1</diffuse>
    </light>

    <!-- Floor -->
    <model name="floor">
      <static>true</static>
      <link name="link">
        <collision name="c"><geometry><plane><normal>0 0 1</normal><size>20 20</size></plane></geometry></collision>
        <visual name="v"><geometry><plane><normal>0 0 1</normal><size>20 20</size></plane></geometry></visual>
      </link>
    </model>

    <!-- WALLS — make a room by placing 4 walls -->
    <!-- North wall -->
    <model name="wall_north">
      <static>true</static>
      <pose>0 5 1 0 0 0</pose>  <!-- x y z roll pitch yaw -->
      <link name="link">
        <collision name="c"><geometry><box><size>10 0.2 2</size></box></geometry></collision>
        <visual name="v"><geometry><box><size>10 0.2 2</size></box></geometry></visual>
      </link>
    </model>

    <!-- South wall -->
    <model name="wall_south">
      <static>true</static>
      <pose>0 -5 1 0 0 0</pose>
      <link name="link">
        <collision name="c"><geometry><box><size>10 0.2 2</size></box></geometry></collision>
        <visual name="v"><geometry><box><size>10 0.2 2</size></box></geometry></visual>
      </link>
    </model>

    <!-- East wall -->
    <model name="wall_east">
      <static>true</static>
      <pose>5 0 1 0 0 1.5708</pose>  <!-- rotated 90° -->
      <link name="link">
        <collision name="c"><geometry><box><size>10 0.2 2</size></box></geometry></collision>
        <visual name="v"><geometry><box><size>10 0.2 2</size></box></geometry></visual>
      </link>
    </model>

    <!-- West wall -->
    <model name="wall_west">
      <static>true</static>
      <pose>-5 0 1 0 0 1.5708</pose>
      <link name="link">
        <collision name="c"><geometry><box><size>10 0.2 2</size></box></geometry></collision>
        <visual name="v"><geometry><box><size>10 0.2 2</size></box></geometry></visual>
      </link>
    </model>

    <!-- OBSTACLES — cylinders scattered in room -->
    <model name="obstacle_1">
      <static>true</static>
      <pose>1.5 2.0 0.5 0 0 0</pose>
      <link name="link">
        <collision name="c"><geometry><cylinder><radius>0.2</radius><length>1.0</length></cylinder></geometry></collision>
        <visual name="v"><geometry><cylinder><radius>0.2</radius><length>1.0</length></cylinder></geometry></visual>
      </link>
    </model>

    <model name="obstacle_2">
      <static>true</static>
      <pose>-2.0 1.0 0.5 0 0 0</pose>
      <link name="link">
        <collision name="c"><geometry><box><size>0.5 0.5 1.0</size></box></geometry></collision>
        <visual name="v"><geometry><box><size>0.5 0.5 1.0</size></box></geometry></visual>
      </link>
    </model>

    <!-- Add more obstacles by copying and changing pose -->

  </world>
</sdf>
```

### Launch with your custom world:
```python
# In your launch file:
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os

gz_sim = IncludeLaunchDescription(
    PythonLaunchDescriptionSource(
        os.path.join(get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')
    ),
    launch_arguments={'gz_args': '/home/bmscecse/my_world.world'}.items()
)
```

### Method B — Gazebo GUI (drag and drop)

1. Open Gazebo: `gz sim`
2. Left panel → **Insert** tab
3. Drag **Box**, **Cylinder**, **Sphere** into the scene
4. Resize/position with the transform gizmo
5. **File → Save World As** → saves as `.sdf`

### Method C — Gazebo Fuel (pre-built environments)

Download ready-made environments from the official model store:
- 🌐 **https://fuel.gazebosim.org**
- Search: `office`, `warehouse`, `maze`, `hospital`, `apartment`

```bash
# Include a Fuel model in your world SDF:
<include>
  <uri>https://fuel.gazebosim.org/1.0/OpenRobotics/models/Office</uri>
  <pose>0 0 0 0 0 0</pose>
</include>
```

---

## PART 3 — Where to Learn All of This

### 📺 Best YouTube Channels (free, hands-on)

| Channel | What you get |
|---------|-------------|
| **Articulated Robotics** (Josh Newans) | Best ROS2 + Gazebo Harmonic series. URDF, sensors, Nav2. Start here. |
| **The Construct** | ROS2 tutorials, Nav2, SLAM, professional quality |
| **Robotics Backend** | Concise how-tos for ROS2 topics/services/actions |

> 🔥 **Search:** "Articulated Robotics ROS2 Gazebo" — this series covers everything from URDF to Nav2 in one playlist

### 📖 Official Documentation

| Topic | Link |
|-------|------|
| Gazebo Harmonic SDF worlds | https://gazebosim.org/docs/harmonic/sdf_worlds |
| Gazebo sensors | https://gazebosim.org/docs/harmonic/sensors |
| ros_gz_bridge | https://github.com/gazebosim/ros_gz/tree/ros2/ros_gz_bridge |
| URDF tutorials | https://docs.ros.org/en/jazzy/Tutorials/Intermediate/URDF/URDF-Main.html |
| Nav2 docs | https://docs.nav2.org |
| RTAB-Map tutorials | https://github.com/introlab/rtabmap_ros/wiki |
| RealSense ROS2 | https://github.com/IntelRealSense/realsense-ros |
| Gazebo Fuel models | https://fuel.gazebosim.org |

### 📚 Step-by-Step Learning Order

```
1. URDF basics         → docs.ros.org/en/jazzy/Tutorials/URDF
2. Gazebo Harmonic     → gazebosim.org/docs/harmonic
3. ROS2 + Gazebo       → Articulated Robotics YouTube series
4. Nav2 stack          → docs.nav2.org/getting_started
5. SLAM Toolbox        → github.com/stevemacenski/slam_toolbox
6. RTAB-Map            → github.com/introlab/rtabmap_ros/wiki
7. D435i simulation    → github.com/IntelRealSense/realsense-ros
8. Metrics / paper     → github.com/MichaelGrupp/evo
```

---

## PART 4 — Quick Cheatsheet

```bash
# Open Gazebo with GUI (to drag & drop build world)
gz sim

# Open your custom world
gz sim /home/bmscecse/my_world.world

# Spawn robot into running Gazebo
ros2 run ros_gz_sim create -name turtlebot3 -file my_robot.urdf

# Check what topics D435i bridge is publishing
ros2 topic list | grep camera

# Visualize depth cloud in RViz
rviz2  # add PointCloud2 display → /camera/points

# Start RTAB-Map with depth camera only (no LiDAR needed)
ros2 launch rtabmap_launch rtabmap.launch.py \
    rgb_topic:=/camera/image \
    depth_topic:=/camera/depth_image \
    camera_info_topic:=/camera/camera_info \
    use_sim_time:=true
```
