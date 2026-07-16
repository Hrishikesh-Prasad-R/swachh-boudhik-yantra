#!/usr/bin/env python3
"""
spawn_robot.launch.py
─────────────────────
Standalone robot spawner for vacuum_gazebo.

Use this when Gazebo is already running and you only need to spawn the robot.
For the full simulation stack (Gazebo + spawn + bridge + RViz), use
vacuum_bringup/launch/sim.launch.py instead.

Usage:
  ros2 launch vacuum_gazebo spawn_robot.launch.py
  ros2 launch vacuum_gazebo spawn_robot.launch.py spawn_x:=1.0 spawn_y:=2.0
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():

    pkg_description = get_package_share_directory('vacuum_description')
    urdf_file = os.path.join(pkg_description, 'urdf', 'vacuum.urdf.xacro')

    # ── Spawn position arguments ───────────────────────────────────
    declare_spawn_x = DeclareLaunchArgument(
        'spawn_x', default_value='0.0',
        description='Robot spawn X position in world frame')
    declare_spawn_y = DeclareLaunchArgument(
        'spawn_y', default_value='0.0',
        description='Robot spawn Y position in world frame')
    declare_spawn_z = DeclareLaunchArgument(
        'spawn_z', default_value='0.0',
        description='Robot spawn Z position in world frame (0 = ground level)')
    declare_spawn_yaw = DeclareLaunchArgument(
        'spawn_yaw', default_value='0.0',
        description='Robot spawn yaw (heading) in radians')
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='Use simulation clock')

    spawn_x   = LaunchConfiguration('spawn_x')
    spawn_y   = LaunchConfiguration('spawn_y')
    spawn_z   = LaunchConfiguration('spawn_z')
    spawn_yaw = LaunchConfiguration('spawn_yaw')
    use_sim_time = LaunchConfiguration('use_sim_time')

    # ── Robot State Publisher ──────────────────────────────────────
    # Publishes /robot_description topic and static TF for fixed joints
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': ParameterValue(
                Command(['xacro ', urdf_file]),
                value_type=str
            ),
            'use_sim_time': use_sim_time,
        }],
    )

    # ── Spawn into Gazebo ──────────────────────────────────────────
    # ros_gz_sim/create reads /robot_description and spawns the model
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        name='spawn_vacuum_robot',
        arguments=[
            '-name',  'vacuum_robot',
            '-topic', '/robot_description',
            '-x',     spawn_x,
            '-y',     spawn_y,
            '-z',     spawn_z,
            '-Y',     spawn_yaw,
        ],
        output='screen',
    )

    return LaunchDescription([
        declare_spawn_x,
        declare_spawn_y,
        declare_spawn_z,
        declare_spawn_yaw,
        declare_use_sim_time,
        robot_state_publisher,
        spawn_robot,
    ])
