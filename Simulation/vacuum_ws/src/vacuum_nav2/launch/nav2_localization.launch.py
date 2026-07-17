#!/usr/bin/env python3
"""
nav2_localization.launch.py  —  Stage 5: AMCL + Map Server + Nav2
──────────────────────────────────────────────────────────────────
Launches the complete Stage 5 localization and navigation stack.

Assumes Gazebo + ros2_control + robot_state_publisher are ALREADY running
(either from start.sh or manually). Does NOT launch Gazebo.

Startup sequence (staged):
  T+0s  : depthimage_to_laserscan  — depth image → /scan_from_depth
  T+2s  : map_server               — loads saved .pgm/.yaml map → /map
  T+5s  : amcl                     — particle filter, publishes map→odom TF
  T+8s  : Nav2 nodes               — planner, controller, behavior, smoother
  T+12s : lifecycle_manager        — activates all nodes (autostart: true)
  T+14s : RViz2                    — with Pose Estimate + Nav Goal tools

Required argument:
  map_path   — absolute path to .yaml map file (e.g. ~/maps/stage5/apartment.yaml)

Optional arguments:
  environment [apartment]   — label for metrics naming
  use_rviz    [true]        — set false for headless runs
  use_sim_time [true]       — set false for real hardware

Usage:
  ros2 launch vacuum_nav2 nav2_localization.launch.py \\
    map_path:=/home/bmscecse/maps/stage5/apartment.yaml

  # From start.sh:
  ./start.sh navigate apartment
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

    pkg_nav2 = get_package_share_directory('vacuum_nav2')

    nav2_yaml     = os.path.join(pkg_nav2, 'config', 'nav2_params.yaml')
    amcl_yaml     = os.path.join(pkg_nav2, 'config', 'amcl_params.yaml')
    nav_bt_xml    = os.path.join(pkg_nav2, 'behavior_trees', 'navigate.xml')

    # ── Arguments ─────────────────────────────────────────────────────────────
    declare_map_path = DeclareLaunchArgument(
        'map_path',
        default_value=os.path.expanduser('~/maps/stage5/apartment.yaml'),
        description='Full path to the saved map .yaml file')

    declare_environment = DeclareLaunchArgument(
        'environment', default_value='apartment',
        description='Environment label for metrics naming')

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='Use Gazebo simulation clock')

    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz', default_value='true',
        description='Launch RViz2 for navigation visualisation')

    map_path     = LaunchConfiguration('map_path')
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz     = LaunchConfiguration('use_rviz')

    log_start = LogInfo(msg=[
        '\n',
        '╔══════════════════════════════════════════════════════╗\n',
        '║  Stage 5: Localization & Goal Navigation             ║\n',
        '║  AMCL + Map Server + Nav2 (MPPI + SmacHybrid)        ║\n',
        '╚══════════════════════════════════════════════════════╝\n',
        '  Map : ', map_path, '\n',
        '  IMPORTANT: Use RViz "2D Pose Estimate" to initialise\n',
        '             AMCL before sending navigation goals.\n',
    ])

    # ── T+0s: depthimage_to_laserscan ─────────────────────────────────────────
    # Converts D435i depth image to /scan_from_depth for AMCL.
    depth_to_scan = Node(
        package='depthimage_to_laserscan',
        executable='depthimage_to_laserscan_node',
        name='depth_to_scan',
        output='screen',
        parameters=[{
            'use_sim_time':  use_sim_time,
            'scan_height':   5,
            'scan_time':     0.033,
            'range_min':     0.20,
            'range_max':     4.00,
            'output_frame':  'camera_link',
        }],
        remappings=[
            ('image',       '/camera/depth/image_rect_raw'),
            ('camera_info', '/camera/color/camera_info'),
            ('scan',        '/scan_from_depth'),
        ],
    )

    # ── T+2s: Map Server ──────────────────────────────────────────────────────
    # Loads the saved occupancy grid and publishes it as /map.
    map_server = TimerAction(
        period=2.0,
        actions=[Node(
            package='nav2_map_server',
            executable='map_server',
            name='map_server',
            output='screen',
            parameters=[{
                'use_sim_time':  use_sim_time,
                'yaml_filename': map_path,
                'frame_id':      'map',
                'topic_name':    '/map',
            }],
        )],
    )

    # ── T+5s: AMCL ───────────────────────────────────────────────────────────
    # Particle filter localisation. Publishes map → odom TF.
    amcl = TimerAction(
        period=5.0,
        actions=[Node(
            package='nav2_amcl',
            executable='amcl',
            name='amcl',
            output='screen',
            parameters=[amcl_yaml, {'use_sim_time': use_sim_time}],
        )],
    )

    # ── T+8s: Nav2 nodes (reused from Stage 4B) ───────────────────────────────
    bt_navigator = TimerAction(period=8.0, actions=[Node(
        package='nav2_bt_navigator',
        executable='bt_navigator',
        name='bt_navigator',
        output='screen',
        parameters=[nav2_yaml, {
            'use_sim_time': use_sim_time,
            'default_nav_to_pose_bt_xml': nav_bt_xml,  # navigate.xml (Stage 5)
        }],
    )])

    planner_server = TimerAction(period=8.0, actions=[Node(
        package='nav2_planner',
        executable='planner_server',
        name='planner_server',
        output='screen',
        parameters=[nav2_yaml, {'use_sim_time': use_sim_time}],
    )])

    controller_server = TimerAction(period=8.0, actions=[Node(
        package='nav2_controller',
        executable='controller_server',
        name='controller_server',
        output='screen',
        parameters=[nav2_yaml, {'use_sim_time': use_sim_time}],
        remappings=[('cmd_vel', '/diff_drive_controller/cmd_vel_unstamped')],
    )])

    behavior_server = TimerAction(period=8.0, actions=[Node(
        package='nav2_behaviors',
        executable='behavior_server',
        name='behavior_server',
        output='screen',
        parameters=[nav2_yaml, {'use_sim_time': use_sim_time}],
        remappings=[('cmd_vel', '/diff_drive_controller/cmd_vel_unstamped')],
    )])

    smoother_server = TimerAction(period=8.0, actions=[Node(
        package='nav2_smoother',
        executable='smoother_server',
        name='smoother_server',
        output='screen',
        parameters=[nav2_yaml, {'use_sim_time': use_sim_time}],
    )])

    velocity_smoother = TimerAction(period=8.0, actions=[Node(
        package='nav2_velocity_smoother',
        executable='velocity_smoother',
        name='velocity_smoother',
        output='screen',
        parameters=[nav2_yaml, {'use_sim_time': use_sim_time}],
        remappings=[
            ('cmd_vel',         '/diff_drive_controller/cmd_vel_unstamped'),
            ('cmd_vel_smoothed', '/diff_drive_controller/cmd_vel_unstamped'),
        ],
    )])

    # ── T+12s: Lifecycle Manager ──────────────────────────────────────────────
    # Stage 5 adds map_server + amcl to the lifecycle chain.
    lifecycle_manager = TimerAction(
        period=12.0,
        actions=[Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='lifecycle_manager',
            output='screen',
            parameters=[{
                'use_sim_time': use_sim_time,
                'autostart': True,
                'node_names': [
                    'map_server',          # Stage 5 — new
                    'amcl',                # Stage 5 — new
                    'bt_navigator',
                    'planner_server',
                    'controller_server',
                    'behavior_server',
                    'smoother_server',
                    'velocity_smoother',
                ],
            }],
        )],
    )

    # ── T+14s: RViz2 ─────────────────────────────────────────────────────────
    rviz = TimerAction(
        period=14.0,
        actions=[Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2_navigation',
            parameters=[{'use_sim_time': use_sim_time}],
            output='screen',
            condition=IfCondition(use_rviz),
        )],
    )

    return LaunchDescription([
        declare_map_path,
        declare_environment,
        declare_use_sim_time,
        declare_use_rviz,
        log_start,
        depth_to_scan,
        map_server,
        amcl,
        bt_navigator,
        planner_server,
        controller_server,
        behavior_server,
        smoother_server,
        velocity_smoother,
        lifecycle_manager,
        rviz,
    ])
