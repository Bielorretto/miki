"""
Programme 1 : même architecture que l'app (OpenAI Realtime, speech-to-speech).

  micro → anti-écho → écoute locale (Silero + volume + Smart Turn) → seul l'audio utile part chez OpenAI
  → transcription du tour → filtre / juge → response.create → voix de l'IA
  Barge-in : response.cancel + conversation.item.truncate à l'endroit exact où l'utilisateur a coupé.

OpenAI ne décide jamais seul (turn_detection = null) : c'est notre écoute qui dit quand répondre.

Lancer :  python -m realtime.bot [--audio mac|pulse|fichier:chemin.wav] [--juge groq|openai|mistral]
"""

from __future__ import annotations

import asyncio
import base64
import json
import time

import numpy as np
import websockets

from commun.audio import float_vers_pcm16, pcm16_vers_float, resample
from commun.config import Config, env
from commun.conversation import Conversation
from commun.lancement import lancer

RATE_OPENAI = 24000


class BotRealtime(Conversation):
    nom = "realtime"
    accueil_par_instructions = True  # l'accueil est demandé dans response.create (Eleven : par un message)

    def __init__(self, cfg: Config) -> None:
        super().__init__(cfg)
        self.modele = env("REALTIME_MODEL", "gpt-realtime-2.1-mini")
        self.voix = env("REALTIME_VOICE", "marin")
        self.ws = None
        self._attentes: dict[str, asyncio.Future] = {}  # item_id → transcription
        self._commit: asyncio.Future | None = None
        self._fin_reponse: asyncio.Event | None = None
        self._item_ia: str | None = None
        self._texte_ia = ""
        self._ms_ia = 0.0  # durée de l'audio reçu pour la réponse en cours
        self._items_tour: list[str] = []
        self._items_repondus: list[str] = []
        self._resp_id: str | None = None
        self._annulees: set[str] = set()
        self._ecoute_ws: asyncio.Task | None = None
        self._active = asyncio.Event()  # une réponse est en cours côté serveur
        self._t_reponse = 0.0
        self._dernier_create: dict | None = None

    async def connecter(self) -> None:
        cle = env("OPENAI_API_KEY")
        if not cle:
            raise SystemExit("OPENAI_API_KEY manquante dans .env")
        self.ws = await websockets.connect(
            f"wss://api.openai.com/v1/realtime?model={self.modele}",
            additional_headers={"Authorization": f"Bearer {cle}"},
            max_size=None,
        )
        transcription = {"model": env("TRANSCRIBE_MODEL", "gpt-4o-transcribe")}
        if self.cfg.langue != "multi":
            transcription["language"] = self.cfg.langue
        await self._envoyer({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": self.cfg.consignes,
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": RATE_OPENAI},
                        "transcription": transcription,
                        # Le bruit est déjà traité chez nous (anti-écho + écoute) : rien à faire côté OpenAI.
                        "noise_reduction": None,
                        # Personne d'autre que nous ne décide de la fin du tour.
                        "turn_detection": None,
                    },
                    "output": {"format": {"type": "audio/pcm", "rate": RATE_OPENAI}, "voice": self.voix},
                },
            },
        })
        self._ecoute_ws = asyncio.create_task(self._recevoir())
        self.journal.log("openai", f"connecté ({self.modele}, voix {self.voix})")

    async def _envoyer(self, ev: dict) -> None:
        await self.ws.send(json.dumps(ev))

    # ------------------------------------------------------------------ réception

    async def _recevoir(self) -> None:
        try:
            async for brut in self.ws:
                ev = json.loads(brut)
                t = ev.get("type", "")
                if ev.get("response_id") in self._annulees or ev.get("response", {}).get("id") in self._annulees:
                    if t == "response.done":
                        self._active.clear()  # la réponse coupée est bien finie côté serveur
                    continue  # restes d'une réponse coupée
                if t == "response.created":
                    self._resp_id = ev["response"]["id"]
                    self._active.set()
                elif t == "response.output_audio.delta":
                    if not self.repond:
                        continue  # morceau arrivé après une coupure
                    if self._ms_ia == 0 and self._t_reponse:
                        self.journal.log("voix", f"1er son en {(time.perf_counter() - self._t_reponse) * 1000:.0f} ms")
                    pcm = pcm16_vers_float(base64.b64decode(ev["delta"]))
                    self._ms_ia += len(pcm) / RATE_OPENAI * 1000
                    self.audio.lecteur.ajouter(pcm, RATE_OPENAI)
                elif t == "response.output_audio_transcript.delta":
                    self._texte_ia += ev.get("delta", "")
                elif t == "response.output_item.added":
                    item = ev.get("item", {})
                    if item.get("role") == "assistant":
                        self._item_ia = item.get("id")
                elif t == "input_audio_buffer.committed":
                    if self._commit and not self._commit.done():
                        self._commit.set_result(ev["item_id"])
                elif t == "conversation.item.input_audio_transcription.completed":
                    f = self._attentes.pop(ev["item_id"], None)
                    if f and not f.done():
                        f.set_result(ev.get("transcript", ""))
                elif t == "conversation.item.input_audio_transcription.failed":
                    f = self._attentes.pop(ev["item_id"], None)
                    if f and not f.done():
                        f.set_result("")
                    self.journal.log("erreur", f"transcription : {ev.get('error')}")
                elif t == "response.done":
                    if ev.get("response", {}).get("id") in (self._resp_id, None):
                        self._active.clear()
                    statut = ev.get("response", {}).get("status")
                    if statut == "completed" and self._texte_ia.strip():
                        self.ia_a_dit(self.nettoyer(self._texte_ia))
                    elif statut == "failed":
                        self.journal.log("erreur", f"réponse : {ev['response'].get('status_details')}")
                    if self._fin_reponse:
                        self._fin_reponse.set()
                elif t == "error":
                    err = ev.get("error", {})
                    # Annuler une réponse déjà finie n'est pas grave.
                    if "active response" in (err.get("message") or "") and self._dernier_create and self.repond:
                        # L'ancienne réponse n'était pas encore finie côté serveur : on l'annule et on relance.
                        asyncio.create_task(self._relancer())
                    elif err.get("code") not in ("response_cancel_not_active",):
                        self.journal.log("erreur", f"openai : {err.get('message')}")
        except websockets.ConnectionClosed as e:
            self.journal.log("erreur", f"connexion OpenAI fermée : {e}")

    # ------------------------------------------------------------------ ce que demande la conversation

    async def transcrire(self, audio: np.ndarray) -> str:
        if len(audio) < 1600:
            return ""
        x = resample(audio, 16000, RATE_OPENAI)
        await self._envoyer({"type": "input_audio_buffer.clear"})
        for i in range(0, len(x), RATE_OPENAI):  # morceaux d'1 s
            await self._envoyer({"type": "input_audio_buffer.append", "audio": base64.b64encode(float_vers_pcm16(x[i : i + RATE_OPENAI])).decode()})
        self._commit = asyncio.get_running_loop().create_future()
        await self._envoyer({"type": "input_audio_buffer.commit"})
        try:
            item = await asyncio.wait_for(self._commit, 3)
            f = asyncio.get_running_loop().create_future()
            self._attentes[item] = f
            self._items_tour.append(item)
            return (await asyncio.wait_for(f, 6)).strip()
        except asyncio.TimeoutError:
            self.journal.log("erreur", "transcription trop lente")
            return ""

    async def oublier_tour(self, deja_repondu: bool = False) -> None:
        # Le bruit ne doit pas rester dans la mémoire du modèle.
        ids = (self._items_repondus + ([self._item_ia] if self._item_ia else [])) if deja_repondu else self._items_tour[-1:]
        for i in ids:
            await self._envoyer({"type": "conversation.item.delete", "item_id": i})
        if not deja_repondu and self._items_tour:
            self._items_tour.pop()

    async def repondre(self, texte: str) -> None:
        self._items_repondus, self._items_tour = self._items_tour, []
        self._texte_ia = ""
        self._ms_ia = 0.0
        self._item_ia = None
        self._resp_id = None
        self._fin_reponse = asyncio.Event()
        # Après une coupure, le serveur doit avoir fini d'annuler avant qu'on relance une réponse.
        if self._active.is_set():
            for _ in range(30):
                if not self._active.is_set():
                    break
                await asyncio.sleep(0.05)
            self._active.clear()
        self._t_reponse = time.perf_counter()
        ev: dict = {"type": "response.create"}
        if not texte and self.accueil_par_instructions:
            debut = (f"Commence l'appel en disant exactement, mot pour mot : « {self.cfg.accueil} »" if self.cfg.accueil
                     else "Commence par saluer l'utilisateur en une phrase courte.")
            ev["response"] = {"instructions": self.cfg.consignes + "\n\n" + debut}
        self._dernier_create = ev
        await self._envoyer(ev)
        await self._fin_reponse.wait()

    async def _relancer(self) -> None:
        await self._envoyer({"type": "response.cancel"})
        await asyncio.sleep(0.3)
        if self.repond and self._dernier_create:
            self.journal.log("relance", "réponse précédente pas finie côté serveur → annulée, nouvelle réponse")
            await self._envoyer(self._dernier_create)

    def nettoyer(self, texte: str) -> str:
        """Texte de l'IA tel qu'il est prononcé (Eleven y ajoute des balises de ton)."""
        return texte.strip()

    def texte_ia_courant(self) -> str:
        return self.nettoyer(self._texte_ia) if self.repond else ""

    async def arreter_reponse(self) -> str:
        joue = self.audio.lecteur.joue_ms
        if self._resp_id:
            self._annulees.add(self._resp_id)
        if self._fin_reponse:
            self._fin_reponse.set()
        await self._envoyer({"type": "response.cancel"})
        if self._item_ia:
            # L'IA ne se souviendra que de ce que l'utilisateur a vraiment entendu.
            await self._envoyer({"type": "conversation.item.truncate", "item_id": self._item_ia, "content_index": 0, "audio_end_ms": int(min(joue, self._ms_ia))})
        mots = self.nettoyer(self._texte_ia).split()
        n = round(len(mots) * min(1.0, joue / self._ms_ia)) if self._ms_ia else 0
        entendu = " ".join(mots[:n])
        self.ia_texte = self.nettoyer(self._texte_ia)  # pour reconnaître son écho
        return entendu

    async def fermer(self) -> None:
        if self._ecoute_ws:
            self._ecoute_ws.cancel()
        if self.ws:
            await self.ws.close()


if __name__ == "__main__":
    lancer(BotRealtime)
