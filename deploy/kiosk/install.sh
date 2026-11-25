#!/usr/bin/env bash
# Turn a headless Debian or Ubuntu box into an always-on monitor for the glance view.
#
#   sudo deploy/kiosk/install.sh http://192.168.1.185:8088 <KIOSK_TOKEN>
#
# What it does: installs cage (a one-window Wayland compositor, a few MB) and a Chromium build (Debian's
# apt package, or Google's .deb on Ubuntu where the apt package is a snap that does not start under cage),
# creates a "kiosk" user with no password, and starts a systemd service on tty7 that opens
# <url>/glance?token=<KIOSK_TOKEN>. The token sets a read-only cookie good for a year and drops out of
# the URL; the cookie lives in the kiosk user's Chromium profile, so reboots never ask for a sign-in.
# Disk: roughly 400 MB for the browser and 50 MB for cage and its libraries. Memory: a single tab,
# around 300 to 500 MB.
set -euo pipefail
URL="${1:?usage: install.sh <dashboard url> <KIOSK_TOKEN>}"
TOKEN="${2:?usage: install.sh <dashboard url> <KIOSK_TOKEN>}"
USER_NAME="${KIOSK_USER:-kiosk}"
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q cage
if apt-cache show chromium 2>/dev/null | grep -q '^Version:' && ! grep -qi ubuntu /etc/os-release; then
  apt-get install -y -q chromium
  BROWSER=/usr/bin/chromium
else
  # Ubuntu: the apt "chromium" is a snap stub; Google's .deb runs as a normal binary
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/chrome.deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  apt-get install -y -q "$tmp/chrome.deb"
  rm -rf "$tmp"
  BROWSER=/usr/bin/google-chrome-stable
fi

id "$USER_NAME" >/dev/null 2>&1 || useradd -m -s /usr/sbin/nologin "$USER_NAME"
usermod -aG video,input,render "$USER_NAME" 2>/dev/null || true

sed -e "s|__KIOSK_USER__|$USER_NAME|g" -e "s|__BROWSER__|$BROWSER|g" -e "s|__URL__|${URL%/}/glance?token=$TOKEN|g" \
  "$HERE/frankenstein-kiosk.service" > /etc/systemd/system/frankenstein-kiosk.service
chmod 600 /etc/systemd/system/frankenstein-kiosk.service   # the unit carries the kiosk token
systemctl daemon-reload
systemctl set-default graphical.target >/dev/null
systemctl enable --now frankenstein-kiosk.service
echo "frankenstein-kiosk is running on tty7. Logs: journalctl -u frankenstein-kiosk -f"
