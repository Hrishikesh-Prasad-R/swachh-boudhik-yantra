#!/usr/bin/env python3
"""
localization_monitor.launch.py  —  Stage 5: Localization Monitor Nodes
────────────────────────────────────────────────────────────────────────
Launches the three vacuum_localization monitoring nodes alongside an
already-running Stage 5 nav2_localization stack.

Usage:
  ros2 launch vacuum_localization localization_monitor.launch.py
  ros2 launch vacuum_localization localization_monitor.launch.py environment:=office
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    pkg_loc = get_package_share_directory('vacuum_localization')
    loc_yaml = os.path.join(pkg_loc, 'config', 'localization_params.yaml')

    declare_environment = DeclareLaunchArgument(
        'environment', default_value='apartment',
        description='Environment label for metrics naming')

    declare_map_file = DeclareLaunchArgument(
        'map_file', default_value='',
        description='Path to map .yaml file used (for metadata)')

    environment = LaunchConfiguration('environment')
    map_file    = LaunchConfiguration('map_file')

    localization_monitor = Node(
        package='vacuum_localization',
        executable='localization_monitor',
        name='localization_monitor',
        output='screen',
        parameters=[loc_yaml, {'use_sim_time': True}],
    )

    recovery_monitor = Node(
        package='vacuum_localization',
        executable='recovery_monitor',
        name='recovery_monitor',
        output='screen',
        parameters=[loc_yaml, {'use_sim_time': True}],
    )

    localization_metrics = Node(
        package='vacuum_localization',
        executable='localization_metrics',
        name='localization_metrics',
        output='screen',
        parameters=[loc_yaml, {
            'use_sim_time': True,
            'environment':  environment,
            'map_file':     map_file,
        }],
    )

    return LaunchDescription([
        declare_environment,
        declare_map_file,
        localization_monitor,
        recovery_monitor,
        localization_metrics,
    ])
