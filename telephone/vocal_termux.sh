#!/data/data/com.termux/files/usr/bin/bash
# À copier dans Termux :  ~/vocal.sh   puis lancer :  bash ~/vocal.sh [1|2] [options]
# Démarre le son du téléphone, puis lance test_vocal dans Ubuntu.
command -v pulseaudio >/dev/null || pkg install -y pulseaudio
pactl info >/dev/null 2>&1 || pulseaudio --start --exit-idle-time=-1
for i in 1 2 3 4 5; do pactl info >/dev/null 2>&1 && break; sleep 1; done
modules=$(pactl list modules short 2>/dev/null)
# Port local pour qu'Ubuntu accède au son.
echo "$modules" | grep -q module-native-protocol-tcp || \
  pactl load-module module-native-protocol-tcp auth-ip-acl=127.0.0.1 auth-anonymous=1 >/dev/null || echo "Erreur : port son"
# Micro du téléphone.
echo "$modules" | grep -q module-sles-source || \
  pactl load-module module-sles-source >/dev/null || echo "Erreur : micro (donne la permission Micro à Termux)"
exec proot-distro login ubuntu -- bash /root/test_vocal/lancer.sh "$@"
