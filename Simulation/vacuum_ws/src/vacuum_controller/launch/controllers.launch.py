#!/usr/bin/env python3
"""
controllers.launch.py — Stage 3 (D435i + Controller Orchestration)
────────────────────────────────────────────────────────────────────
Manages helper nodes for the ros2_control pipeline.

IMPORTANT: joint_state_broadcaster and diff_drive_controller are NOT
spawned here. gz_ros2_control reads the controller types from
controllers.yaml (via <parameters> in _gazebo.xacro) and
auto-loads + activates them at robot spawn time. Explicit spawner
nodes would conflict (cannot configure an already-active controller).

Startup sequence:
  t=0s   Gazebo starts with gz_ros2_control plugin
  t=3s   Robot spawned; gz_ros2_control reads controllers.yaml,
         auto-loads and activates JSB + DDC immediately
  t=12s  cmd_vel relay + odom relay started
  t=13s  OdometryNoiseNode + MotionDiagnosticsNode
  t=15s  CameraDiagnosticsNode

Usage:
  Included by vacuum_bringup/launch/sim.launch.py automatically.
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    camera_yaml = os.path.join(
        get_package_share_directory('vacuum_gazebo'),
        'config', 'camera.yaml')

    # ── Arguments ──────────────────────────────────────────────────
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='Use simulation clock')
    declare_enable_noise = DeclareLaunchArgument(
        'enable_odom_noise', default_value='false',
        description='Enable Gaussian odometry noise on /odom_noisy topic')
    declare_enable_diagnostics = DeclareLaunchArgument(
        'enable_diagnostics', default_value='true',
        description='Enable motion diagnostics node')
    declare_enable_cam_diag = DeclareLaunchArgument(
        'enable_camera_diagnostics', default_value='true',
        description='Enable D435i camera diagnostics node')

    use_sim_time = LaunchConfiguration('use_sim_time')
    enable_noise = LaunchConfiguration('enable_odom_noise')

    # ── Controller Spawners ────────────────────────────────────────
    # gz_ros2_control initialises the hardware interface (VacuumRobotHW)
    # at robot spawn time (~T+3s), but does NOT auto-load controllers.
    # Explicit spawners are required to load, configure, and activate
    # joint_state_broadcaster and diff_drive_controller.
    #
    # T+5s gives gz_ros2_control ~2s after robot spawn to fully
    # initialise the hardware before the spawners contact it.
    jsb_spawner = TimerAction(
        period=2.0,
        actions=[
            Node(
                package='controller_manager',
                executable='spawner',
                name='jsb_spawner',
                prefix=['python3.12'],
                arguments=['joint_state_broadcaster', '--activate'],
                output='screen',
            )
        ],
    )

    ddc_spawner = TimerAction(
        period=2.0,
        actions=[
            Node(
                package='controller_manager',
                executable='spawner',
                name='ddc_spawner',
                prefix=['python3.12'],
                arguments=['diff_drive_controller', '--activate'],
                output='screen',
            )
        ],
    )

    # ── cmd_vel relay ──────────────────────────────────────────────
    # diff_drive_controller subscribes to /diff_drive_controller/cmd_vel.
    # This relay remaps that to the standard /cmd_vel interface.
    # Starts at T+12s (well after gz_ros2_control has activated DDC).
    cmd_vel_relay = TimerAction(
        period=12.0,
        actions=[
            Node(
                package='vacuum_controller',
                executable='cmd_vel_relay.py',
                name='cmd_vel_relay',
                prefix=['python3.12'],
                parameters=[{'use_sim_time': use_sim_time}],
                output='screen',
            )
        ],
    )

    # ── odom relay ─────────────────────────────────────────────────
    # diff_drive_controller publishes /diff_drive_controller/odom.
    # Relay to /odom for Nav2, RTAB-Map and other downstream nodes.
    odom_relay = TimerAction(
        period=12.0,
        actions=[
            Node(
                package='topic_tools',
                executable='relay',
                name='odom_relay',
                arguments=['/diff_drive_controller/odom', '/odom'],
                parameters=[{'use_sim_time': use_sim_time}],
                output='screen',
            )
        ],
    )

    # ── Odometry Noise Node (optional) ─────────────────────────────
    odometry_noise_node = TimerAction(
        period=13.0,
        actions=[
            Node(
                package='vacuum_controller',
                executable='odometry_noise_node.py',
                name='odometry_noise_node',
                prefix=['python3.12'],
                parameters=[{
                    'use_sim_time': use_sim_time,
                    'enable_noise': enable_noise,
                    'linear_noise_std':  0.005,
                    'angular_noise_std': 0.003,
                    'rate_hz': 30.0,
                }],
                output='screen',
            )
        ],
    )

    # ── Motion Diagnostics Node ─────────────────────────────────────
    motion_diagnostics_node = TimerAction(
        period=13.0,
        actions=[
            Node(
                package='vacuum_controller',
                executable='motion_diagnostics_node.py',
                name='motion_diagnostics_node',
                prefix=['python3.12'],
                parameters=[{
                    'use_sim_time': use_sim_time,
                    'cmd_vel_timeout_warn': 0.5,
                    'publish_rate': 2.0,
                }],
                output='screen',
            )
        ],
    )

    # ── Camera Diagnostics Node (Stage 3) ──────────────────────────
    camera_diagnostics_node = TimerAction(
        period=15.0,
        actions=[
            Node(
                package='vacuum_controller',
                executable='camera_diagnostics_node.py',
                name='camera_diagnostics_node',
                prefix=['python3.12'],
                parameters=[
                    camera_yaml,
                    {'use_sim_time': use_sim_time},
                ],
                output='screen',
            )
        ],
    )

    return LaunchDescription([
        declare_use_sim_time,
        declare_enable_noise,
        declare_enable_diagnostics,
        declare_enable_cam_diag,
        jsb_spawner,
        ddc_spawner,
        cmd_vel_relay,
        odom_relay,
        odometry_noise_node,
        motion_diagnostics_node,
        camera_diagnostics_node,
    ])
