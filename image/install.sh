#!/bin/bash
# Turn Raspberry Pi OS Lite (64-bit, Bookworm or Trixie) into an AudioTarget
# appliance: tracker service, spoken menu, Bluetooth audio, belt buttons.
#
# Used two ways:
#   - by the SD-card image build (pi-gen, inside a chroot)
#   - on a running Pi:  sudo ./image/install.sh     (from a checkout of the repo)
#
# Safe to run again to update.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER=audiotarget
APP_HOME=/var/lib/audiotarget
VENV=/opt/audiotarget/venv
BOOT=/boot/firmware
IN_CHROOT="${AUDIOTARGET_IN_CHROOT:-0}"

if [ "$(id -u)" -ne 0 ]; then
	echo "run as root (sudo)" >&2
	exit 1
fi
if [ ! -f "$SRC/pi/audiotarget/__init__.py" ]; then
	echo "can't find the AudioTarget source next to this script ($SRC)" >&2
	exit 1
fi
[ -d "$BOOT" ] || BOOT=/boot

echo "== packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
# Package names that differ between Bookworm and Trixie.
POLKIT=polkitd
apt-cache show polkitd >/dev/null 2>&1 || POLKIT=policykit-1
apt-get install -y --no-install-recommends \
	python3 python3-venv python3-pip \
	python3-numpy python3-opencv python3-serial python3-evdev \
	python3-picamera2 python3-sounddevice \
	espeak-ng \
	pipewire pipewire-alsa pipewire-pulse wireplumber libspa-0.2-bluetooth \
	bluez alsa-utils "$POLKIT"

echo "== app user"
if ! id "$APP_USER" >/dev/null 2>&1; then
	useradd --system --create-home --home-dir "$APP_HOME" --shell /usr/sbin/nologin "$APP_USER"
fi
for g in video input dialout bluetooth audio gpio render; do
	getent group "$g" >/dev/null && usermod -aG "$g" "$APP_USER"
done

echo "== python environment"
# System OpenCV / picamera2 come from apt; the venv sees them.
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --no-cache-dir --upgrade pip >/dev/null
"$VENV/bin/python" -c "import bleak" 2>/dev/null || "$VENV/bin/pip" install --no-cache-dir "bleak>=0.21,<2"
"$VENV/bin/python" -c "import cv2, cv2.aruco" 2>/dev/null || \
	"$VENV/bin/pip" install --no-cache-dir "opencv-contrib-python-headless>=4.7,<6"
# Faster ML inference than OpenCV's DNN module; optional, so don't fail the install.
"$VENV/bin/python" -c "import onnxruntime" 2>/dev/null || \
	"$VENV/bin/pip" install --no-cache-dir "onnxruntime>=1.17,<2" || echo "onnxruntime not installed; ML will use OpenCV"
"$VENV/bin/pip" install --no-cache-dir --no-deps --force-reinstall "$SRC/pi"

echo "== config"
install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$APP_HOME" "$APP_HOME/models"
if [ ! -f "$APP_HOME/audiotarget.toml" ]; then
	install -o "$APP_USER" -g "$APP_USER" -m 0640 "$SRC/image/rootfs/audiotarget.toml" \
		"$APP_HOME/audiotarget.toml"
fi

echo "== services"
UNIT_DIR="$APP_HOME/.config/systemd/user"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_HOME/.config" "$APP_HOME/.config/systemd" \
	"$UNIT_DIR" "$UNIT_DIR/default.target.wants"
install -o "$APP_USER" -g "$APP_USER" -m 0644 "$SRC/image/rootfs/audiotarget.service" \
	"$UNIT_DIR/audiotarget.service"
ln -sf ../audiotarget.service "$UNIT_DIR/default.target.wants/audiotarget.service"
chown -h "$APP_USER:$APP_USER" "$UNIT_DIR/default.target.wants/audiotarget.service"

# Start the user's services (PipeWire + AudioTarget) at boot, with nobody logged in.
install -d /var/lib/systemd/linger
touch "/var/lib/systemd/linger/$APP_USER"

# WirePlumber normally only enables Bluetooth audio for a logged-in seat user;
# this headless user needs it regardless. (0.5 and 0.4 config styles.)
WP="$APP_HOME/.config/wireplumber"
install -d -o "$APP_USER" -g "$APP_USER" "$WP" "$WP/wireplumber.conf.d" "$WP/bluetooth.lua.d"
install -o "$APP_USER" -g "$APP_USER" -m 0644 "$SRC/image/rootfs/wireplumber-50-headless-bluez.conf" \
	"$WP/wireplumber.conf.d/50-headless-bluez.conf"
install -o "$APP_USER" -g "$APP_USER" -m 0644 "$SRC/image/rootfs/wireplumber-50-headless-bluez.lua" \
	"$WP/bluetooth.lua.d/50-headless-bluez.lua"

# Let the app user shut down / restart from the voice menu, nothing else.
install -d /etc/polkit-1/rules.d
install -m 0644 "$SRC/image/rootfs/50-audiotarget.rules" /etc/polkit-1/rules.d/50-audiotarget.rules

systemctl enable bluetooth.service >/dev/null 2>&1 || true

echo "== boot config"
CONFIG_TXT="$BOOT/config.txt"
if [ -f "$CONFIG_TXT" ] && ! grep -q "AudioTarget begin" "$CONFIG_TXT"; then
	cat "$SRC/image/rootfs/config.txt.append" >> "$CONFIG_TXT"
fi
# The UART talks to the gun module, so it can't also be a login console.
if [ -f "$BOOT/cmdline.txt" ]; then
	sed -i -E 's/console=(serial0|ttyAMA0|ttyS0),[0-9]+ ?//g' "$BOOT/cmdline.txt"
fi

if [ "$IN_CHROOT" != "1" ] && [ -d /run/systemd/system ]; then
	echo "== starting"
	systemctl start "user@$(id -u "$APP_USER").service" || true
	echo "Installed. Reboot so the UART and button settings take effect: sudo reboot"
fi
echo "AudioTarget install complete."
