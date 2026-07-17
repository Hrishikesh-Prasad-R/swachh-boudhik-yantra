cmake_minimum_required(VERSION 3.8)
project(vacuum_nav2)

find_package(ament_cmake REQUIRED)

# Install config, behavior trees, and launch files
install(DIRECTORY
  config
  behavior_trees
  launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
