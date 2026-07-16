#!/usr/bin/env python3
# FIXED: ParameterValue wrapper — required in ROS2 Jazzy for XML parameters
# Without this, launch parses URDF XML as YAML and throws an error.
"""
sim.launch.py — MASTER simulation launch file (Stage 2)
────────────────────────────────────────────────────────
Orchestrates the complete simulation stack in this order:

  1. robot_state_publisher  — reads URDF, publishes /robot_description + TF
  2. Gazebo Harmonic        — physics simulation (loads gz_ros2_control plugin)
  3. ros_gz_bridge          — /clock bridge only (Stage 2: ros2_control owns robot topics)
  4. spawn_robot            — places the robot into Gazebo (delayed 3s)
  5. controllers            — spawns JSB + diff_drive_controller (delayed 5–7s)
  6. RViz2 (optional)       — visualisation

Stage 2 changes from Stage 1:
  - gz_ros2_control replaces DiffDrive/JSP gz plugins
  - Controllers launch (vacuum_controller) included
  - Bridge reduced to /clock only

Launch arguments:
  use_sim_time       [true]  — all nodes use /clock from Gazebo
  use_rviz           [true]  — launch RViz2 alongside Gazebo
  world_file         [empty_world.sdf] — path to Gazebo world file
  spawn_x/y/yaw      [0.0]  — robot initial pose
  enable_odom_noise  [false] — enable Gaussian noise on /odom_noisy
  enable_diagnostics [true]  — enable motion diagnostics node

Usage:
  ros2 launch vacuum_bringup sim.launch.py
  ros2 launch vacuum_bringup sim.launch.py use_rviz:=false
  ros2 launch vacuum_bringup sim.launch.py enable_odom_noise:=true
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
)
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.actions import Node


def generate_launch_description():

    # ── Package share directories ──────────────────────────────────
    pkg_description  = get_package_share_directory('vacuum_description')
    pkg_gazebo       = get_package_share_directory('vacuum_gazebo')
    pkg_bringup      = get_package_share_directory('vacuum_bringup')
    pkg_controller   = get_package_share_directory('vacuum_controller')
    pkg_ros_gz_sim   = get_package_share_directory('ros_gz_sim')

    # ── Default paths ──────────────────────────────────────────────
    default_world   = os.path.join(pkg_gazebo,  'worlds', 'empty_world.sdf')
    default_rviz    = os.path.join(pkg_bringup, 'config', 'rviz_config.rviz')
    urdf_file       = os.path.join(pkg_description, 'urdf', 'vacuum.urdf.xacro')
    bridge_config   = os.path.join(pkg_gazebo,  'config', 'gz_bridge.yaml')
    controllers_launch = os.path.join(pkg_controller, 'launch', 'controllers.launch.py')

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
    declare_enable_noise = DeclareLaunchArgument(
        'enable_odom_noise', default_value='false',
        description='Enable Gaussian noise on /odom_noisy')
    declare_enable_diagnostics = DeclareLaunchArgument(
        'enable_diagnostics', default_value='true',
        description='Enable motion diagnostics node')

    use_sim_time       = LaunchConfiguration('use_sim_time')
    use_rviz           = LaunchConfiguration('use_rviz')
    world_file         = LaunchConfiguration('world_file')
    spawn_x            = LaunchConfiguration('spawn_x')
    spawn_y            = LaunchConfiguration('spawn_y')
    spawn_yaw          = LaunchConfiguration('spawn_yaw')
    enable_odom_noise  = LaunchConfiguration('enable_odom_noise')
    enable_diagnostics = LaunchConfiguration('enable_diagnostics')

    # ── 1. Robot State Publisher ───────────────────────────────────
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
    # gz_ros2_control plugin starts automatically when Gazebo loads the URDF.
    # -r flag = run immediately (no pause on startup).
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': ['-r ', world_file],
            'on_exit_shutdown': 'true',
        }.items(),
    )

    # ── 3. ROS-Gazebo Bridge (/clock only) ─────────────────────────
    # Stage 2: ros2_control publishes /odom, /tf, /joint_states natively.
    # Only /clock still requires bridging for use_sim_time synchronisation.
    ros_gz_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_bridge',
        parameters=[{'config_file': bridge_config}],
        output='screen',
    )

    # ── 4. Spawn robot (delayed 3s) ────────────────────────────────
    # 3-second delay allows Gazebo physics to fully initialise before spawn.
    # gz_ros2_control::GazeboSimROS2ControlPlugin starts when model spawns.
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
                    '-z',     '0.0',
                    '-Y',     spawn_yaw,
                ],
                output='screen',
            )
        ],
    )

    # ── 5. Controllers (from vacuum_controller package) ────────────
    # Controllers are spawned at 5s (JSB) and 6s (DDC) by the included launch.
    # This gives Gazebo + gz_ros2_control time to create /controller_manager.
    controllers = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(controllers_launch),
        launch_arguments={
            'use_sim_time':     use_sim_time,
            'enable_odom_noise': enable_odom_noise,
            'enable_diagnostics': enable_diagnostics,
        }.items(),
    )

    # ── 6. RViz2 (conditional) ─────────────────────────────────────
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
        declare_enable_noise,
        declare_enable_diagnostics,

        # Launch in dependency order
        robot_state_publisher,  # must be before spawn (provides /robot_description)
        gazebo,
        ros_gz_bridge,          # /clock only in Stage 2
        spawn_robot,            # delayed 3s — triggers gz_ros2_control init
        controllers,            # delayed internally (5s JSB, 6s DDC)
        rviz,
    ])
