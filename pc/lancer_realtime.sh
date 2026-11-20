#!/usr/bin/env bash
# Programme realtime sur Mac (micro + haut-parleur de l'ordinateur). Options en plus : --langue en, --juge openai…
cd "$(dirname "$0")/.."
export ORT_LOGGING_LEVEL=3
exec .venv/bin/python -m realtime.bot --audio mac "$@"
