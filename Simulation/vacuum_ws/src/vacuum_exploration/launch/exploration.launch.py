#!/usr/bin/env python3
"""
exploration.launch.py  —  Stage 4B: Full Autonomous Exploration Stack
──────────────────────────────────────────────────────────────────────
Launches the complete Stage 4B pipeline in the correct order:

  T+0s   : Gazebo simulation + robot (vacuum_bringup sim.launch.py)
  T+12s  : RTAB-Map SLAM in mapping mode (vacuum_slam slam.launch.py)
  T+20s  : Nav2 stack (vacuum_nav2 nav2.launch.py)
  T+28s  : Exploration nodes (frontier_detector, exploration_manager,
             frontier_visualizer, exploration_metrics)
  T+28s  : RViz2 with exploration configuration

Usage:
  # Default apartment environment
  ros2 launch vacuum_exploration exploration.launch.py

  # Office environment
  ros2 launch vacuum_exploration exploration.launch.py environment:=office

  # Without Gazebo (if already running)
  ros2 launch vacuum_exploration exploration.launch.py launch_sim:=false

Arguments:
  environment [apartment]  — label for bag naming and metrics
  launch_sim  [true]       — set false if Gazebo is already running
  use_rviz    [true]       — set false for headless runs
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, IncludeLaunchDescription,
    LogInfo, TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    # ── Package paths ──────────────────────────────────────────────────────────
    pkg_bringup     = get_package_share_directory('vacuum_bringup')
    pkg_slam        = get_package_share_directory('vacuum_slam')
    pkg_nav2        = get_package_share_directory('vacuum_nav2')
    pkg_exploration = get_package_share_directory('vacuum_exploration')

    exploration_yaml = os.path.join(pkg_exploration, 'config', 'exploration_params.yaml')

    # ── Arguments ─────────────────────────────────────────────────────────────
    declare_environment = DeclareLaunchArgument(
        'environment', default_value='apartment',
        choices=['apartment', 'office', 'room', 'corridor', 'warehouse'],
        description='Environment label — used for metrics and bag naming')

    declare_launch_sim = DeclareLaunchArgument(
        'launch_sim', default_value='true',
        description='Launch Gazebo simulation (false if already running)')

    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz', default_value='true',
        description='Launch RViz2 for exploration visualisation')

    environment  = LaunchConfiguration('environment')
    launch_sim   = LaunchConfiguration('launch_sim')
    use_rviz     = LaunchConfiguration('use_rviz')

    log_start = LogInfo(msg=[
        '\n',
        '╔══════════════════════════════════════════════════════╗\n',
        '║  Stage 4B: Autonomous Exploration                    ║\n',
        '║  Nav2 + Frontier Exploration + RTAB-Map             ║\n',
        '╚══════════════════════════════════════════════════════╝\n',
        '  Environment : ', environment, '\n',
        '  Startup sequence:\n',
        '    T+0s  : Gazebo simulation\n',
        '    T+12s : RTAB-Map SLAM\n',
        '    T+20s : Nav2 stack\n',
        '    T+28s : Exploration nodes\n',
    ])

    # ── 1. Gazebo Simulation (T+0s) ───────────────────────────────────────────
    sim_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [pkg_bringup, '/launch/sim.launch.py']),
        launch_arguments={'use_sim_time': 'true'}.items(),
        condition=IfCondition(launch_sim),
    )

    # ── 2. RTAB-Map SLAM (T+12s) ──────────────────────────────────────────────
    slam_launch = TimerAction(
        period=12.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                [pkg_slam, '/launch/slam.launch.py']),
            launch_arguments={
                'use_sim_time': 'true',
                'use_rviz':     'false',   # RViz started separately below
                'delete_db':    'true',
                'environment':  environment,
            }.items(),
        )],
    )

    # ── 3. Nav2 Stack (T+20s) ─────────────────────────────────────────────────
    nav2_launch = TimerAction(
        period=20.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                [pkg_nav2, '/launch/nav2.launch.py']),
            launch_arguments={'use_sim_time': 'true'}.items(),
        )],
    )

    # ── 4. Exploration Nodes (T+28s) ──────────────────────────────────────────
    frontier_detector = TimerAction(
        period=28.0,
        actions=[Node(
            package='vacuum_exploration',
            executable='frontier_detector',
            name='frontier_detector',
            output='screen',
            parameters=[exploration_yaml, {'use_sim_time': True}],
        )],
    )

    exploration_manager = TimerAction(
        period=28.0,
        actions=[Node(
            package='vacuum_exploration',
            executable='exploration_manager',
            name='exploration_manager',
            output='screen',
            parameters=[exploration_yaml, {
                'use_sim_time': True,
                'environment':  environment,
            }],
        )],
    )

    frontier_visualizer = TimerAction(
        period=28.0,
        actions=[Node(
            package='vacuum_exploration',
            executable='frontier_visualizer',
            name='frontier_visualizer',
            output='screen',
            parameters=[{'use_sim_time': True}],
        )],
    )

    exploration_metrics = TimerAction(
        period=28.0,
        actions=[Node(
            package='vacuum_exploration',
            executable='exploration_metrics',
            name='exploration_metrics',
            output='screen',
            parameters=[exploration_yaml, {
                'use_sim_time': True,
                'environment':  environment,
            }],
        )],
    )

    # ── 5. RViz2 (T+28s, optional) ────────────────────────────────────────────
    rviz = TimerAction(
        period=28.0,
        actions=[Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2_exploration',
            parameters=[{'use_sim_time': True}],
            output='screen',
            condition=IfCondition(use_rviz),
        )],
    )

    return LaunchDescription([
        declare_environment,
        declare_launch_sim,
        declare_use_rviz,
        log_start,
        sim_launch,
        slam_launch,
        nav2_launch,
        frontier_detector,
        exploration_manager,
        frontier_visualizer,
        exploration_metrics,
        rviz,
    ])
