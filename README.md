# Swachh Boudhik Yantra

HMI and motor controller for an autonomous cleaning robot. The system has two parts — a GTK4 touchscreen interface running on a Jetson Orin Nano, and Arduino firmware that drives two BLDC motors and peripherals over USB serial.

## Structure

```
src/        - C++ source files (GUI, callbacks, serial, logger)
include/    - Header files
arduino/    - Arduino motor controller firmware
scripts/    - Build and setup scripts
```

## Setup

```
bash scripts/setup.sh
```

Installs GTK4, cmake, build tools, and serial port permissions. Reboot after running.

## Build and Run

```
bash scripts/run.sh
```

Auto-detects the Arduino serial port, builds if needed, and launches the HMI.

## Hardware

- Jetson Orin Nano (runs the HMI)
- Arduino (motor control)
- 2x BLDC motors with relay direction control
- Peripherals: vacuum, arm, wiper, UV

## Serial Protocol

Commands are newline-terminated, 115200 baud. Movement: `MOVE:FORWARD`, `MOVE:LEFT`, etc. Peripherals: `VACUUM:ON`, `ARM:OFF`, etc. Speed: `SPEED:1` to `SPEED:9`. Safety: `ESTOP`, `RESET`. Arduino replies with `ACK:<command>` and sends periodic `STATUS:` updates.
