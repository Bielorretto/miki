"""
Programme 3 : Eleven Realtime (ElevenLabs, speech-to-speech), même protocole qu'OpenAI Realtime.

Tout est repris du programme 1 (realtime/bot.py) : seules l'adresse, la connexion et la session changent.
  - modèle : eleven_realtime_v1_max (ou ELEVEN_REALTIME_MODEL=eleven_realtime_v1_mini dans .env)
  - voix   : Lucie (TTS_VOICE_ID)
  - clé    : ELEVEN_API_KEY, qui doit avoir la permission « ElevenAgents / Conversational AI : écriture »
             (sert à créer un secret de courte durée, puis on se connecte avec ce secret)

Lancer :  python -m eleven.bot [--audio mac|pulse|fichier:chemin.wav]
"""

from __future__ import annotations

import asyncio
import re

import httpx
import websockets

from commun.config import Config, env
from commun.lancement import lancer
from realtime.bot import RATE_OPENAI, BotRealtime

URL = "https://api.elevenlabs.io/v1/convai/realtime"


class BotEleven(BotRealtime):
    nom = "eleven"
    accueil_par_instructions = False

    def __init__(self, cfg: Config) -> None:
        super().__init__(cfg)
        self.modele = env("ELEVEN_REALTIME_MODEL", "eleven_realtime_v1_max")
        self.voix = env("TTS_VOICE_ID", "YxrwjAKoUKULGd0g8K9Y")

    def _session(self) -> dict:
        transcription: dict = {}
        if self.cfg.langue != "multi":
            transcription["language"] = self.cfg.langue
        return {
            "type": "realtime",
            "model": self.modele,
            "instructions": self.cfg.consignes,
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": RATE_OPENAI},
                    "transcription": transcription,
                    "turn_detection": None,  # c'est notre écoute qui décide de la fin du tour
                },
                "output": {"format": {"type": "audio/pcm", "rate": RATE_OPENAI}, "voice": self.voix},
            },
        }

    async def connecter(self) -> None:
        cle = env("ELEVEN_API_KEY")
        if not cle:
            raise SystemExit("ELEVEN_API_KEY manquante dans .env")
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{URL}/client_secrets", headers={"xi-api-key": cle},
                             json={"session": self._session(), "expires_after": {"anchor": "created_at", "seconds": 600}})
        if r.status_code == 401 and "convai_write" in r.text:
            raise SystemExit("Ta clé ElevenLabs n'a pas la permission « ElevenAgents : écriture ». "
                             "Va sur elevenlabs.io → Developers → API Keys, coche-la, puis relance.")
        r.raise_for_status()
        secret = r.json()["value"]
        self.ws = await websockets.connect(
            f"wss://api.elevenlabs.io/v1/convai/realtime?model={self.modele}",
            additional_headers={"Authorization": f"Bearer {secret}"},
            max_size=None,
        )
        await self._envoyer({"type": "session.update", "session": self._session()})
        self._ecoute_ws = asyncio.create_task(self._recevoir())
        self.journal.log("eleven", f"connecté ({self.modele}, voix {self.voix})")

    def nettoyer(self, texte: str) -> str:
        # « Merci Lucie. [calm] Quel est… » : les balises de ton ne sont pas prononcées.
        return re.sub(r"\s+", " ", re.sub(r"\[[^\]]{1,20}\]", " ", texte)).strip()

    async def repondre(self, texte: str) -> None:
        if not texte:
            # Eleven ne répond pas si la conversation est vide : on lui donne le signal de début d'appel.
            debut = (f"(L'appel commence. Dis exactement, mot pour mot : « {self.cfg.accueil} »)" if self.cfg.accueil
                     else "(L'appel commence : salue l'utilisateur en une phrase courte.)")
            await self._envoyer({"type": "conversation.item.create",
                                 "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": debut}]}})
        await super().repondre(texte)

    async def oublier_tour(self, deja_repondu: bool = False) -> None:
        # Eleven Realtime v1 ne sait pas effacer un message (conversation.item.delete) : on ne fait rien.
        # Le bruit n'a de toute façon pas déclenché de réponse (seul notre filtre décide).
        if self._items_tour and not deja_repondu:
            self._items_tour.pop()


if __name__ == "__main__":
    lancer(BotEleven)
