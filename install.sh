#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="atemschutz-scan-system"
INSTALL_DIR="/opt/${PROJECT_NAME}"
SERVICE_NAME="${PROJECT_NAME}.service"
CAPTIVE_PORTAL_SERVICE_NAME="${PROJECT_NAME}-captive-portal.service"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="${SUDO_USER:-agw}"

# Access-Point-Defaults
# Bei Bedarf vor dem Aufruf ueberschreiben, z. B.:
#   sudo AP_SSID="Atemschutz-Scan-System" AP_PASSPHRASE="GeheimesPasswort" ./install.sh
AP_INTERFACE="${AP_INTERFACE:-wlan0}"
ETH_INTERFACE="${ETH_INTERFACE:-eth0}"
AP_SSID="${AP_SSID:-Atemschutz-Scan-System}"
AP_PASSPHRASE="${AP_PASSPHRASE:-Atemschutz2026}"
AP_OPEN_NETWORK="${AP_OPEN_NETWORK:-0}"
AP_COUNTRY="${AP_COUNTRY:-DE}"
AP_CHANNEL="${AP_CHANNEL:-6}"
AP_IP_ADDRESS="${AP_IP_ADDRESS:-192.168.50.1}"
AP_PREFIX_LENGTH="${AP_PREFIX_LENGTH:-24}"
AP_NETMASK="${AP_NETMASK:-255.255.255.0}"
AP_DHCP_START="${AP_DHCP_START:-192.168.50.20}"
AP_DHCP_END="${AP_DHCP_END:-192.168.50.150}"
AP_DHCP_LEASE_TIME="${AP_DHCP_LEASE_TIME:-24h}"
AP_CONNECTION_NAME="${AP_CONNECTION_NAME:-atemschutz-access-point}"
AP_LOCAL_HOSTNAME="${AP_LOCAL_HOSTNAME:-atemschutz-scan-system.local}"
AP_BACKEND="${AP_BACKEND:-classic}"
CAPTIVE_PORTAL_ENABLED="${CAPTIVE_PORTAL_ENABLED:-1}"
CAPTIVE_PORTAL_EXTERNAL_URL="${CAPTIVE_PORTAL_EXTERNAL_URL:-http://portal.atemschutz.scan/}"
WEB_APP_PORT="${WEB_APP_PORT:-5000}"
WEB_PROXY_PORT="${WEB_PROXY_PORT:-80}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Bitte mit sudo ausfuehren: sudo ./install.sh"
  exit 1
fi

if ! id "${RUN_USER}" >/dev/null 2>&1; then
  echo "Benutzer ${RUN_USER} existiert nicht. Lege zuerst den User an oder nutze sudo -u."
  exit 1
fi

if [[ "${AP_OPEN_NETWORK}" != "1" ]]; then
  if [[ ${#AP_PASSPHRASE} -lt 8 || ${#AP_PASSPHRASE} -gt 63 ]]; then
    echo "AP_PASSPHRASE muss zwischen 8 und 63 Zeichen lang sein oder AP_OPEN_NETWORK=1 setzen."
    exit 1
  fi
fi

remove_block_from_file() {
  local file_path="$1"
  local start_marker="$2"
  local end_marker="$3"

  if [[ ! -f "${file_path}" ]]; then
    return 0
  fi

  python3 - "$file_path" "$start_marker" "$end_marker" <<'PY'
from pathlib import Path
import sys

file_path = Path(sys.argv[1])
start_marker = sys.argv[2]
end_marker = sys.argv[3]
content = file_path.read_text(encoding='utf-8', errors='ignore')
start = content.find(start_marker)
if start == -1:
    raise SystemExit(0)
end = content.find(end_marker, start)
if end == -1:
    raise SystemExit(0)
end += len(end_marker)
while end < len(content) and content[end] == '\n':
    end += 1
new_content = (content[:start].rstrip('\n') + '\n\n' + content[end:].lstrip('\n')).rstrip() + '\n'
file_path.write_text(new_content, encoding='utf-8')
PY
}

get_interface_ip() {
  local interface_name="$1"
  ip -4 -o addr show dev "${interface_name}" 2>/dev/null | awk '{print $4}' | cut -d'/' -f1 | head -n1
}

configure_wifi_country() {
  echo "== Setze WLAN-Land auf ${AP_COUNTRY} =="
  if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_wifi_country "${AP_COUNTRY}" || true
  fi

  mkdir -p /etc/wpa_supplicant
  python3 - "${AP_COUNTRY}" <<'PY'
from pathlib import Path
import sys

country = sys.argv[1]
path = Path('/etc/wpa_supplicant/wpa_supplicant.conf')
base_lines = [
    f'country={country}',
    'ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev',
    'update_config=1',
]
if path.exists():
    lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
    filtered = [line for line in lines if not line.startswith('country=')]
    if not any(line.startswith('ctrl_interface=') for line in filtered):
        filtered.insert(0, 'ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev')
    if not any(line.startswith('update_config=') for line in filtered):
        filtered.insert(1, 'update_config=1')
    filtered.insert(0, f'country={country}')
    path.write_text('\n'.join(filtered).rstrip() + '\n', encoding='utf-8')
else:
    path.write_text('\n'.join(base_lines) + '\n', encoding='utf-8')
PY

  if command -v iw >/dev/null 2>&1; then
    iw reg set "${AP_COUNTRY}" || true
  fi
}

disable_wlan_client_conflicts() {
  echo "== Deaktiviere stoerende WLAN-Client-Dienste auf ${AP_INTERFACE} =="

  systemctl stop wpa_supplicant.service || true
  systemctl stop "wpa_supplicant@${AP_INTERFACE}.service" || true
  systemctl disable wpa_supplicant.service || true
  systemctl disable "wpa_supplicant@${AP_INTERFACE}.service" || true

  # Raspberry Pi OS Lite 64 Bit nutzt je nach Release NetworkManager.
  # nmcli device set <iface> managed no ist nur eine Laufzeit-Einstellung
  # und geht beim Reboot verloren. Danach verwaltet NetworkManager wlan0 wieder,
  # startet wpa_supplicant und hostapd kann den Access Point nicht mehr
  # uebernehmen. Deshalb wird wlan0 zusaetzlich persistent als unmanaged
  # konfiguriert. Ethernet bleibt davon unberuehrt und laeuft weiter per DHCP.
  mkdir -p /etc/NetworkManager/conf.d
  cat > "/etc/NetworkManager/conf.d/90-${PROJECT_NAME}-${AP_INTERFACE}-unmanaged.conf" <<NMCONF
# Managed by ${PROJECT_NAME}/install.sh
# ${AP_INTERFACE} is reserved for hostapd/dnsmasq access-point mode.
[keyfile]
unmanaged-devices=interface-name:${AP_INTERFACE}
NMCONF

  if command -v nmcli >/dev/null 2>&1; then
    nmcli connection down "${AP_CONNECTION_NAME}" || true
    nmcli connection delete "${AP_CONNECTION_NAME}" || true
    nmcli device set "${AP_INTERFACE}" managed no || true
    nmcli general reload || true
  fi

  if systemctl is-active --quiet NetworkManager.service; then
    systemctl reload NetworkManager.service || systemctl restart NetworkManager.service || true
  fi
}

configure_nginx_reverse_proxy() {
  echo "== Richte lokalen Web-Proxy fuer Captive Portal und Port 80 ein =="
  apt install -y nginx

  rm -f /etc/nginx/sites-enabled/default /etc/nginx/sites-available/default
  cat > /etc/nginx/sites-available/${PROJECT_NAME}.conf <<NGINX
server {
    listen ${WEB_PROXY_PORT} default_server;
    listen [::]:${WEB_PROXY_PORT} default_server;
    server_name _;

    proxy_read_timeout 300;
    proxy_connect_timeout 300;
    proxy_send_timeout 300;
    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:${WEB_APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX

  ln -sf /etc/nginx/sites-available/${PROJECT_NAME}.conf /etc/nginx/sites-enabled/${PROJECT_NAME}.conf
  nginx -t
  systemctl enable nginx
  systemctl restart nginx
}

configure_access_point_with_classic_stack() {
  echo "== Richte WLAN-Access-Point ueber hostapd/dnsmasq ein =="
  apt install -y hostapd dnsmasq rfkill dhcpcd5 iw
  systemctl unmask hostapd || true
  systemctl enable dhcpcd
  systemctl start dhcpcd
  rfkill unblock wlan || true

  configure_wifi_country
  disable_wlan_client_conflicts

  cat > /etc/hostapd/hostapd.conf <<HOSTAPD
country_code=${AP_COUNTRY}
interface=${AP_INTERFACE}
driver=nl80211
ctrl_interface=/var/run/hostapd
ctrl_interface_group=0
ssid=${AP_SSID}
hw_mode=g
channel=${AP_CHANNEL}
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
ieee80211d=1
ieee80211n=0
HOSTAPD

  if [[ "${AP_OPEN_NETWORK}" == "1" ]]; then
    cat >> /etc/hostapd/hostapd.conf <<'HOSTAPD'
wpa=0
HOSTAPD
  else
    cat >> /etc/hostapd/hostapd.conf <<HOSTAPD
wpa=2
wpa_passphrase=${AP_PASSPHRASE}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
HOSTAPD
  fi

  if grep -q '^#\?DAEMON_CONF=' /etc/default/hostapd 2>/dev/null; then
    sed -i 's|^#\?DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
  else
    echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' >> /etc/default/hostapd
  fi

  cat > "/etc/dnsmasq.d/${PROJECT_NAME}-ap.conf" <<DNSMASQ
interface=${AP_INTERFACE}
bind-dynamic
domain-needed
bogus-priv
dhcp-authoritative
dhcp-range=${AP_DHCP_START},${AP_DHCP_END},${AP_NETMASK},${AP_DHCP_LEASE_TIME}
dhcp-option=option:router,${AP_IP_ADDRESS}
dhcp-option=option:dns-server,${AP_IP_ADDRESS}
DNSMASQ

  if [[ "${CAPTIVE_PORTAL_ENABLED}" == "1" ]]; then
    cat >> "/etc/dnsmasq.d/${PROJECT_NAME}-ap.conf" <<DNSMASQ
# Captive Portal: alle DNS-Anfragen im Hotspot auf den Pi aufloesen
address=/#/${AP_IP_ADDRESS}
# RFC 8910 Captive-Portal-Hinweis fuer kompatible Clients
# Der Hostname zeigt absichtlich ebenfalls auf den Pi.
dhcp-option=114,${CAPTIVE_PORTAL_EXTERNAL_URL}
DNSMASQ
  else
    cat >> "/etc/dnsmasq.d/${PROJECT_NAME}-ap.conf" <<DNSMASQ
address=/${AP_LOCAL_HOSTNAME}/${AP_IP_ADDRESS}
DNSMASQ
  fi

  local start_marker="# >>> ${PROJECT_NAME} access point >>>"
  local end_marker="# <<< ${PROJECT_NAME} access point <<<"
  remove_block_from_file /etc/dhcpcd.conf "${start_marker}" "${end_marker}"
  cat >> /etc/dhcpcd.conf <<DHCP

${start_marker}
interface ${AP_INTERFACE}
static ip_address=${AP_IP_ADDRESS}/${AP_PREFIX_LENGTH}
nohook wpa_supplicant
${end_marker}
DHCP

  if ip link show "${ETH_INTERFACE}" >/dev/null 2>&1; then
    local eth_start_marker="# >>> ${PROJECT_NAME} ethernet >>>"
    local eth_end_marker="# <<< ${PROJECT_NAME} ethernet <<<"
    remove_block_from_file /etc/dhcpcd.conf "${eth_start_marker}" "${eth_end_marker}"
    cat >> /etc/dhcpcd.conf <<DHCP

${eth_start_marker}
interface ${ETH_INTERFACE}
require dhcp_server_identifier
${eth_end_marker}
DHCP
  fi

  systemctl restart dhcpcd
  systemctl enable dnsmasq hostapd
  systemctl restart dnsmasq
  systemctl restart hostapd
}

configure_access_point_with_networkmanager() {
  echo "== NetworkManager-Backend explizit angefordert =="
  echo "== Auf Raspberry Pi OS Lite ist der klassische hostapd/dnsmasq-Backend empfohlen =="
  configure_access_point_with_classic_stack
}

echo "== Installiere Pakete =="
apt update
apt install -y python3-flask python3-evdev python3-rpi.gpio python3-usb sqlite3 rsync usbutils iw

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

if [[ "${AP_BACKEND}" == "networkmanager" ]]; then
  configure_access_point_with_networkmanager
else
  configure_access_point_with_classic_stack
fi

if [[ "${CAPTIVE_PORTAL_ENABLED}" == "1" ]]; then
  configure_nginx_reverse_proxy
fi

echo "== Richte systemd-Service ein =="
sed "s/__RUN_USER__/${RUN_USER}/g" "${INSTALL_DIR}/atemschutz-scan-system.service" > "/etc/systemd/system/${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

AP_WEB_URL="http://${AP_IP_ADDRESS}"
AP_DIRECT_WEB_URL="http://${AP_IP_ADDRESS}:${WEB_APP_PORT}"
ETH_CURRENT_IP="$(get_interface_ip "${ETH_INTERFACE}")"

echo "== Fertig =="
echo "Access-Point SSID: ${AP_SSID}"
if [[ "${AP_OPEN_NETWORK}" == "1" ]]; then
  echo "Access-Point Sicherheit: offen"
else
  echo "Access-Point Passwort: ${AP_PASSPHRASE}"
fi
echo "Access-Point Webinterface (Captive Portal/Port 80): ${AP_WEB_URL}"
echo "Access-Point Direktzugriff: ${AP_DIRECT_WEB_URL}"
echo "Access-Point SSH: ssh ${RUN_USER}@${AP_IP_ADDRESS}"
if [[ -n "${ETH_CURRENT_IP}" ]]; then
  if [[ "${CAPTIVE_PORTAL_ENABLED}" == "1" ]]; then
    echo "LAN-Webinterface: http://${ETH_CURRENT_IP}"
  fi
  echo "LAN-Webinterface direkt: http://${ETH_CURRENT_IP}:${WEB_APP_PORT}"
  echo "LAN-SSH: ssh ${RUN_USER}@${ETH_CURRENT_IP}"
else
  echo "LAN: DHCP bleibt aktiv. Sobald ${ETH_INTERFACE} verbunden ist, sind SSH und Webinterface ueber die per DHCP vergebene IP erreichbar."
fi
echo "Dokumentation: ${INSTALL_DIR}/docs/"
echo "GPIO-Konfiguration: ${INSTALL_DIR}/config.py"
echo "Bondruck-Layout: ${INSTALL_DIR}/data/print_layout.json"
echo "Scanner-Test: python3 ${INSTALL_DIR}/tools/list_input_devices.py"
echo "GPIO-Test: python3 ${INSTALL_DIR}/tools/test_gpio_io.py"
echo "Drucker-Probe: sudo python3 ${INSTALL_DIR}/tools/test_thermal_printer.py --probe"
echo "Hotspot-Diagnose: sudo systemctl status hostapd dnsmasq nginx ${SERVICE_NAME} --no-pager"
echo "Hotspot-Logs: sudo journalctl -u hostapd -u dnsmasq -u nginx -u ${SERVICE_NAME} -n 150 --no-pager"
echo "Wichtig: Wenn ein Geraet das WLAN bereits gespeichert hat, Netzwerk auf dem Geraet einmal loeschen/vergessen und neu verbinden."
echo "Wichtig: Bei Captive-Portal-Erkennung ist HTTPS-Umleitung technisch eingeschraenkt. Der automatische Start funktioniert ueber die HTTP-Erkennung des Geraets."
echo "Wichtig: Einmal neu einloggen oder rebooten, damit die Gruppenrechte fuer ${RUN_USER} aktiv werden."
