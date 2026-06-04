#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# hotspot_stop.sh — Restore RPi5 wlan0 to normal WiFi client mode
#
# Run as root. Stops the hotspot so RPi can join a regular WiFi network again.
# Usage:  sudo bash hotspot_stop.sh
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }

if [[ $EUID -ne 0 ]]; then
    echo "[ERROR] Run as root: sudo bash $0"
    exit 1
fi

info "Stopping hotspot services..."
systemctl stop hostapd dnsmasq 2>/dev/null || true
systemctl disable hostapd dnsmasq 2>/dev/null || true

info "Removing static IP configuration from dhcpcd.conf..."
# Remove the block added by hotspot_setup.sh
sed -i '/# Swachh hotspot/,/nohook wpa_supplicant/d' /etc/dhcpcd.conf

info "Restoring dnsmasq to default..."
# Restore from backup if it exists
BACKUP=$(ls /etc/dnsmasq.conf.backup.* 2>/dev/null | sort | tail -1)
if [[ -n "$BACKUP" ]]; then
    cp "$BACKUP" /etc/dnsmasq.conf
    info "Restored dnsmasq.conf from $BACKUP"
fi

info "Restarting dhcpcd to re-enable DHCP on wlan0..."
systemctl restart dhcpcd

echo ""
echo -e "${GREEN}Hotspot stopped. RPi5 will reconnect to saved WiFi networks.${NC}"
echo "You may need to reconnect manually via: nmcli, raspi-config, or the desktop."
