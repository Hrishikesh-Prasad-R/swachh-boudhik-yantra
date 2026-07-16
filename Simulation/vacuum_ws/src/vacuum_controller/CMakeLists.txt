cmake_minimum_required(VERSION 3.10)
project(vacuum_controller)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclpy REQUIRED)

# Install controller configuration
install(
  DIRECTORY config/
  DESTINATION share/${PROJECT_NAME}/config
)

# Install launch files
install(
  DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

# Install Python package (odometry_noise_node, motion_diagnostics_node)
ament_python_install_package(${PROJECT_NAME})

# Install Python node scripts as executables
install(
  PROGRAMS
    vacuum_controller/odometry_noise_node.py
    vacuum_controller/motion_diagnostics_node.py
    vacuum_controller/camera_diagnostics_node.py
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
