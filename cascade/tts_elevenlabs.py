"""
Voix du programme 2 : ElevenLabs, voix Lucie.

  - eleven_v3_conversational (défaut) : la voix la plus naturelle, la même famille que Eleven Realtime.
    Pas de websocket pour ce modèle : une requête HTTP en flux par phrase. Chaque phrase est demandée
    dès qu'elle est écrite (la suivante se prépare pendant que la précédente est lue) et jouée dans l'ordre.
  - eleven_flash_v2_5 (ELEVEN_MODELE=eleven_flash_v2_5 dans .env) : websocket, un peu plus rapide.

Les phrases du penseur sont envoyées dès qu'elles sont prêtes ; le son revient par petits morceaux
avec l'alignement (à quel moment chaque lettre est prononcée). Grâce à ça, en cas de barge-in,
on sait exactement quels mots l'utilisateur a entendus.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path
from typing import AsyncIterator

import numpy as np

import httpx
import websockets

from commun.audio import Lecteur, pcm16_vers_float
from commun.config import env

DOSSIER_PRET = Path(__file__).resolve().parent.parent / "cache" / "phrases"  # phrases fixes déjà prononcées
RATE_TTS = 24000  # meilleure qualité que 16 kHz (voix moins étouffée)


class ElevenLabs:
    def __init__(self) -> None:
        self.cle = env("ELEVEN_API_KEY")
        self.voix = env("TTS_VOICE_ID")
        if not self.cle or not self.voix:
            raise SystemExit("ELEVEN_API_KEY et TTS_VOICE_ID nécessaires dans .env")
        self.modele = env("ELEVEN_MODELE", "eleven_v3_conversational")
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5), headers={"xi-api-key": self.cle},
                                      limits=httpx.Limits(keepalive_expiry=120))
        # Lettres prononcées et leur moment (ms depuis le début de la réponse).
        self.lettres: list[tuple[float, str]] = []
        self.texte = ""
        self._ms = 0.0
        self.premier_son: asyncio.Event = asyncio.Event()

    def _url(self) -> str:
        return (
            f"wss://api.elevenlabs.io/v1/text-to-speech/{self.voix}/stream-input"
            f"?model_id={self.modele}&output_format=pcm_{RATE_TTS}&sync_alignment=true&auto_mode=true"
        )

    @property
    def en_websocket(self) -> bool:
        return "flash" in self.modele or "turbo_v2" in self.modele or "multilingual" in self.modele

    async def chauffer(self) -> None:
        """Ouvre la connexion HTTPS à l'avance (gagne ~100 ms sur la première phrase)."""
        if not self.en_websocket:
            try:
                await self.http.get("https://api.elevenlabs.io/v1/models")
            except httpx.HTTPError:
                pass

    async def parler(self, phrases: AsyncIterator[str], lecteur: Lecteur) -> str:
        """Lit les phrases au fur et à mesure ; renvoie le texte complet."""
        if not self.en_websocket:
            return await self._parler_http(phrases, lecteur)
        self.lettres, self.texte, self._ms = [], "", 0.0
        self.premier_son.clear()
        # Connexion ouverte pendant que le penseur réfléchit (on ne perd pas de temps).
        async def ouvrir():
            return await websockets.connect(self._url(), additional_headers={"xi-api-key": self.cle}, max_size=None)

        connexion = asyncio.create_task(ouvrir())
        file: asyncio.Queue[str | None] = asyncio.Queue()

        async def penser():
            try:
                async for p in phrases:
                    self.texte += (" " if self.texte else "") + p
                    await file.put(p)
            finally:
                await file.put(None)

        tache_penseur = asyncio.create_task(penser())
        ws = await connexion
        try:
            await ws.send(json.dumps({"text": " ", "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "speed": 1.0}}))

            async def envoyer():
                while (p := await file.get()) is not None:
                    await ws.send(json.dumps({"text": p + " "}))
                await ws.send(json.dumps({"text": ""}))  # fin du texte

            tache_envoi = asyncio.create_task(envoyer())
            async for brut in ws:
                m = json.loads(brut)
                if m.get("audio"):
                    pcm = pcm16_vers_float(base64.b64decode(m["audio"]))
                    al = m.get("alignment") or {}
                    for c, t in zip(al.get("chars", []), al.get("charStartTimesMs", [])):
                        self.lettres.append((self._ms + t, c))
                    self._ms += len(pcm) / RATE_TTS * 1000
                    lecteur.ajouter(pcm, RATE_TTS)
                    self.premier_son.set()
                if m.get("isFinal"):
                    break
            await tache_envoi
            await tache_penseur
        finally:
            tache_penseur.cancel()
            await ws.close()
        return self.texte

    async def _parler_http(self, phrases: AsyncIterator[str], lecteur: Lecteur) -> str:
        self.lettres, self.texte, self._ms = [], "", 0.0
        self.premier_son.clear()
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voix}/stream/with-timestamps?output_format=pcm_{RATE_TTS}"
        reglages = {"stability": 0.5, "similarity_boost": 0.8, "speed": 1.0}

        async def demander(texte: str, precedent: str, sortie: asyncio.Queue) -> None:
            """Une phrase → morceaux (son, alignement) dans sa file, puis None."""
            corps = {"text": texte, "model_id": self.modele, "voice_settings": reglages}
            if precedent and "v3" not in self.modele:  # v3 ne l'accepte pas encore
                corps["previous_text"] = precedent[-300:]  # intonation continue d'une phrase à l'autre
            try:
                async with limite:
                    for essai in range(3):
                        async with self.http.stream("POST", url, json=corps) as r:
                            if r.status_code == 429 and essai < 2:  # trop de requêtes en même temps : on réessaie
                                await asyncio.sleep(0.3)
                                continue
                            if r.status_code >= 400:
                                raise RuntimeError(f"ElevenLabs {r.status_code} : {(await r.aread())[:200]!r}")
                            async for ligne in r.aiter_lines():
                                if ligne.strip():
                                    await sortie.put(json.loads(ligne))
                            break
            finally:
                await sortie.put(None)

        files: asyncio.Queue[asyncio.Queue | None] = asyncio.Queue()
        # Abonnement ElevenLabs : 5 requêtes simultanées maximum (Deepgram/juge à part) → 3 phrases à la fois.
        limite = asyncio.Semaphore(3)
        taches: list[asyncio.Task] = []

        async def penser():
            try:
                async for p in phrases:
                    precedent = self.texte
                    self.texte += (" " if self.texte else "") + p
                    q: asyncio.Queue = asyncio.Queue()
                    taches.append(asyncio.create_task(demander(p, precedent, q)))
                    await files.put(q)
            finally:
                await files.put(None)

        tache_penseur = asyncio.create_task(penser())
        try:
            while (q := await files.get()) is not None:
                debut = self._ms
                reste = b""
                while (m := await q.get()) is not None:
                    if m.get("audio_base64"):
                        brut = reste + base64.b64decode(m["audio_base64"])
                        coupe = len(brut) - len(brut) % 2
                        brut, reste = brut[:coupe], brut[coupe:]
                        pcm = pcm16_vers_float(brut)
                        al = m.get("alignment") or {}
                        for c, t in zip(al.get("characters", []), al.get("character_start_times_seconds", [])):
                            self.lettres.append((debut + t * 1000, c))
                        self._ms += len(pcm) / RATE_TTS * 1000
                        lecteur.ajouter(pcm, RATE_TTS)
                        self.premier_son.set()
                self.lettres.append((self._ms, " "))
            await tache_penseur
            for t in taches:
                await t  # remonte une éventuelle erreur ElevenLabs
        finally:
            tache_penseur.cancel()
            for t in taches:
                t.cancel()
        return self.texte

    # ------------------------------------------------------------------ phrases toutes prêtes

    def _fichier_pret(self, texte: str) -> Path:
        cle = hashlib.sha1(f"{self.voix}|{self.modele}|{texte}".encode()).hexdigest()[:16]
        return DOSSIER_PRET / f"{cle}.npz"

    async def preparer(self, texte: str) -> None:
        """Enregistre une phrase fixe une fois pour toutes (sessions suivantes : lue depuis le disque)."""
        f = self._fichier_pret(texte)
        if f.exists():
            return

        class Capture:
            def __init__(self) -> None:
                self.blocs: list[np.ndarray] = []

            def ajouter(self, pcm: np.ndarray, rate: int) -> None:
                self.blocs.append(pcm)

        async def une():
            yield texte

        c = Capture()
        await self._parler_http(une(), c)  # type: ignore[arg-type]
        if c.blocs:
            DOSSIER_PRET.mkdir(parents=True, exist_ok=True)
            np.savez(f, pcm=np.concatenate(c.blocs), t=np.array([t for t, _ in self.lettres]),
                     c=np.array([ch for _, ch in self.lettres]))

    def dire_pret(self, texte: str, lecteur: Lecteur) -> bool:
        """Phrase fixe déjà enregistrée : envoyée tout de suite au lecteur, sans appel à ElevenLabs."""
        f = self._fichier_pret(texte)
        if not f.exists():
            return False
        d = np.load(f)
        self.texte, self._ms = texte, len(d["pcm"]) / RATE_TTS * 1000
        self.lettres = list(zip(d["t"].tolist(), d["c"].tolist()))
        lecteur.ajouter(d["pcm"], RATE_TTS)
        self.premier_son.set()
        return True

    def entendu(self, joue_ms: float) -> str:
        """Les mots réellement prononcés avant joue_ms."""
        texte = "".join(c for t, c in self.lettres if t <= joue_ms)
        return texte.strip()
