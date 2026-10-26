#!/usr/bin/env bash
# Meshtastic <-> Telegram bridge: prepares the Python environment, then opens the setup menu.
#   ./setup.sh              menu
#   ./setup.sh config|install|uninstall|status|logs|test
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

it=0
if grep -qs '^BRIDGE_LANG=it' config.env || { [ ! -f config.env ] && [[ "${LANG:-}" == it* ]]; }; then it=1; fi
say() { if [ "$it" = 1 ]; then echo "$2"; else echo "$1"; fi; }

command -v python3 >/dev/null || { say "python3 not found: sudo apt install python3 python3-venv" \
                                      "python3 non trovato: sudo apt install python3 python3-venv"; exit 1; }
if [ ! -x venv/bin/python ]; then
    say "Creating the Python environment (venv)..." "Creo l'ambiente Python (venv)..."
    python3 -m venv venv || { rm -rf venv; say "Install venv first: sudo apt install python3-venv" \
                                                 "Installa prima venv: sudo apt install python3-venv"; exit 1; }
fi
if ! venv/bin/python -c "import meshtastic, requests, pubsub" 2>/dev/null; then
    say "Installing the dependencies (meshtastic, requests)..." "Installo le dipendenze (meshtastic, requests)..."
    venv/bin/pip install -q --upgrade pip
    venv/bin/pip install -q -r requirements.txt
fi
exec venv/bin/python setup_wizard.py "$@"
