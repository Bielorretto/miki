#!/usr/bin/env bash
# Programme realtime sur le téléphone (micro + haut-parleur via PulseAudio de Termux). Options en plus : --langue en, --juge openai…
cd "$(dirname "$0")/.."
export ORT_LOGGING_LEVEL=3
exec .venv/bin/python -m realtime.bot --audio pulse "$@"
