#!/usr/bin/env bash
# Installation sur Mac (une fois) :  bash pc/installer_mac.sh
set -e
cd "$(dirname "$0")/.."
command -v brew >/dev/null || { echo "Installe Homebrew d'abord : https://brew.sh"; exit 1; }
brew list portaudio >/dev/null 2>&1 || brew install portaudio
PY=$(command -v python3.12 || command -v python3.13 || command -v python3)
"$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt -r requirements-pc.txt
[ -f .env ] || { cp .env.example .env; echo "→ Ouvre .env et mets tes clés (jamais dans le code)."; }
.venv/bin/python -c "from commun.modeles import telecharger; telecharger()"
echo "Prêt. Lance : bash pc/lancer_realtime.sh   ou   bash pc/lancer_cascade.sh"
echo "(La 1re fois, macOS demande l'accès au micro pour le Terminal : accepte.)"
