cmake_minimum_required(VERSION 3.10)
project(SwacchHMI_Final VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find GTK4
find_package(PkgConfig REQUIRED)
pkg_check_modules(GTK4 REQUIRED gtk4)

# Source files
set(HMI_SOURCES
    src/main.cpp
    src/gui.cpp
    src/callbacks.cpp
    src/serial_comm.cpp
    src/logger.cpp
)

# Executable
add_executable(swacch_hmi ${HMI_SOURCES})

# Include & link
target_include_directories(swacch_hmi PRIVATE
    ${GTK4_INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_directories(swacch_hmi PRIVATE ${GTK4_LIBRARY_DIRS})

target_link_libraries(swacch_hmi PRIVATE ${GTK4_LIBRARIES})

target_compile_options(swacch_hmi PRIVATE
    ${GTK4_CFLAGS_OTHER}
    -Wall
    -O2
)

# Install
install(TARGETS swacch_hmi DESTINATION bin)
