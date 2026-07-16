cmake_minimum_required(VERSION 3.10)
project(vacuum_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)

# Stage 1: No custom interfaces defined yet.
# Uncomment and add .msg / .srv / .action files as needed in later stages.
#
# rosidl_generate_interfaces(${PROJECT_NAME}
#   "msg/VacuumStatus.msg"
#   "srv/SetMode.srv"
#   "action/NavigateToGoal.action"
#   DEPENDENCIES std_msgs geometry_msgs
# )

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
