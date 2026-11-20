"""
Journal d'une session : tout ce qui se passe, à la milliseconde, + l'enregistrement du micro et de la voix de l'IA.
Même format que l'app (lignes de conversation + journal {t, ev, info}) : analysable avec tools/call.js.

Fichiers dans sessions/<date>/ : journal.txt, session.json, micro.wav (après anti-écho), ia.wav.
"""

from __future__ import annotations

import json
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from .config import RACINE, env


class Journal:
    def __init__(self, programme: str) -> None:
        self.programme = programme
        self.t0 = time.monotonic()
        self.debut = datetime.now()
        self.entrees: list[dict] = []
        self.lignes: list[dict] = []
        self.dossier = RACINE / "sessions" / f"{self.debut:%Y-%m-%d_%H-%M-%S}_{programme}"
        self.dossier.mkdir(parents=True, exist_ok=True)
        self._fichier = (self.dossier / "journal.txt").open("w", encoding="utf-8")

    def t(self) -> int:
        return int((time.monotonic() - self.t0) * 1000)

    def log(self, ev: str, info: str = "", afficher: bool = True) -> None:
        e = {"t": self.t(), "ev": ev, "info": info}
        self.entrees.append(e)
        ligne = f"{e['t'] / 1000:7.2f}s  {ev:11s} {info}"
        self._fichier.write(ligne + "\n")
        self._fichier.flush()
        if afficher:
            print(ligne, flush=True)

    def ligne(self, role: str, texte: str, ignore: str | None = None, coupe: bool = False) -> None:
        l = {"id": str(len(self.lignes)), "role": role, "text": texte}
        if ignore:
            l["ignored"] = ignore
        if coupe:
            l["interrupted"] = True
        self.lignes.append(l)

    def terminer(self, micro: list[np.ndarray], ia: list[np.ndarray] | None) -> Path:
        self._fichier.close()
        for nom, blocs in (("micro.wav", micro), ("ia.wav", ia or [])):
            if not blocs:
                continue
            x = np.concatenate(blocs)
            with wave.open(str(self.dossier / nom), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        data = {
            "id": f"{self.programme}-{self.debut:%Y%m%d%H%M%S}",
            "ts": int(self.debut.timestamp() * 1000),
            "topic": f"test_vocal / {self.programme}",
            "seconds": round(time.monotonic() - self.t0),
            "speaker": True,
            "lines": self.lignes,
            "log": self.entrees,
            "summary": "",
            "errors": [],
            "hasAudio": bool(micro),
            "device": {"os": "test_vocal", "version": self.programme},
        }
        (self.dossier / "session.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
        self._envoyer(data)
        return self.dossier

    def _envoyer(self, data: dict) -> None:
        """Envoi optionnel au serveur d'analyse (pour que Claude puisse lire la session)."""
        url, secret = env("UPLOAD_URL"), env("APP_SECRET")
        if not url or not secret:
            return
        try:
            import httpx

            h = {"x-app-secret": secret}
            httpx.post(f"{url}/calls", json=data, headers=h, timeout=20).raise_for_status()
            wav = self.dossier / "micro.wav"
            if wav.exists():
                httpx.put(f"{url}/calls/{data['id']}/audio", content=wav.read_bytes(), headers={**h, "Content-Type": "audio/wav"}, timeout=60)
            print(f"Session envoyée pour analyse : {data['id']}")
        except Exception as e:
            print(f"Envoi impossible : {e}")
