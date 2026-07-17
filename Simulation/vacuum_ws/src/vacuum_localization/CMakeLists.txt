cmake_minimum_required(VERSION 3.8)
project(vacuum_localization)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(${PROJECT_NAME})

install(
  PROGRAMS
    vacuum_localization/localization_monitor.py
    vacuum_localization/recovery_monitor.py
    vacuum_localization/localization_metrics.py
  DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
