#!/bin/bash
# Swacch Robot HMI - Setup Script

echo "=== Swacch Robot HMI Setup ==="

# 1. Install dependencies
echo "Installing GTK4 and build tools..."
sudo apt update
sudo apt install -y build-essential cmake pkg-config libgtk-4-dev

# 2. Arduino CLI (optional, for uploading firmware)
if ! command -v arduino-cli &> /dev/null; then
    echo "Arduino-CLI not found. Installing..."
    curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
    export PATH=$PATH:$HOME/bin
fi

# 3. Serial Port Permissions
echo "Adding user to dialout group for serial access..."
sudo usermod -a -G dialout $USER

echo "=== Setup Complete ==="
echo "Please REBOOT or LOG OUT and back in for group changes to take effect."
