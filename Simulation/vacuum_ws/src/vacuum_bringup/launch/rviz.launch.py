#!/usr/bin/env python3
"""
rviz.launch.py — RViz2 standalone launch
─────────────────────────────────────────
Use this when you want to open RViz2 separately from the simulation.
The simulation must already be running for topics to be visible.

Usage:
  ros2 launch vacuum_bringup rviz.launch.py
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    pkg_bringup = get_package_share_directory('vacuum_bringup')
    rviz_config = os.path.join(pkg_bringup, 'config', 'rviz_config.rviz')

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='Use simulation clock')

    use_sim_time = LaunchConfiguration('use_sim_time')

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': use_sim_time}],
        output='screen',
    )

    return LaunchDescription([
        declare_use_sim_time,
        rviz,
    ])
