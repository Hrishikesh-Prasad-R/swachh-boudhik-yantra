#!/usr/bin/env python3
"""
controllers.launch.py — Stage 3 (D435i + Controller Orchestration)
────────────────────────────────────────────────────────────────────
Spawns ros2_control controllers AND the camera diagnostics node.

Startup sequence:
  t=0s   Gazebo starts with gz_ros2_control plugin
  t=3s   Robot + D435i sensor spawned into Gazebo
  t=5s   joint_state_broadcaster spawned
  t=6s   diff_drive_controller spawned
  t=7s   cmd_vel relay active
  t=8s   OdometryNoiseNode + MotionDiagnosticsNode
  t=10s  CameraDiagnosticsNode (waits for camera bridge to stabilise)

Usage:
  Included by vacuum_bringup/launch/sim.launch.py automatically.
  Can also be run standalone:
    ros2 launch vacuum_controller controllers.launch.py
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

    use_sim_time     = LaunchConfiguration('use_sim_time')
    enable_noise     = LaunchConfiguration('enable_odom_noise')
    enable_diag      = LaunchConfiguration('enable_diagnostics')

    # ── joint_state_broadcaster ────────────────────────────────────
    # Must be spawned first: diff_drive_controller depends on having
    # joint states available to read encoder positions.
    # Delay 5s: robot spawns at 3s, give controller_manager 2 more seconds.
    joint_state_broadcaster_spawner = TimerAction(
        period=5.0,
        actions=[
            Node(
                package='controller_manager',
                executable='spawner',
                name='joint_state_broadcaster_spawner',
                prefix=['python3.12'],
                arguments=[
                    'joint_state_broadcaster',
                    '--controller-manager', '/controller_manager',
                ],
                output='screen',
            )
        ],
    )

    # ── diff_drive_controller ──────────────────────────────────────
    # Spawned after joint_state_broadcaster (6s total delay).
    # The 1s gap between JSB and DDC avoids a race condition where DDC
    # tries to read joint states before JSB has activated.
    diff_drive_controller_spawner = TimerAction(
        period=6.0,
        actions=[
            Node(
                package='controller_manager',
                executable='spawner',
                name='diff_drive_controller_spawner',
                prefix=['python3.12'],
                arguments=[
                    'diff_drive_controller',
                    '--controller-manager', '/controller_manager',
                ],
                output='screen',
            )
        ],
    )

    # ── cmd_vel relay ──────────────────────────────────────────────
    # diff_drive_controller subscribes to /diff_drive_controller/cmd_vel.
    # This relay node remaps that to the standard /cmd_vel.
    # Using topic_tools/relay keeps teleop commands simple.
    cmd_vel_relay = TimerAction(
        period=7.0,
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
    # Relaying this to /odom satisfies downstream components (like RTAB-Map)
    # that expect /odom topic by default.
    odom_relay = TimerAction(
        period=7.0,
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
        period=8.0,
        actions=[
            Node(
                package='vacuum_controller',
                executable='odometry_noise_node.py',
                name='odometry_noise_node',
                prefix=['python3.12'],
                parameters=[{
                    'use_sim_time': use_sim_time,
                    'enable_noise': enable_noise,
                    'linear_noise_std':  0.005,   # m, σ for x/y position noise
                    'angular_noise_std': 0.003,   # rad, σ for yaw noise
                    'rate_hz': 30.0,
                }],
                output='screen',
            )
        ],
    )

    # ── Motion Diagnostics Node ─────────────────────────────────────
    motion_diagnostics_node = TimerAction(
        period=8.0,
        actions=[
            Node(
                package='vacuum_controller',
                executable='motion_diagnostics_node.py',
                name='motion_diagnostics_node',
                prefix=['python3.12'],
                parameters=[{
                    'use_sim_time': use_sim_time,
                    'cmd_vel_timeout_warn': 0.5,  # s — warn if no cmd for this long
                    'publish_rate': 2.0,           # Hz — diagnostics publish rate
                }],
                output='screen',
            )
        ],
    )

    # ── Camera Diagnostics Node (Stage 3) ──────────────────────────
    # Started 10s after launch to ensure the gz_bridge is publishing
    # and the camera topics have stabilised from startup transients.
    camera_diagnostics_node = TimerAction(
        period=10.0,
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
        joint_state_broadcaster_spawner,
        diff_drive_controller_spawner,
        cmd_vel_relay,
        odom_relay,
        odometry_noise_node,
        motion_diagnostics_node,
        camera_diagnostics_node,
    ])
