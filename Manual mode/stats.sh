#!/bin/bash
# stats.sh — Swachh Robot System Metrics

# 1. Temperature
TEMP=$(cat /sys/class/thermal/thermal_zone0/temp)
TEMP_C=$(echo "scale=1; $TEMP/1000" | bc -l)

# 2. CPU Usage
CPU=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')

# 3. RAM Usage
RAM=$(free -m | awk '/Mem:/ { printf "%d/%dMB (%.1f%%)", $3, $2, $3*100/$2 }')

# 4. Disk Usage
DISK=$(df -h / | awk '/\// { print $3 "/" $2 " (" $5 ")" }')

echo "------------------------------------------"
echo "   Swachh Robot RPi 5 Status"
echo "------------------------------------------"
echo "   Temp:  ${TEMP_C}°C"
echo "   CPU:   ${CPU}%"
echo "   RAM:   ${RAM}"
echo "   Disk:  ${DISK}"
echo "------------------------------------------"
