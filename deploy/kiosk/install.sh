#!/usr/bin/env bash
# Turn a headless Debian or Ubuntu box into an always-on monitor for the glance view.
#
#   sudo deploy/kiosk/install.sh http://192.168.1.185:8088 <KIOSK_TOKEN>
#
# What it does: installs cage (a one-window Wayland compositor, a few MB) and a Chromium build (Debian's
# apt package, or Google's .deb on Ubuntu where the apt package is a snap that does not start under cage),
# creates a "kiosk" user with no password, and starts a systemd service on tty7 that opens
# <url>/kiosk?token=<KIOSK_TOKEN>. The token sets a read-only cookie good for a year and drops out of
# the URL; the cookie lives in the kiosk user's Chromium profile, so reboots never ask for a sign-in.
# Disk: roughly 400 MB for the browser and 50 MB for cage and its libraries. Memory: a single tab,
# around 300 to 500 MB.
set -euo pipefail
URL="${1:?usage: install.sh <dashboard url> <KIOSK_TOKEN>}"
TOKEN="${2:?usage: install.sh <dashboard url> <KIOSK_TOKEN>}"
USER_NAME="${KIOSK_USER:-kiosk}"
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

# the token goes into a URL inside the unit file: it must be one line of plain characters
case "$TOKEN" in *$'\n'*)
  echo "The token argument has more than one line: .env probably has two KIOSK_TOKEN entries. Check: grep -n ^KIOSK_TOKEN .env" >&2
  exit 1 ;;
esac
TOKEN="${TOKEN//$'\r'/}"
TOKEN="${TOKEN#\'}"; TOKEN="${TOKEN%\'}"; TOKEN="${TOKEN#\"}"; TOKEN="${TOKEN%\"}"
case "$TOKEN" in
  ""|*[[:space:]]*|*[^A-Za-z0-9._-]*)
    echo "KIOSK_TOKEN must be one line of letters, digits, dots, dashes or underscores (got ${#TOKEN} characters)." >&2
    exit 1 ;;
esac
case "$URL" in http://*|https://*) ;; *) echo "dashboard url must start with http:// or https://" >&2; exit 1 ;; esac

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

# /kiosk rather than /glance: same one-screen view, plus the hidden cursor, the locked screen and the daily reload
unit="$(cat "$HERE/frankenstein-kiosk.service")"
unit="${unit//__KIOSK_USER__/$USER_NAME}"
unit="${unit//__BROWSER__/$BROWSER}"
unit="${unit//__URL__/${URL%/}/kiosk?token=$TOKEN}"
printf '%s\n' "$unit" > /etc/systemd/system/frankenstein-kiosk.service
chmod 600 /etc/systemd/system/frankenstein-kiosk.service   # the unit carries the kiosk token
systemctl daemon-reload
systemctl set-default graphical.target >/dev/null
systemctl enable frankenstein-kiosk.service >/dev/null
systemctl restart frankenstein-kiosk.service
sleep 3
systemctl --no-pager --lines=0 status frankenstein-kiosk.service || true
echo "frankenstein-kiosk is on tty7. Logs: journalctl -u frankenstein-kiosk -f"
