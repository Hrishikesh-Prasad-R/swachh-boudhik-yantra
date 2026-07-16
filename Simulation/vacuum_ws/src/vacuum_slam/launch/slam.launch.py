#!/usr/bin/env python3
"""
slam.launch.py  —  Stage 4A: Manual RTAB-Map Mapping
──────────────────────────────────────────────────────
Starts RTAB-Map in RGB-D + wheel odometry mode for manual mapping.

Prerequisites (must be running BEFORE this launch):
  ros2 launch vacuum_bringup sim.launch.py

This launch starts:
  1. rtabmap_ros/rtabmap     — SLAM engine (builds map from camera + odom)
  2. RViz2                   — visualises map, pointcloud, trajectory (optional)

Topic remappings (D435i topics → RTAB-Map expected inputs):
  /camera/color/image_raw      → rgb/image
  /camera/depth/image_rect_raw → depth/image
  /camera/color/camera_info    → rgb/camera_info
  /odom                        → odom

RTAB-Map outputs:
  /rtabmap/map                 → nav_msgs/OccupancyGrid  (2D map for Nav2)
  /rtabmap/cloud_map           → sensor_msgs/PointCloud2 (3D map)
  /rtabmap/odom                → nav_msgs/Odometry       (refined odometry)
  /rtabmap/info                → rtabmap_msgs/Info       (keyframes, loops)
  /rtabmap/mapData             → rtabmap_msgs/MapData    (full graph)

Map is saved to ~/.ros/rtabmap.db automatically.
Run map_saver.launch.py to export as PNG/YAML for Nav2.

Launch arguments:
  use_sim_time    [true]    — use Gazebo clock
  use_rviz        [true]    — launch RViz2 with SLAM config
  environment     [room]    — label for rosbag subfolder naming
  database_path   [~/.ros/rtabmap.db]  — RTAB-Map database file
  delete_db       [true]    — delete old DB on start (fresh map)
  localization    [false]   — run in localisation mode (no new nodes)

Usage:
  # Fresh mapping run (default):
  ros2 launch vacuum_slam slam.launch.py

  # Map an office environment:
  ros2 launch vacuum_slam slam.launch.py environment:=office

  # Re-localise against existing map (no new keyframes):
  ros2 launch vacuum_slam slam.launch.py localization:=true delete_db:=false

  # Without RViz (for CI or remote):
  ros2 launch vacuum_slam slam.launch.py use_rviz:=false
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import (
    LaunchConfiguration, PythonExpression
)
from launch_ros.actions import Node


def generate_launch_description():

    pkg_slam   = get_package_share_directory('vacuum_slam')
    slam_rviz  = os.path.join(pkg_slam, 'config', 'slam_rviz.rviz')
    rtabmap_yaml = os.path.join(pkg_slam, 'config', 'rtabmap.yaml')

    # ── Arguments ─────────────────────────────────────────────────────────
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='Use Gazebo simulation clock')

    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz', default_value='true',
        description='Launch RViz2 with SLAM configuration')

    declare_environment = DeclareLaunchArgument(
        'environment', default_value='room',
        choices=['room', 'office', 'apartment', 'corridor', 'large'],
        description='Environment label — used for rosbag naming and logging')

    declare_database_path = DeclareLaunchArgument(
        'database_path',
        default_value=os.path.expanduser('~/.ros/rtabmap.db'),
        description='Absolute path to the RTAB-Map SQLite database file')

    declare_delete_db = DeclareLaunchArgument(
        'delete_db', default_value='true',
        description='Delete database on startup (start a fresh map)')

    declare_localization = DeclareLaunchArgument(
        'localization', default_value='false',
        description='If true: localisation-only mode (no new keyframes added)')

    use_sim_time   = LaunchConfiguration('use_sim_time')
    use_rviz       = LaunchConfiguration('use_rviz')
    database_path  = LaunchConfiguration('database_path')
    delete_db      = LaunchConfiguration('delete_db')
    localization   = LaunchConfiguration('localization')
    environment    = LaunchConfiguration('environment')

    # ── Startup log ───────────────────────────────────────────────────────
    log_start = LogInfo(msg=[
        '\n',
        '═══════════════════════════════════════════════════════\n',
        '  Swachh Boudhik Yantra — Stage 4A: RTAB-Map SLAM\n',
        '═══════════════════════════════════════════════════════\n',
        '  Environment   : ', environment, '\n',
        '  Database      : ', database_path, '\n',
        '  Fresh start   : ', delete_db, '\n',
        '  Localise only : ', localization, '\n',
        '\n',
        '  Prerequisites:\n',
        '    ros2 launch vacuum_bringup sim.launch.py\n',
        '\n',
        '  Drive with:\n',
        '    ros2 run teleop_twist_keyboard teleop_twist_keyboard\n',
        '      --ros-args --remap cmd_vel:=/cmd_vel\n',
        '\n',
        '  Save map after mapping:\n',
        '    ros2 launch vacuum_slam map_saver.launch.py\n',
        '═══════════════════════════════════════════════════════',
    ])

    # ── RTAB-Map — mapping mode ───────────────────────────────────────────
    #
    # All RTAB-Map parameters are loaded from rtabmap.yaml.
    # Runtime overrides are passed as Node parameters (override YAML values).
    #
    # Key remappings:
    #   rgb/image      ← /camera/color/image_raw
    #   depth/image    ← /camera/depth/image_rect_raw
    #   rgb/camera_info← /camera/color/camera_info
    #   odom           ← /odom  (from diff_drive_controller)
    #
    # Arguments:
    #   --delete_db_on_start  — wipes old database for a clean mapping run
    #   --Mem/IncrementalMemory true — add new nodes during mapping
    #
    rtabmap_mapping = Node(
        package='rtabmap_slam',
        executable='rtabmap',
        name='rtabmap',
        output='screen',
        parameters=[
            rtabmap_yaml,
            {
                'use_sim_time':   use_sim_time,
                'database_path':  database_path,
                # Override the Mem/IncrementalMemory in YAML for clarity
                'Mem/IncrementalMemory': 'true',
                'Rtabmap/StartNewMapOnLoopClosure': 'false',
            },
        ],
        remappings=[
            # ── Camera inputs ──
            ('rgb/image',       '/camera/color/image_raw'),
            ('depth/image',     '/camera/depth/image_rect_raw'),
            ('rgb/camera_info', '/camera/color/camera_info'),
            # ── Odometry ──
            ('odom',            '/odom'),
        ],
        arguments=['--delete_db_on_start'],
        condition=UnlessCondition(localization),
    )

    # ── RTAB-Map — localisation mode ──────────────────────────────────────
    # Same node, but with Mem/IncrementalMemory=false (no new keyframes).
    # Used when mapping is complete and you want to localise only.
    rtabmap_localisation = Node(
        package='rtabmap_slam',
        executable='rtabmap',
        name='rtabmap',
        output='screen',
        parameters=[
            rtabmap_yaml,
            {
                'use_sim_time':         use_sim_time,
                'database_path':        database_path,
                'Mem/IncrementalMemory': 'false',    # localisation only
                'Mem/InitWMWithAllNodes': 'true',    # load all nodes from DB
            },
        ],
        remappings=[
            ('rgb/image',       '/camera/color/image_raw'),
            ('depth/image',     '/camera/depth/image_rect_raw'),
            ('rgb/camera_info', '/camera/color/camera_info'),
            ('odom',            '/odom'),
        ],
        condition=IfCondition(localization),
    )

    # ── RViz2 ─────────────────────────────────────────────────────────────
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2_slam',
        arguments=['-d', slam_rviz],
        parameters=[{'use_sim_time': use_sim_time}],
        output='screen',
        condition=IfCondition(use_rviz),
    )

    return LaunchDescription([
        declare_use_sim_time,
        declare_use_rviz,
        declare_environment,
        declare_database_path,
        declare_delete_db,
        declare_localization,
        log_start,
        rtabmap_mapping,
        rtabmap_localisation,
        rviz,
    ])
