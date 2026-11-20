"""
Le numéro Twilio appelle la cascade (Deepgram → penseur → ElevenLabs).

  Appel → Twilio → GET https://<tunnel>/voix?k=<jeton>  → TwiML <Connect><Stream>
               → websocket wss://<tunnel>/media/<jeton> : son de l'appel (μ-law 8 kHz) dans les deux sens

  - Un tunnel Cloudflare gratuit rend ce serveur joignable depuis Internet ; son adresse change à chaque
    lancement, le numéro est donc rebranché automatiquement (appel/twilio.py).
  - Un jeton secret dans l'adresse : personne d'autre ne peut se brancher sur le serveur.
  - Une conversation (et un dossier sessions/) par appel. Barge-in : on vide aussi le tampon de Twilio (« clear »).

Lancer :  python -m appel.serveur [--appeler +33612345678] [--penseur groq|openai|mistral] ...   (ou : bash lancer.sh 4)
  --appeler : c'est le bot qui t'appelle (tu ne paies rien ; Twilio facture l'appel sortant sur ton compte).
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import platform
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import websockets
from websockets.datastructures import Headers
from websockets.http11 import Response

from cascade.bot import BotCascade
from commun.config import Config
from commun.lancement import configuration

from . import twilio

PORT = 8765
RACINE = Path(__file__).resolve().parent.parent
CLOUDFLARED = RACINE / "outils" / "cloudflared"


# ------------------------------------------------------------------ tunnel

def _cloudflared() -> str:
    if shutil.which("cloudflared"):
        return shutil.which("cloudflared")
    if not CLOUDFLARED.exists():
        machine = platform.machine().lower()
        arch = "arm64" if machine in ("aarch64", "arm64") else "amd64"
        if platform.system() == "Darwin":
            raise SystemExit("Installe cloudflared :  brew install cloudflared")
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        print("Téléchargement de cloudflared (tunnel)…")
        CLOUDFLARED.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(url, CLOUDFLARED)
        CLOUDFLARED.chmod(0o755)
    return str(CLOUDFLARED)


def ouvrir_tunnel() -> tuple[subprocess.Popen, str]:
    """Lance un tunnel Cloudflare rapide vers le serveur local ; renvoie (processus, https://….trycloudflare.com)."""
    p = subprocess.Popen([_cloudflared(), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    fin = time.time() + 40
    for ligne in p.stdout:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", ligne)
        if m:
            threading.Thread(target=lambda: [None for _ in p.stdout], daemon=True).start()  # vider la sortie
            return p, m.group(0)
        if time.time() > fin:
            break
    p.kill()
    raise SystemExit("Le tunnel Cloudflare n'a pas démarré (connexion Internet ?)")


# ------------------------------------------------------------------ un appel

class Appel:
    def __init__(self, cfg: Config, ws, classe=BotCascade) -> None:
        self.ws = ws
        self.bot = classe(cfg)
        self.loop = asyncio.get_running_loop()
        self.stream_sid: str | None = None
        self.entree: queue.Queue[bytes | None] = queue.Queue()
        self.bot.audio.lecteur.sur_coupure = self._vider_twilio
        # Le traitement du micro (Silero, Smart Turn…) tourne dans un fil à part, comme sur le téléphone.
        threading.Thread(target=self._traiter_entree, daemon=True).start()

    def _traiter_entree(self) -> None:
        while (b := self.entree.get()) is not None:
            self.bot.audio.twilio_entree(b)

    def _vider_twilio(self) -> None:
        if self.stream_sid:
            msg = json.dumps({"event": "clear", "streamSid": self.stream_sid})
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._envoyer(msg)))

    async def _envoyer(self, msg: str) -> None:
        try:
            await self.ws.send(msg)
        except websockets.ConnectionClosed:
            pass

    async def _parler(self) -> None:
        """Envoie la voix de l'IA au rythme réel (20 ms par paquet, 60 ms d'avance)."""
        t0, k, avance = time.monotonic(), 0, 3
        while True:
            payload = base64.b64encode(self.bot.audio.twilio_sortie()).decode()
            await self._envoyer(json.dumps({"event": "media", "streamSid": self.stream_sid, "media": {"payload": payload}}))
            k += 1
            attente = t0 + (k - avance) * 0.02 - time.monotonic()
            if attente > 0:
                await asyncio.sleep(attente)

    async def gerer(self) -> None:
        conversation = parole = None
        try:
            async for brut in self.ws:
                m = json.loads(brut)
                ev = m.get("event")
                if ev == "start":
                    self.stream_sid = m["start"]["streamSid"]
                    print(f"📞 Appel reçu ({m['start'].get('customParameters', {}).get('de', 'numéro masqué')})")
                    conversation = asyncio.create_task(self.bot.lancer())
                    # Conversation finie (l'IA a dit au revoir) : on ferme le flux, Twilio n'a plus d'instruction et raccroche.
                    conversation.add_done_callback(lambda _: asyncio.ensure_future(self.ws.close()))
                    parole = asyncio.create_task(self._parler())
                elif ev == "media":
                    self.entree.put(base64.b64decode(m["media"]["payload"]))
                elif ev == "stop":
                    break
        except websockets.ConnectionClosed:
            pass
        finally:
            self.entree.put(None)
            if parole:
                parole.cancel()
            self.bot.audio.fin_fichier.set()  # fin de la conversation (voir Conversation.lancer)
            if conversation:
                await conversation
            print("📴 Appel terminé")


# ------------------------------------------------------------------ serveur

async def servir(cfg: Config, appeler: str | None = None, classe=BotCascade) -> None:
    jeton = secrets.token_urlsafe(16)

    def requete(connexion, req):
        chemin = req.path
        if chemin.startswith("/voix") and f"k={jeton}" in chemin:
            hote = req.headers.get("Host", "")
            de = re.search(r"From=([^&]+)", chemin)
            twiml = (f'<?xml version="1.0" encoding="UTF-8"?><Response><Connect><Stream url="wss://{hote}/media/{jeton}">'
                     f'<Parameter name="de" value="{html.escape(urllib.parse.unquote(de.group(1))) if de else ""}"/>'
                     f"</Stream></Connect></Response>")
            corps = twiml.encode()
            return Response(200, "OK", Headers([("Content-Type", "text/xml"), ("Content-Length", str(len(corps)))]), corps)
        if chemin == f"/media/{jeton}":
            return None  # websocket de l'appel
        return Response(404, "Not Found", Headers([("Content-Type", "text/plain"), ("Content-Length", "0")]), b"")

    async def appel(ws):
        await Appel(cfg, ws, classe).gerer()

    async with websockets.serve(appel, "127.0.0.1", PORT, process_request=requete, max_size=None):
        tunnel, adresse = await asyncio.to_thread(ouvrir_tunnel)
        try:
            await asyncio.sleep(3)  # le temps que l'adresse du tunnel soit connue partout
            numero = await asyncio.to_thread(twilio.brancher, f"{adresse}/voix?k={jeton}")
            if appeler:
                await asyncio.to_thread(twilio.appeler, appeler, f"{adresse}/voix?k={jeton}")
                print(f"\n✅ Le bot t'appelle au {appeler[:6]}•••{appeler[-2:]} (Ctrl+C pour arrêter)\n")
            else:
                print(f"\n✅ Prêt : appelle le {numero}  (Ctrl+C pour arrêter)\n")
            await asyncio.Future()
        finally:
            tunnel.kill()


def main(classe=BotCascade) -> None:
    import sys

    appeler = None
    if "--appeler" in sys.argv:
        i = sys.argv.index("--appeler")
        appeler = sys.argv[i + 1].replace(" ", "")
        if appeler.startswith("0"):
            appeler = "+33" + appeler[1:]  # 06 12 34 56 78 → +33612345678
        del sys.argv[i : i + 2]
    cfg = configuration(classe, audio_defaut="twilio")
    cfg.audio = "twilio"
    try:
        asyncio.run(servir(cfg, appeler, classe))
    except KeyboardInterrupt:
        print("\nServeur arrêté. (Pour rendre le numéro à l'ancien callbot : .venv/bin/python -m appel.twilio --remettre)")


if __name__ == "__main__":
    main()
