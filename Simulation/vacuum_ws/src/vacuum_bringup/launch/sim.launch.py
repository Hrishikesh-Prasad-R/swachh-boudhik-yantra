#!/usr/bin/env python3
# FIXED: ParameterValue wrapper — required in ROS2 Jazzy for XML parameters
# Without this, launch parses URDF XML as YAML and throws an error.
"""
sim.launch.py — MASTER simulation launch file (Stage 3)
────────────────────────────────────────────────────
Orchestrates the complete simulation stack in this order:

  1. robot_state_publisher  — reads URDF, publishes /robot_description + TF
  2. Gazebo Harmonic        — physics simulation (loads gz_ros2_control plugin)
  3. ros_gz_bridge          — /clock + camera topics (Stage 3)
  4. spawn_robot            — places the robot into Gazebo (delayed 3s)
  5. controllers            — spawns JSB + diff_drive_controller + camera diag
  6. RViz2 (optional)       — visualisation

Stage 3 changes:
  - D435i RGB-D camera sensor active (rgbd_camera plugin)
  - 5 camera topics bridged (image, depth, points, 2x camera_info)
  - camera_diagnostics_node started at t=10s

Launch arguments:
  use_sim_time       [true]           — all nodes use /clock from Gazebo
  use_rviz           [true]           — launch RViz2 alongside Gazebo
  world              [room]           — shorthand: room/apartment/office/corridor
  world_file         [empty_world.sdf]— override with absolute SDF path
  spawn_x/y/yaw      [0.0]           — robot initial pose
  enable_odom_noise  [false]          — Gaussian noise on /odom_noisy
  enable_diagnostics [true]           — enable motion diagnostics node

Usage:
  ros2 launch vacuum_bringup sim.launch.py
  ros2 launch vacuum_bringup sim.launch.py world:=apartment
  ros2 launch vacuum_bringup sim.launch.py world:=office use_rviz:=false
  ros2 launch vacuum_bringup sim.launch.py world_file:=/abs/path/custom.sdf
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
    PythonExpression,
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

    # ── World file map (shorthand -> SDF path) ─────────────────────
    # Add new environments here; world_file arg overrides all.
    WORLD_MAP = {
        'room':      os.path.join(pkg_gazebo, 'worlds', 'empty_world.sdf'),
        'apartment': os.path.join(pkg_gazebo, 'worlds', 'apartment.sdf'),
        'office':    os.path.join(pkg_gazebo, 'worlds', 'office.sdf'),
        'corridor':  os.path.join(pkg_gazebo, 'worlds', 'corridor.sdf'),
    }

    # ── Default paths ──────────────────────────────────────────────
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
    declare_world = DeclareLaunchArgument(
        'world', default_value='room',
        description='World shorthand: room | apartment | office | corridor'
                    ' (ignored if world_file is set)')

    # Dynamic world path resolution based on 'world' argument
    world = LaunchConfiguration('world')
    dynamic_world_default = PythonExpression([
        "'", os.path.join(pkg_gazebo, 'worlds'), "/' + (",
        "'empty_world.sdf' if '", world, "' == 'room' else ",
        "'apartment.sdf' if '", world, "' == 'apartment' else ",
        "'office.sdf' if '", world, "' == 'office' else ",
        "'corridor.sdf' if '", world, "' == 'corridor' else 'empty_world.sdf')"
    ])

    declare_world_file = DeclareLaunchArgument(
        'world_file', default_value=dynamic_world_default,
        description='Absolute path to the Gazebo .sdf world file (overrides world:=)')
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
        declare_world,
        declare_world_file,
        declare_spawn_x,
        declare_spawn_y,
        declare_spawn_yaw,
        declare_enable_noise,
        declare_enable_diagnostics,

        # Launch in dependency order
        robot_state_publisher,  # must be before spawn (provides /robot_description)
        gazebo,
        ros_gz_bridge,          # /clock + camera topics (Stage 3)
        spawn_robot,            # delayed 3s — triggers gz_ros2_control init
        controllers,            # delayed internally (5s JSB, 6s DDC, 10s camera_diag)
        rviz,
    ])
