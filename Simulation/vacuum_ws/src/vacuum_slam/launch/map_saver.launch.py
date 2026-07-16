#!/usr/bin/env python3
"""
map_saver.launch.py  —  Stage 4A: Export RTAB-Map Database to Nav2 Map
───────────────────────────────────────────────────────────────────────
Exports the 2D occupancy grid from a running or saved RTAB-Map database
into the PNG + YAML format expected by Nav2's map_server.

Usage (while RTAB-Map is running):
  ros2 launch vacuum_slam map_saver.launch.py

Usage (from saved database — RTAB-Map NOT running):
  ros2 launch vacuum_slam map_saver.launch.py \
    map_name:=office \
    output_dir:=/path/to/maps

Outputs:
  <output_dir>/<map_name>.pgm   — greyscale occupancy image
  <output_dir>/<map_name>.yaml  — map metadata for nav2_map_server

These files are loaded in Stage 5 (Nav2) with:
  ros2 run nav2_map_server map_server --ros-args -p map:=<path>/<name>.yaml

Note: This launch requires the /rtabmap/map topic to be publishing.
      Run sim.launch.py + slam.launch.py first, drive the robot, then
      run map_saver.launch.py once coverage is satisfactory.
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node


def generate_launch_description():

    workspace_root = os.path.join(
        os.path.dirname(__file__), '..', '..', '..', '..', '..', '..')

    declare_map_name = DeclareLaunchArgument(
        'map_name', default_value='map',
        description='Output map file name (without extension)')

    declare_output_dir = DeclareLaunchArgument(
        'output_dir',
        default_value=os.path.expanduser('~/maps/stage4'),
        description='Directory to write the PNG and YAML map files')

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='Use Gazebo simulation clock')

    map_name      = LaunchConfiguration('map_name')
    output_dir    = LaunchConfiguration('output_dir')
    use_sim_time  = LaunchConfiguration('use_sim_time')

    log_save = LogInfo(msg=[
        '\n[map_saver] Saving map from /rtabmap/map ...\n',
        '  Output: ', output_dir, '/', map_name, '.pgm / .yaml\n',
        '  (nav2_map_server compatible format)\n',
    ])

    map_saver = Node(
        package='nav2_map_server',
        executable='map_saver_cli',
        name='map_saver',
        output='screen',
        arguments=[
            '-f', [output_dir, '/', map_name],
            '--ros-args',
        ],
        parameters=[{'use_sim_time': use_sim_time}],
    )

    return LaunchDescription([
        declare_map_name,
        declare_output_dir,
        declare_use_sim_time,
        log_save,
        map_saver,
    ])
