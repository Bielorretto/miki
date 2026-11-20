#!/usr/bin/env bash
# À lancer une fois dans Debian (proot), dans le dossier test_vocal.
set -e
cd "$(dirname "$0")/.."
apt-get install -y pulseaudio-utils python3-venv >/dev/null
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "→ Mets tes clés dans .env"; }
.venv/bin/python -c "from commun.modeles import telecharger; telecharger()"
# Vérifie le son.
PULSE_SERVER=tcp:127.0.0.1:4713 pactl info >/dev/null && echo "Son du téléphone : OK" || echo "Son : lance d'abord telephone/1_dans_termux.sh dans Termux"
