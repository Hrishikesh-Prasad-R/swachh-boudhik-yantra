cmake_minimum_required(VERSION 3.10)
project(vacuum_utils)

find_package(ament_cmake REQUIRED)
find_package(rclpy REQUIRED)

# Install all scripts as executables
install(
  PROGRAMS
    scripts/check_tf.py
    scripts/collect_metrics.py
    scripts/validate_urdf.sh
    scripts/validate_controllers.sh
    scripts/record_trajectory.py
    scripts/graphify.py
  DESTINATION lib/${PROJECT_NAME}
)



if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
