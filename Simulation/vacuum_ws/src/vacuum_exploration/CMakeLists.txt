cmake_minimum_required(VERSION 3.8)
project(vacuum_exploration)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

# Install Python package (makes the vacuum_exploration module importable)
ament_python_install_package(${PROJECT_NAME})

# Install Python nodes WITHOUT the .py extension so that ROS2 can find them
# as 'frontier_detector', 'exploration_manager', etc. in the libexec directory.
# The RENAME keyword strips the extension on install.
install(PROGRAMS
  vacuum_exploration/frontier_detector.py
  RENAME frontier_detector
  DESTINATION lib/${PROJECT_NAME}
)
install(PROGRAMS
  vacuum_exploration/exploration_manager.py
  RENAME exploration_manager
  DESTINATION lib/${PROJECT_NAME}
)
install(PROGRAMS
  vacuum_exploration/frontier_visualizer.py
  RENAME frontier_visualizer
  DESTINATION lib/${PROJECT_NAME}
)
install(PROGRAMS
  vacuum_exploration/exploration_metrics.py
  RENAME exploration_metrics
  DESTINATION lib/${PROJECT_NAME}
)

# Install config and launch files
install(DIRECTORY
  config
  launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
