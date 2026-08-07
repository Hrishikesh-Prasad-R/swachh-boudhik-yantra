#!/usr/bin/env python3
"""
nav2.launch.py  —  Stage 4B: Nav2 Stack for Autonomous Exploration
───────────────────────────────────────────────────────────────────
Launches the minimal Nav2 stack required for frontier exploration.

Nodes started:
  1. depthimage_to_laserscan   — converts D435i depth to /scan_from_depth
  2. nav2_bt_navigator         — executes NavigateToPose action goals
  3. nav2_planner_server       — global path planning (SmacHybrid)
  4. nav2_controller_server    — local control (MPPI)
  5. nav2_behavior_server      — recovery behaviors (spin, back_up, wait)
  6. nav2_smoother_server      — path smoothing
  7. nav2_velocity_smoother    — velocity smoothing
  8. nav2_lifecycle_manager    — activates all the above nodes

RTAB-Map provides the map→odom TF, so AMCL is NOT launched here.
This is correct for Stage 4B (exploration on an unknown map).

Prerequisites:
  ros2 launch vacuum_bringup sim.launch.py       (Gazebo + robot)
  ros2 launch vacuum_slam slam.launch.py         (RTAB-Map)

Usage:
  ros2 launch vacuum_nav2 nav2.launch.py
  ros2 launch vacuum_nav2 nav2.launch.py use_sim_time:=true
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, GroupAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace


def generate_launch_description():

    pkg_nav2   = get_package_share_directory('vacuum_nav2')
    nav2_yaml  = os.path.join(pkg_nav2, 'config', 'nav2_params.yaml')
    bt_xml     = os.path.join(pkg_nav2, 'behavior_trees', 'explore.xml')

    # ── Arguments ─────────────────────────────────────────────────────────────
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='Use Gazebo simulation clock')

    use_sim_time = LaunchConfiguration('use_sim_time')

    log_start = LogInfo(msg=[
        '\n',
        '═══════════════════════════════════════════════════════\n',
        '  Swachh Boudhik Yantra — Stage 4B: Nav2 Stack\n',
        '═══════════════════════════════════════════════════════\n',
        '  Global planner : SmacPlannerHybrid (Hybrid A*)\n',
        '  Local planner  : MPPIController\n',
        '  Map source     : /rtabmap/map  (live from RTAB-Map)\n',
        '  Localisation   : RTAB-Map TF  (no AMCL in Stage 4B)\n',
        '  BT             : behavior_trees/explore.xml\n',
        '═══════════════════════════════════════════════════════',
    ])

    # ── /rtabmap/map → /map relay ─────────────────────────────────────────────
    # RTAB-Map publishes OccupancyGrid on /rtabmap/map.
    # Nav2 static_layer expects /map (nav2_params.yaml: map_topic: /map).
    # This relay bridges the two so the global costmap is populated.
    map_relay = Node(
        package='topic_tools',
        executable='relay',
        name='rtabmap_map_relay',
        arguments=['/rtabmap/map', '/map'],
        parameters=[{'use_sim_time': use_sim_time}],
        output='screen',
    )

    # ── depthimage_to_laserscan ────────────────────────────────────────────────
    # Converts RealSense D435i depth image → /scan_from_depth (LaserScan).
    # This scan is used by Nav2's obstacle layer for real-time obstacle detection.
    #
    # Parameters:
    #   scan_height  : number of depth rows to use for the 2D scan slice
    #   range_min/max: matches D435i effective range (0.2 – 4.0 m)
    depth_to_scan = Node(
        package='depthimage_to_laserscan',
        executable='depthimage_to_laserscan_node',
        name='depthimage_to_laserscan_node',
        output='screen',
        parameters=[{
            'use_sim_time':     use_sim_time,
            'scan_height':      5,          # rows of depth image to collapse into scan
            'scan_time':        0.033,      # s — ~30 fps
            'range_min':        0.20,       # m
            'range_max':        4.00,       # m — D435i max reliable depth
            'output_frame':     'camera_link',
        }],
        remappings=[
            ('image',        '/camera/depth/image_rect_raw'),
            ('camera_info',  '/camera/color/camera_info'),
            ('scan',         '/scan_from_depth'),
        ],
    )

    # ── BT Navigator ──────────────────────────────────────────────────────────
    bt_navigator = Node(
        package='nav2_bt_navigator',
        executable='bt_navigator',
        name='bt_navigator',
        output='screen',
        parameters=[
            nav2_yaml,
            {
                'use_sim_time': use_sim_time,
                'default_nav_to_pose_bt_xml': bt_xml,
            },
        ],
    )

    # ── Planner Server ────────────────────────────────────────────────────────
    planner_server = Node(
        package='nav2_planner',
        executable='planner_server',
        name='planner_server',
        output='screen',
        parameters=[nav2_yaml, {'use_sim_time': use_sim_time}],
    )

    # ── Controller Server ─────────────────────────────────────────────────────
    controller_server = Node(
        package='nav2_controller',
        executable='controller_server',
        name='controller_server',
        output='screen',
        parameters=[nav2_yaml, {'use_sim_time': use_sim_time}],
        remappings=[('cmd_vel', '/diff_drive_controller/cmd_vel_unstamped')],
    )

    # ── Behavior Server ────────────────────────────────────────────────────────
    behavior_server = Node(
        package='nav2_behaviors',
        executable='behavior_server',
        name='behavior_server',
        output='screen',
        parameters=[nav2_yaml, {'use_sim_time': use_sim_time}],
        remappings=[('cmd_vel', '/diff_drive_controller/cmd_vel_unstamped')],
    )

    # ── Smoother Server ────────────────────────────────────────────────────────
    smoother_server = Node(
        package='nav2_smoother',
        executable='smoother_server',
        name='smoother_server',
        output='screen',
        parameters=[nav2_yaml, {'use_sim_time': use_sim_time}],
    )

    # ── Velocity Smoother ──────────────────────────────────────────────────────
    velocity_smoother = Node(
        package='nav2_velocity_smoother',
        executable='velocity_smoother',
        name='velocity_smoother',
        output='screen',
        parameters=[nav2_yaml, {'use_sim_time': use_sim_time}],
        remappings=[
            ('cmd_vel',        '/diff_drive_controller/cmd_vel_unstamped'),
            ('cmd_vel_smoothed', '/diff_drive_controller/cmd_vel_unstamped'),
        ],
    )

    # ── Lifecycle Manager ──────────────────────────────────────────────────────
    # Manages startup and shutdown sequencing of all Nav2 nodes.
    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager',
        output='screen',
        parameters=[{
            'use_sim_time': use_sim_time,
            'autostart': True,
            'node_names': [
                'planner_server',
                'controller_server',
                'behavior_server',
                'smoother_server',
                'velocity_smoother',
                'bt_navigator',
            ],
        }],
    )

    return LaunchDescription([
        declare_use_sim_time,
        log_start,
        map_relay,
        depth_to_scan,
        bt_navigator,
        planner_server,
        controller_server,
        behavior_server,
        smoother_server,
        velocity_smoother,
        lifecycle_manager,
    ])
