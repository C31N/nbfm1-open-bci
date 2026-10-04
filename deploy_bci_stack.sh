#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -Eeuo pipefail
IFS=$'\n\t'

if [[ ${EUID} -ne 0 ]]; then
    exec sudo -E bash "$0" "$@"
fi

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PREFIX=/opt/bci-stack
VENV="$PREFIX/venv"
BCI_USER=bci
BCI_GROUP=bci
ARDUINO_CLI_VERSION=1.5.1
ESP32_CORE_VERSION=3.3.12
ESP32_FQBN=esp32:esp32:esp32s3

log() { printf '[BCI] %s\n' "$*"; }
die() { printf '[BCI] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "$SOURCE_DIR/bin/export_onnx.py" ]] || die "run this script from the repository root"

if command -v apt-get >/dev/null 2>&1; then
    log "Installing OS packages"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates curl git build-essential python3 python3-dev python3-venv python3-pip \
        libgl1 libx11-6 libxtst6 libxrandr2 libxi6 jq xz-utils unzip udev
else
    die "Debian/Ubuntu/Raspberry-Pi-OS/JetPack target required"
fi

getent group "$BCI_GROUP" >/dev/null || groupadd --system "$BCI_GROUP"
id "$BCI_USER" >/dev/null 2>&1 || useradd --system --gid "$BCI_GROUP" --home-dir "$PREFIX" --shell /usr/sbin/nologin "$BCI_USER"
for g in dialout video render; do getent group "$g" >/dev/null && usermod -a -G "$g" "$BCI_USER"; done

install -d -m 0755 "$PREFIX" "$PREFIX/bin" "$PREFIX/config" "$PREFIX/systemd" "$PREFIX/firmware" "$PREFIX/models"
install -d -m 0770 -o "$BCI_USER" -g "$BCI_GROUP" "$PREFIX/engine-cache" "$PREFIX/reports" "$PREFIX/build"
cp -a "$SOURCE_DIR/bin/." "$PREFIX/bin/"
cp -a "$SOURCE_DIR/config/." "$PREFIX/config/"
cp -a "$SOURCE_DIR/systemd/." "$PREFIX/systemd/"
cp -a "$SOURCE_DIR/firmware/." "$PREFIX/firmware/"
cp "$SOURCE_DIR/requirements.txt" "$PREFIX/requirements.txt"

python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV/bin/pip" install -r "$PREFIX/requirements.txt"

install_arduino_cli() {
    command -v arduino-cli >/dev/null 2>&1 && return
    local arch url tmp
    arch="$(uname -m)"
    tmp="$(mktemp -d)"
    case "$arch" in
        x86_64|amd64) url="https://downloads.arduino.cc/arduino-cli/arduino-cli_${ARDUINO_CLI_VERSION}_Linux_64bit.tar.gz" ;;
        aarch64|arm64) url="https://downloads.arduino.cc/arduino-cli/arduino-cli_${ARDUINO_CLI_VERSION}_Linux_ARM64.tar.gz" ;;
        *) die "unsupported architecture for bundled Arduino CLI install: $arch" ;;
    esac
    curl -fL "$url" -o "$tmp/arduino-cli.tar.gz"
    tar -xzf "$tmp/arduino-cli.tar.gz" -C "$tmp"
    install -m 0755 "$tmp/arduino-cli" /usr/local/bin/arduino-cli
    rm -rf "$tmp"
}
install_arduino_cli

arduino-cli config init --overwrite >/dev/null
arduino-cli core update-index
arduino-cli core install "esp32:esp32@${ESP32_CORE_VERSION}"
rm -rf "$PREFIX/build/esp32"
install -d -m 0755 "$PREFIX/build/esp32"
arduino-cli compile --fqbn "$ESP32_FQBN" --output-dir "$PREFIX/build/esp32" "$PREFIX/firmware/bci_bridge_esp32s3"

install -m 0644 "$PREFIX/config/99-bci-esp32.rules" /etc/udev/rules.d/99-bci-esp32.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=tty || true

install -m 0644 "$PREFIX/config/bci-tmpfiles.conf" /etc/tmpfiles.d/bci.conf
systemd-tmpfiles --create /etc/tmpfiles.d/bci.conf
chown "$BCI_USER:$BCI_GROUP" /run/bci /dev/shm/bci
chmod 0700 /run/bci /dev/shm/bci
runuser -u "$BCI_USER" -- "$VENV/bin/python" "$PREFIX/bin/ensure_runtime.py"
chmod 0600 /run/bci/master.key /run/bci/arm

chown -R "$BCI_USER:$BCI_GROUP" "$PREFIX/models" "$PREFIX/engine-cache" "$PREFIX/reports"
runuser -u "$BCI_USER" -- env PYTHONPATH="$PREFIX/bin" "$VENV/bin/python" "$PREFIX/bin/export_onnx.py" --output "$PREFIX/models/nbfm1.onnx"

TRTEXEC="$(command -v trtexec 2>/dev/null || true)"
if [[ -z "$TRTEXEC" && -x /usr/src/tensorrt/bin/trtexec ]]; then TRTEXEC=/usr/src/tensorrt/bin/trtexec; fi
if [[ -n "$TRTEXEC" ]]; then
    "$TRTEXEC" --onnx="$PREFIX/models/nbfm1.onnx" --saveEngine="$PREFIX/models/nbfm1_fp16.engine" --fp16 --timingCacheFile="$PREFIX/engine-cache/nbfm1.timing" --memPoolSize=workspace:2048 --skipInference
fi

for unit in bci-simulator.service bci-inference.service bci-bridge.service bci-dashboard.service bci-stack.target; do
    install -m 0644 "$PREFIX/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable bci-stack.target
systemctl restart bci-stack.target

"$VENV/bin/python" -m compileall -q "$PREFIX/bin"
log "Deployment complete"
log "Dashboard: http://127.0.0.1:8088"
