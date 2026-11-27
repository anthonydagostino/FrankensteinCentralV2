#!/usr/bin/env bash
# Turn a headless Debian or Ubuntu box into an always-on monitor for the glance view.
#
#   sudo deploy/kiosk/install.sh http://192.168.1.185:8088 <KIOSK_TOKEN>
#
# What it does: installs a plain X server (Xorg with xinit) and a Chromium build (Debian's apt package, or Google's
# .deb on Ubuntu where the apt package is a snap that does not start outside a desktop), creates a "kiosk" user
# with no password, and starts a systemd service on tty1 (in place of the login prompt there; a keyboard still gets
# a console on tty2 with Ctrl+Alt+F2) that opens <url>/kiosk?token=<KIOSK_TOKEN> full screen. The token sets a
# read-only cookie good for a year and drops out of the URL; the cookie lives in the kiosk user's Chromium profile,
# so reboots never ask for a sign-in.
# Disk: roughly 400 MB for the browser and 150 MB for X. Memory: a single tab, around 300 to 500 MB.
#
# KIOSK_BACKEND=cage picks the Wayland compositor instead of X (lighter, but Chrome crashes on the cage that
# Ubuntu 22.04 ships, so X is the default). KIOSK_INPUT=on lets a mouse and keyboard reach the dashboard; by
# default X ignores them, so nothing can be scrolled or clicked by accident.
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

BACKEND="${KIOSK_BACKEND:-x11}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
if [ "$BACKEND" = cage ]; then
  # Ubuntu and Debian build cage with Xwayland support and it refuses to start without the binary, even for a Wayland-only client
  apt-get install -y -q cage xwayland
else
  apt-get install -y -q xserver-xorg xserver-xorg-legacy xinit x11-xserver-utils
  # let the unprivileged kiosk user start X on its tty (the setuid wrapper then runs the server with root rights)
  printf 'allowed_users=anybody\nneeds_root_rights=yes\n' > /etc/X11/Xwrapper.config
  mkdir -p /etc/X11/xorg.conf.d
  if [ "${KIOSK_INPUT:-off}" = on ]; then
    rm -f /etc/X11/xorg.conf.d/10-frankenstein-kiosk-no-input.conf
  else
    # a display nobody touches: X ignores every mouse and keyboard, so a nudge cannot scroll or click anything.
    # Ctrl+Alt+F2 at the box stops working too; use SSH, or "sudo chvt 2", for a console. KIOSK_INPUT=on keeps input.
    cat > /etc/X11/xorg.conf.d/10-frankenstein-kiosk-no-input.conf <<'XORG'
Section "ServerFlags"
    Option "AutoAddDevices" "false"
EndSection
XORG
  fi
fi
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
usermod -aG video,input,render,tty "$USER_NAME" 2>/dev/null || true

# /kiosk rather than /glance: same one-screen view, plus the hidden cursor, the locked screen and the daily reload
template="$HERE/frankenstein-kiosk.service"; [ "$BACKEND" = cage ] && template="$HERE/frankenstein-kiosk-cage.service"
unit="$(cat "$template")"
unit="${unit//__KIOSK_USER__/$USER_NAME}"
unit="${unit//__BROWSER__/$BROWSER}"
unit="${unit//__URL__/${URL%/}/kiosk?token=$TOKEN}"
printf '%s\n' "$unit" > /etc/systemd/system/frankenstein-kiosk.service
session="$(cat "$HERE/frankenstein-kiosk-session")"
printf '%s\n' "${session//__BROWSER__/$BROWSER}" > /usr/local/bin/frankenstein-kiosk-session
chmod 755 /usr/local/bin/frankenstein-kiosk-session
chmod 600 /etc/systemd/system/frankenstein-kiosk.service   # the unit carries the kiosk token
systemctl daemon-reload
systemctl set-default graphical.target >/dev/null
systemctl enable frankenstein-kiosk.service >/dev/null
systemctl restart frankenstein-kiosk.service
sleep 3
systemctl --no-pager --lines=0 status frankenstein-kiosk.service || true
echo "frankenstein-kiosk is on tty1 (Ctrl+Alt+F2 for a console). Logs: journalctl -u frankenstein-kiosk -f and journalctl _UID=$(id -u "$USER_NAME") -f"
