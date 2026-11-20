"""Programme 5 au téléphone : le serveur Twilio du programme 4, avec le bot « live ».
Lancer :  python -m live.serveur [--appeler 06…]   (ou : bash lancer.sh 5)"""

from appel.serveur import main
from live.bot import BotLive

if __name__ == "__main__":
    main(BotLive)
