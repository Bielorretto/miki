"""
Oreille du programme 2 : Deepgram nova-3 en continu.

Seul l'audio utile (la voix détectée par l'écoute locale) est envoyé : le bruit avant / après la phrase
n'arrive jamais chez Deepgram. À la fin du tour on envoie « Finalize » : Deepgram rend le texte final
en ~100-300 ms au lieu d'attendre son propre silence (qui n'arrive jamais dans le bruit).

Les transcriptions partielles servent à confirmer un barge-in pendant que l'utilisateur parle encore.

Au téléphone (par_tour=True) : une connexion neuve à chaque tour, ouverte dès la fin du tour précédent (l'ouvrir
au premier son prend 0,6-1 s : le son arriverait en rafale et Deepgram en perd la fin, « Mon prénom, c'est » sans
« Adam »). Une connexion qui n'a encore reçu aucun son est fermée par Deepgram en 2-4 s, même avec des KeepAlive :
on lui envoie donc un souffle très faible (100 ms à -70 dB toutes les ~0,5 s) tant que personne ne parle.
Si Deepgram coupe quand même la connexion en plein tour, le tour entier est renvoyé en fichier (secours).
Une seule connexion pour tout l'appel reçoit les morceaux de voix recollés bout à bout ; dans le bruit elle
s'encrasse et rend du vide (appel du 10/11 17h27 : 9 tours vides sur 18, 3 avec une connexion par tour).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Awaitable, Callable

import httpx
import numpy as np
import websockets

from commun.audio import float_vers_pcm16
from commun.config import env


class Deepgram:
    def __init__(self, langue: str, sur_partiel: Callable[[str], Awaitable[None]], log: Callable[[str, str], None],
                 par_tour: bool = False) -> None:
        self.langue = langue
        self.par_tour = par_tour
        self._souffle = np.random.default_rng(0).normal(0, 10, 1600).astype(np.int16).tobytes()  # 100 ms à -70 dB
        self._ws_tour = None  # connexion qui a reçu la voix de ce tour
        self._casse = False  # la connexion a changé en plein tour : le début du tour est perdu côté flux
        self._ouverture: asyncio.Task | None = None
        self.sur_partiel = sur_partiel
        self.log = log
        self.cle = env("DEEPGRAM_API_KEY")
        if not self.cle:
            raise SystemExit("DEEPGRAM_API_KEY manquante dans .env")
        self.modele = env("DEEPGRAM_MODELE", "nova-3")
        self.ws = None
        self.file: asyncio.Queue[bytes | str] = asyncio.Queue()
        self._finals: list[str] = []
        self._partiel = ""
        self._finalise: asyncio.Event = asyncio.Event()
        self._taches: list[asyncio.Task] = []
        self._dernier_envoi = time.monotonic()

    def _url(self) -> str:
        p = f"model={self.modele}&language={self.langue}&encoding=linear16&sample_rate=16000&channels=1"
        return f"wss://api.deepgram.com/v1/listen?{p}&interim_results=true&punctuate=true&smart_format=true&endpointing=false"

    async def connecter(self) -> None:
        self.ws = await websockets.connect(self._url(), additional_headers={"Authorization": f"Token {self.cle}"}, max_size=None)
        self._taches = [asyncio.create_task(self._envoyer()), asyncio.create_task(self._recevoir()), asyncio.create_task(self._garder())]

    # ------------------------------------------------------------------ envoi

    def audio(self, pcm: np.ndarray) -> None:
        self.file.put_nowait(float_vers_pcm16(pcm))

    def nouveau_tour(self) -> None:
        self._finals = []
        self._partiel = ""
        self._ws_tour = None
        self._casse = False

    async def _envoyer(self) -> None:
        while True:
            m = await self.file.get()
            if self._ouverture is not None and not self._ouverture.done():
                await asyncio.wait([self._ouverture])  # connexion du tour suivant en cours d'ouverture
            for _ in range(2):
                try:
                    if self.ws is None:
                        await self._reconnecter()
                        if self.ws is None:
                            break
                    await self.ws.send(m)
                    self._dernier_envoi = time.monotonic()
                    if isinstance(m, bytes) and m is not self._souffle:
                        if self._ws_tour is None:
                            self._ws_tour = self.ws
                        elif self._ws_tour is not self.ws:
                            self._casse = True
                    break
                except websockets.ConnectionClosed:
                    self.ws = None

    async def _garder(self) -> None:
        """Sans audio pendant 10 s Deepgram ferme la connexion : on envoie un KeepAlive (ou un souffle, voir plus haut)."""
        if self.par_tour:
            while True:
                await asyncio.sleep(0.25)
                if time.monotonic() - self._dernier_envoi > 0.5:
                    self.file.put_nowait(self._souffle)
        while True:
            await asyncio.sleep(3)
            if time.monotonic() - self._dernier_envoi > 4:
                self.file.put_nowait(json.dumps({"type": "KeepAlive"}))

    async def _reconnecter(self) -> None:
        self.log("deepgram", "reconnexion…")
        try:
            self.ws = await websockets.connect(self._url(), additional_headers={"Authorization": f"Token {self.cle}"}, max_size=None)
            self._taches.append(asyncio.create_task(self._recevoir()))
        except Exception as e:
            self.log("erreur", f"deepgram : {e!r}")
            self.ws = None

    async def _connexion_neuve(self) -> None:
        """Fin de tour : connexion neuve pour le tour suivant ; l'ancienne est fermée, ses derniers messages ignorés."""
        ancienne = self.ws
        try:
            self.ws = await websockets.connect(self._url(), additional_headers={"Authorization": f"Token {self.cle}"}, max_size=None)
            self._taches.append(asyncio.create_task(self._recevoir()))
            self._dernier_envoi = 0.0  # souffle tout de suite
        except Exception as e:
            self.log("erreur", f"deepgram connexion neuve : {e!r}")
            self.ws = None  # reconnexion au prochain envoi
        if ancienne is not None:
            await self._fermer(ancienne)

    async def _fermer(self, ws) -> None:
        try:
            await ws.send(json.dumps({"type": "CloseStream"}))
            await asyncio.wait_for(ws.close(), 2)
        except Exception:
            pass

    # ------------------------------------------------------------------ réception

    async def _recevoir(self) -> None:
        ws = self.ws
        try:
            async for brut in ws:
                ev = json.loads(brut)
                if ev.get("type") != "Results" or ws is not self.ws:
                    continue
                texte = ev["channel"]["alternatives"][0].get("transcript", "")
                if ev.get("is_final"):
                    if texte:
                        self._finals.append(texte)
                    self._partiel = ""
                    if ev.get("from_finalize"):
                        self._finalise.set()
                else:
                    self._partiel = texte
                if texte:
                    await self.sur_partiel(" ".join(self._finals + ([self._partiel] if self._partiel else [])))
        except websockets.ConnectionClosed:
            pass
        if self.ws is ws:
            self.ws = None  # reconnexion au prochain envoi
            self.log("deepgram", f"connexion fermée ({ws.close_code} {ws.close_reason})")

    # ------------------------------------------------------------------ fin du tour

    async def finaliser(self, audio: np.ndarray) -> str:
        """Texte complet du tour. Si le flux ne répond pas à temps : envoi du fichier (secours)."""
        self._finalise.clear()
        await asyncio.sleep(0)  # laisse partir le son encore dans la file
        casse = self._casse or (self._ws_tour is not None and self._ws_tour is not self.ws)
        if casse:
            # Connexion coupée en plein tour (par Deepgram) : le flux n'a pas tout le tour → envoi du fichier.
            self.log("deepgram", "connexion coupée pendant le tour")
            texte = ""
        else:
            self.file.put_nowait(json.dumps({"type": "Finalize"}))
            try:
                await asyncio.wait_for(self._finalise.wait(), 1.0)
            except asyncio.TimeoutError:
                self.log("deepgram", "Finalize sans réponse, on garde ce qu'on a")
            texte = " ".join(self._finals + ([self._partiel] if self._partiel else [])).strip()
        if not self._finalise.is_set() and len(audio) > 3200:
            # Le flux n'a pas répondu (connexion coupée…) : on envoie l'audio du tour en une fois.
            try:
                texte = await self._secours(audio)
                self.log("deepgram", "texte obtenu par le secours (envoi du fichier)")
            except Exception as e:
                self.log("erreur", f"deepgram secours : {e!r}")
        self.nouveau_tour()
        if self.par_tour:
            self._ouverture = asyncio.create_task(self._connexion_neuve())
        return texte

    async def _secours(self, audio: np.ndarray) -> str:
        url = f"https://api.deepgram.com/v1/listen?model={self.modele}&language={self.langue}&encoding=linear16&sample_rate=16000&punctuate=true&smart_format=true"
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(url, content=float_vers_pcm16(audio), headers={"Authorization": f"Token {self.cle}", "Content-Type": "audio/raw"})
            r.raise_for_status()
            return r.json()["results"]["channels"][0]["alternatives"][0]["transcript"]

    async def fermer(self) -> None:
        for t in self._taches:
            t.cancel()
        if self.ws:
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
                await self.ws.close()
            except Exception:
                pass
