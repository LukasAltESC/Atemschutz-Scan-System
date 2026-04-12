#!/usr/bin/env bash
set -euo pipefail

# Update-Skript fuer bestehende Installationen.
# Es arbeitet immer relativ zu seinem eigenen Verzeichnis, damit keine festen
# Benutzer- oder Pfadangaben angepasst werden muessen.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "${SCRIPT_DIR}"
git pull --ff-only
chmod +x install.sh update.sh
sudo ./install.sh
