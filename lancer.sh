#!/usr/bin/env bash
# UNE commande pour tout (Mac ou téléphone) : installe si besoin, puis lance.
#   bash lancer.sh            → menu
#   bash lancer.sh 1          → programme 1 (realtime)
#   bash lancer.sh 2 --penseur groq   → programme 2 (cascade) + options
#   bash lancer.sh 3          → programme 3 (Eleven Realtime)
#   bash lancer.sh 4          → le numéro Twilio appelle la cascade (laisser tourner)
#   bash lancer.sh 5          → le numéro Twilio parle à GPT-Live (+ GPT-5.5 en coulisses)
set -e
cd "$(dirname "$0")"

choix="$1"; [ $# -gt 0 ] && shift
if [ -z "$choix" ]; then
  echo "1) realtime  (OpenAI Realtime, comme l'app)"
  echo "2) cascade   (Deepgram → penseur → ElevenLabs)"
  echo "3) eleven    (Eleven Realtime v1 Max, voix Lucie)"
  echo "4) téléphone (le numéro Twilio appelle la cascade)"
  echo "5) live      (téléphone : GPT-Live, le modèle du vocal ChatGPT, + GPT-5.5 en coulisses)"
  read -rp "Choix [1/2/3/4/5] : " ligne
  # On peut aussi écrire les options à la suite du choix : « 4 --appeler 06… »
  set -- $ligne
  choix="$1"; [ $# -gt 0 ] && shift
fi
case "$choix" in 1|realtime) prog=realtime ;; 2|cascade) prog=cascade ;; 3|eleven) prog=eleven ;; 4|telephone|téléphone) prog=appel ;; 5|live) prog=live ;; *) echo "Choix inconnu : $choix"; exit 1 ;; esac

if [ "$prog" = "appel" ] || [ "$prog" = "live" ]; then
  [ -x .venv/bin/python ] || { [ "$(uname)" = "Darwin" ] && bash pc/installer_mac.sh || bash telephone/2_installer.sh; }
  export ORT_LOGGING_LEVEL=3
  [ "$prog" = "live" ] && exec .venv/bin/python -m live.serveur "$@"
  exec .venv/bin/python -m appel.serveur "$@"
fi

if [ "$(uname)" = "Darwin" ]; then
  [ -x .venv/bin/python ] || bash pc/installer_mac.sh
  audio=mac
else
  [ -x .venv/bin/python ] || bash telephone/2_installer.sh
  if ! PULSE_SERVER=tcp:127.0.0.1:4713 pactl info >/dev/null 2>&1; then
    echo "Pas de son : lance plutôt depuis Termux avec  bash ~/vocal.sh"; exit 1
  fi
  if ! PULSE_SERVER=tcp:127.0.0.1:4713 pactl list sources short | grep -qv monitor; then
    echo "Pas de micro : donne la permission Micro à Termux (Paramètres Android → Applis → Termux),"
    echo "puis dans Termux :  pulseaudio --kill  et relance  bash ~/vocal.sh"; exit 1
  fi
  export PULSE_SOURCE=$(PULSE_SERVER=tcp:127.0.0.1:4713 pactl list sources short | grep -v monitor | head -1 | cut -f2)
  audio=pulse
fi

if [ ! -f .env ] || ! grep -q "^OPENAI_API_KEY=." .env; then
  [ -f .env ] || cp .env.example .env
  echo "Mets d'abord tes clés dans $(pwd)/.env puis relance."; exit 1
fi

export ORT_LOGGING_LEVEL=3
exec .venv/bin/python -m "$prog.bot" --audio "$audio" "$@"
