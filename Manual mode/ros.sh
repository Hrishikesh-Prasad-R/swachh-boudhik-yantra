#!/bin/bash
echo "Entering ROS 2 Humble Environment..."
distrobox enter ros-dev -- bash -c "source /opt/ros/humble/setup.bash; exec bash"
