#!/usr/bin/env python3
# FIXED: ParameterValue wrapper — required in ROS2 Jazzy for XML parameters
# Without this, launch parses URDF XML as YAML and throws an error.
"""
sim.launch.py — MASTER simulation launch file (Stage 1)
────────────────────────────────────────────────────────
Orchestrates the complete simulation stack in this order:

  1. robot_state_publisher  — reads URDF, publishes /robot_description + TF
  2. Gazebo Harmonic        — physics simulation
  3. ros_gz_bridge          — topic bridge between Gazebo ↔ ROS2
  4. spawn_robot            — places the robot into the Gazebo world (delayed 3s)
  5. RViz2 (optional)       — visualisation

Launch arguments:
  use_sim_time  [true]   — all nodes use /clock from Gazebo
  use_rviz      [true]   — launch RViz2 alongside Gazebo
  world_file    [empty_world.sdf]  — path to Gazebo world file
  spawn_x/y/yaw [0.0]   — robot initial pose

Usage:
  ros2 launch vacuum_bringup sim.launch.py
  ros2 launch vacuum_bringup sim.launch.py use_rviz:=false
  ros2 launch vacuum_bringup sim.launch.py world_file:=/path/to/custom.sdf
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    LaunchConfiguration,
    Command,
    PathJoinSubstitution,
)
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.actions import Node


def generate_launch_description():

    # ── Package share directories ──────────────────────────────────
    pkg_description = get_package_share_directory('vacuum_description')
    pkg_gazebo      = get_package_share_directory('vacuum_gazebo')
    pkg_bringup     = get_package_share_directory('vacuum_bringup')
    pkg_ros_gz_sim  = get_package_share_directory('ros_gz_sim')

    # ── Default paths ──────────────────────────────────────────────
    default_world  = os.path.join(pkg_gazebo, 'worlds', 'empty_world.sdf')
    default_rviz   = os.path.join(pkg_bringup, 'config', 'rviz_config.rviz')
    urdf_file      = os.path.join(pkg_description, 'urdf', 'vacuum.urdf.xacro')
    bridge_config  = os.path.join(pkg_gazebo, 'config', 'gz_bridge.yaml')

    # ── Launch arguments ───────────────────────────────────────────
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='Use Gazebo simulation clock for all ROS2 nodes')

    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz', default_value='true',
        description='Launch RViz2 for visualisation')

    declare_world_file = DeclareLaunchArgument(
        'world_file', default_value=default_world,
        description='Absolute path to the Gazebo .sdf world file')

    declare_spawn_x = DeclareLaunchArgument(
        'spawn_x', default_value='0.0',
        description='Initial X position of the robot')
    declare_spawn_y = DeclareLaunchArgument(
        'spawn_y', default_value='0.0',
        description='Initial Y position of the robot')
    declare_spawn_yaw = DeclareLaunchArgument(
        'spawn_yaw', default_value='0.0',
        description='Initial yaw (heading) of the robot in radians')

    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz     = LaunchConfiguration('use_rviz')
    world_file   = LaunchConfiguration('world_file')
    spawn_x      = LaunchConfiguration('spawn_x')
    spawn_y      = LaunchConfiguration('spawn_y')
    spawn_yaw    = LaunchConfiguration('spawn_yaw')

    # ── 1. Robot State Publisher ───────────────────────────────────
    # Parses URDF/Xacro, publishes /robot_description, and publishes
    # static TF for all fixed joints (base_footprint→base_link, mounts, etc.)
    # ParameterValue(value_type=str) is REQUIRED in Jazzy.
    # Without it, launch tries to parse the URDF XML as YAML and fails.
    robot_description_content = ParameterValue(
        Command(['xacro ', urdf_file]),
        value_type=str
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description_content,
            'use_sim_time': use_sim_time,
            'publish_frequency': 50.0,
        }],
    )

    # ── 2. Gazebo Harmonic ─────────────────────────────────────────
    # -r flag = run immediately (no pause on startup)
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': ['-r ', world_file],
            'on_exit_shutdown': 'true',
        }.items(),
    )

    # ── 3. ROS-Gazebo Bridge ───────────────────────────────────────
    # Started before spawning so bridge is ready to receive topic data
    ros_gz_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_bridge',
        parameters=[{'config_file': bridge_config}],
        output='screen',
    )

    # ── 4. Spawn robot (delayed) ───────────────────────────────────
    # 3-second delay allows Gazebo physics to fully initialise before spawn.
    # Spawning too early causes physics instability on first tick.
    spawn_robot = TimerAction(
        period=3.0,
        actions=[
            Node(
                package='ros_gz_sim',
                executable='create',
                name='spawn_vacuum_robot',
                arguments=[
                    '-name',  'vacuum_robot',
                    '-topic', '/robot_description',
                    '-x',     spawn_x,
                    '-y',     spawn_y,
                    '-z',     '0.0',     # base_footprint at ground level
                    '-Y',     spawn_yaw,
                ],
                output='screen',
            )
        ],
    )

    # ── 5. RViz2 (conditional) ─────────────────────────────────────
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', default_rviz],
        parameters=[{'use_sim_time': use_sim_time}],
        output='screen',
        condition=IfCondition(use_rviz),
    )

    return LaunchDescription([
        # Declare all arguments first
        declare_use_sim_time,
        declare_use_rviz,
        declare_world_file,
        declare_spawn_x,
        declare_spawn_y,
        declare_spawn_yaw,

        # Launch in dependency order
        robot_state_publisher,  # must be before spawn (provides /robot_description)
        gazebo,
        ros_gz_bridge,
        spawn_robot,            # delayed 3s
        rviz,
    ])
