cmake_minimum_required(VERSION 3.8)
project(vacuum_exploration)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

# Install Python package
ament_python_install_package(${PROJECT_NAME})

# Install Python executables (nodes)
install(PROGRAMS
  vacuum_exploration/frontier_detector.py
  vacuum_exploration/exploration_manager.py
  vacuum_exploration/frontier_visualizer.py
  vacuum_exploration/exploration_metrics.py
  DESTINATION lib/${PROJECT_NAME}
)

# Install config and launch files
install(DIRECTORY
  config
  launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
