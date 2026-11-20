#!/data/data/com.termux/files/usr/bin/bash
# À lancer dans Termux (PAS dans Debian/proot) : donne le micro et le haut-parleur du téléphone au programme.
#   bash telephone/1_dans_termux.sh
# Termux doit avoir la permission Micro (Paramètres Android → Applications → Termux → Autorisations).
set -e
command -v pulseaudio >/dev/null || pkg install -y pulseaudio
pulseaudio --kill 2>/dev/null || true
pulseaudio --start --exit-idle-time=-1 \
  --load="module-native-protocol-tcp auth-ip-acl=127.0.0.1 auth-anonymous=1"
# Micro du téléphone (OpenSL ES).
pactl load-module module-sles-source >/dev/null 2>&1 || echo "module-sles-source déjà chargé ou indisponible"
echo "PulseAudio prêt sur 127.0.0.1:4713. Ouvre maintenant Debian (proot) et lance telephone/2_installer.sh"
