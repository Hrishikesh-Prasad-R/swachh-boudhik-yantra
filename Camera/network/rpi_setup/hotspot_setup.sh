#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# hotspot_setup.sh — Configure RPi5 wlan0 as a WiFi Access Point
#
# Creates SSID "swachh-bot" with a fixed IP 192.168.4.1
# GPU system connects to this and gets IP 192.168.4.x via DHCP
#
# Run once as root (or with sudo) on the Raspberry Pi 5.
# Usage:  sudo bash hotspot_setup.sh [--ssid NAME] [--password PASS]
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Defaults (override via CLI flags) ─────────────────────────────────────────
SSID="swachh-bot"
PASSWORD="swachh2024"
INTERFACE="wlan0"
AP_IP="192.168.4.1"
DHCP_RANGE_START="192.168.4.100"
DHCP_RANGE_END="192.168.4.200"
DHCP_LEASE="12h"

# ── Parse CLI args ─────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --ssid)     SSID="$2";     shift 2 ;;
        --password) PASSWORD="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }

# ── Root check ─────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR]${NC} Run this script as root: sudo bash $0"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Swachh Boudhik Yantra — RPi5 Hotspot Setup         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
info "SSID:       $SSID"
info "Password:   $PASSWORD"
info "Interface:  $INTERFACE"
info "AP IP:      $AP_IP"
info "DHCP Range: $DHCP_RANGE_START – $DHCP_RANGE_END"
echo ""

# ── Step 1: Install dependencies ──────────────────────────────────────────────
info "Installing hostapd and dnsmasq..."
apt-get update -qq
apt-get install -y hostapd dnsmasq iptables-persistent
success "Dependencies installed."

# ── Step 2: Stop services while configuring ───────────────────────────────────
info "Stopping services..."
systemctl stop hostapd dnsmasq 2>/dev/null || true
systemctl unmask hostapd
rfkill unblock wlan 2>/dev/null || true

# ── Step 3: Static IP for wlan0 ───────────────────────────────────────────────
info "Configuring static IP on $INTERFACE..."

# Prevent dhcpcd from managing wlan0's IP (it conflicts with AP mode)
DHCPCD_CONF="/etc/dhcpcd.conf"
if ! grep -q "interface $INTERFACE" "$DHCPCD_CONF" 2>/dev/null; then
    cat >> "$DHCPCD_CONF" << EOF

# Swachh hotspot — static IP for AP mode
interface $INTERFACE
    static ip_address=$AP_IP/24
    nohook wpa_supplicant
EOF
    success "dhcpcd.conf updated."
else
    warn "dhcpcd.conf already has $INTERFACE entry — skipping."
fi

# ── Step 4: Configure dnsmasq (DHCP server) ───────────────────────────────────
info "Configuring dnsmasq..."
DNSMASQ_CONF="/etc/dnsmasq.conf"
# Backup original
cp "$DNSMASQ_CONF" "${DNSMASQ_CONF}.backup.$(date +%s)" 2>/dev/null || true

cat > "$DNSMASQ_CONF" << EOF
# Swachh Boudhik Yantra — dnsmasq config
# Only serve DHCP on the hotspot interface
interface=$INTERFACE
dhcp-range=$DHCP_RANGE_START,$DHCP_RANGE_END,255.255.255.0,$DHCP_LEASE
dhcp-option=3,$AP_IP       # default gateway = RPi
dhcp-option=6,$AP_IP       # DNS server = RPi
domain=swachh.local
address=/rpi.swachh.local/$AP_IP
log-queries
log-dhcp
EOF
success "dnsmasq configured."

# ── Step 5: Configure hostapd ─────────────────────────────────────────────────
info "Configuring hostapd..."
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
cat > "$HOSTAPD_CONF" << EOF
# Swachh Boudhik Yantra — hostapd config
interface=$INTERFACE
driver=nl80211
ssid=$SSID
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$PASSWORD
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
# Country code — required for 5GHz; change to your country
country_code=IN
EOF

# Point hostapd to the config
sed -i 's|#DAEMON_CONF=""|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' \
    /etc/default/hostapd 2>/dev/null || true
success "hostapd configured."

# ── Step 6: Enable IP forwarding (optional internet sharing via eth0) ─────────
info "Enabling IP forwarding..."
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-swachh-forward.conf
sysctl -p /etc/sysctl.d/99-swachh-forward.conf

# NAT rule: share eth0 internet through the hotspot (comment out if not needed)
# iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
# iptables -A FORWARD -i eth0 -o $INTERFACE -m state --state RELATED,ESTABLISHED -j ACCEPT
# iptables -A FORWARD -i $INTERFACE -o eth0 -j ACCEPT
# netfilter-persistent save

# ── Step 7: Enable services on boot ───────────────────────────────────────────
info "Enabling hostapd and dnsmasq on boot..."
systemctl enable hostapd
systemctl enable dnsmasq

# ── Step 8: Restart services ──────────────────────────────────────────────────
info "Starting services..."
systemctl restart dhcpcd
sleep 2
systemctl start hostapd
systemctl start dnsmasq
sleep 2

# ── Step 9: Verify ────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────────────────────"
info "Verifying setup..."

if systemctl is-active --quiet hostapd; then
    success "hostapd is RUNNING ✓"
else
    echo -e "${RED}[FAIL]${NC} hostapd failed to start. Check: journalctl -u hostapd -n 30"
fi

if systemctl is-active --quiet dnsmasq; then
    success "dnsmasq is RUNNING ✓"
else
    echo -e "${RED}[FAIL]${NC} dnsmasq failed to start. Check: journalctl -u dnsmasq -n 30"
fi

CURRENT_IP=$(ip addr show $INTERFACE | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
if [[ "$CURRENT_IP" == "$AP_IP" ]]; then
    success "$INTERFACE IP is $AP_IP ✓"
else
    warn "$INTERFACE IP is '$CURRENT_IP' (expected $AP_IP) — may need reboot."
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Hotspot Setup Complete!                            ║"
echo "║                                                      ║"
echo "║   SSID:     $SSID"
echo "║   Password: $PASSWORD"
echo "║   RPi IP:   $AP_IP"
echo "║                                                      ║"
echo "║   On GPU system (Windows):                           ║"
echo "║   1. Connect WiFi → $SSID"
echo "║   2. RPi is always at $AP_IP                  ║"
echo "║   3. Run: python check_cuda.py                       ║"
echo "║   4. Run: python gpu_worker.py                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Save config summary ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cat > "$SCRIPT_DIR/hotspot_info.txt" << EOF
Swachh Boudhik Yantra — Hotspot Configuration
==============================================
SSID:              $SSID
Password:          $PASSWORD
Interface:         $INTERFACE
RPi IP (fixed):    $AP_IP
DHCP Range:        $DHCP_RANGE_START – $DHCP_RANGE_END
Created:           $(date)
EOF
success "Config saved to hotspot_info.txt"
