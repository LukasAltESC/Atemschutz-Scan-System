#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="atemschutz-scan-system"
INSTALL_DIR="/opt/${PROJECT_NAME}"
SERVICE_NAME="${PROJECT_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="${SUDO_USER:-agw}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Bitte mit sudo ausfuehren: sudo ./install.sh"
  exit 1
fi

if ! id "${RUN_USER}" >/dev/null 2>&1; then
  echo "Benutzer ${RUN_USER} existiert nicht. Lege zuerst den User an oder nutze sudo -u."
  exit 1
fi

echo "== Installiere Pakete =="
apt update
apt install -y python3-flask python3-evdev python3-rpi.gpio python3-usb sqlite3 rsync usbutils

echo "== Synchronisiere Projekt nach ${INSTALL_DIR} =="
mkdir -p "${INSTALL_DIR}"

# Laufzeitdateien werden absichtlich nicht aus dem Repository ueberkopiert,
# damit lokale Daten, Einstellungen und Exporte bei Updates erhalten bleiben.
rsync -a --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'data/atemschutz_scanner.db' \
  --exclude 'data/last_print_payload.json' \
  --exclude 'data/runtime_settings.json' \
  --exclude 'data/exports/' \
  --exclude 'data/function_cards.json' \
  --exclude 'data/detail_checklist.json' \
  --exclude 'data/output_layout.json' \
  --exclude 'data/print_layout.json' \
  "${SCRIPT_DIR}/" "${INSTALL_DIR}/"

mkdir -p "${INSTALL_DIR}/data"
mkdir -p "${INSTALL_DIR}/data/exports"

# Diese Dateien werden nur beim ersten Installieren aus dem Projekt uebernommen.
# Danach bleiben lokale Anpassungen in /opt erhalten.
for file_name in Database.CSV function_cards.json detail_checklist.json output_layout.json print_layout.json; do
  if [[ ! -f "${INSTALL_DIR}/data/${file_name}" && -f "${SCRIPT_DIR}/data/${file_name}" ]]; then
    cp "${SCRIPT_DIR}/data/${file_name}" "${INSTALL_DIR}/data/${file_name}"
  fi
done

chown -R "${RUN_USER}:${RUN_USER}" "${INSTALL_DIR}"

echo "== Setze Berechtigungen fuer Input, GPIO und Druck =="
usermod -a -G input,gpio,lp "${RUN_USER}"

echo "== Installiere Udev-Regel fuer den Thermodrucker =="
cat > /etc/udev/rules.d/99-caysn-thermal-printer.rules <<'RULE'
# Caysn T7-US / kompatibler USB-Thermodrucker
SUBSYSTEM=="usb", ATTR{idVendor}=="4b43", ATTR{idProduct}=="3538", MODE="0660", GROUP="lp", TAG+="uaccess"
RULE
udevadm control --reload-rules
udevadm trigger || true

echo "== Richte systemd-Service ein =="
sed "s/__RUN_USER__/${RUN_USER}/g" "${INSTALL_DIR}/atemschutz-scan-system.service" > "/etc/systemd/system/${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "== Fertig =="
echo "Webinterface: http://$(hostname -I | awk '{print $1}'):5000"
echo "Dokumentation: ${INSTALL_DIR}/docs/"
echo "GPIO-Konfiguration: ${INSTALL_DIR}/config.py"
echo "Bondruck-Layout: ${INSTALL_DIR}/data/print_layout.json"
echo "Scanner-Test: python3 ${INSTALL_DIR}/tools/list_input_devices.py"
echo "GPIO-Test: python3 ${INSTALL_DIR}/tools/test_gpio_io.py"
echo "Drucker-Probe: sudo python3 ${INSTALL_DIR}/tools/test_thermal_printer.py --probe"
echo "Wichtig: Einmal neu einloggen oder rebooten, damit die Gruppenrechte fuer ${RUN_USER} aktiv werden."
