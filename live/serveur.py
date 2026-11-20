"""
Programme 5 : le numéro Twilio parle directement à GPT-Live (le modèle du mode vocal de ChatGPT), sans cascade.

  Appel → Twilio (μ-law 8 kHz) ⇄ ce pont ⇄ wss://api.openai.com/v1/live/sessions (audio/pcmu 8 kHz : aucun recodage)

  - GPT-Live écoute et parle en même temps (full-duplex) : tours de parole, « mhmm », interruptions et bruit sont gérés par
    le modèle lui-même. Pas de Deepgram, pas de juge, pas d'ElevenLabs, aucun modèle gpt-oss.
  - Quand il faut réfléchir, GPT-Live confie la question à GPT-5.5 en coulisses (délégation « responses », côté OpenAI),
    sans arrêter la conversation.
  - Interruption : l'API ne signale pas quand le modèle s'arrête de parler ; sa voix arrive plus vite que le temps réel et
    attend chez nous. Si l'appelant a dit au moins 2 mots depuis le dernier son reçu du modèle et que le modèle se tait
    depuis 0,35 s, on jette la voix en attente (et celle de Twilio : « clear »).
  - Fiche du dossier : rédigée à la fin par GPT-5.5, à partir de la transcription (sessions/<date>_live/).

Lancer :  bash lancer.sh 5   (ou : python -m live.serveur [--appeler 06…])
Réglages (.env, facultatifs) : LIVE_MODELE (gpt-live-1.1), LIVE_VOIX (brise | sillage), LIVE_PENSEUR (gpt-5.5),
  LIVE_REFLEXION (low | medium | high, défaut medium).
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
import wave

import httpx
import numpy as np
import websockets

from appel.serveur import numero_a_appeler, servir
from cascade import sisiao
from cascade.fiche import CONSIGNES as CONSIGNES_FICHE
from commun.audio import ulaw_vers_float
from commun.config import charger_env, env
from commun.journal import Journal
from commun.roles import role

URL = "wss://api.openai.com/v1/live/sessions"
TRAME = 160  # 20 ms de μ-law 8 kHz
AVANCE = 3  # trames envoyées d'avance à Twilio (60 ms) : le reste attend chez nous, pour pouvoir le jeter
MOTS_COUPURE = 2
SILENCE_MODELE_S = 0.35

DELEGATION = """

QUAND IL FAUT RÉFLÉCHIR
Pour une question de fond (droits, papiers, police, santé, démarches, situation compliquée), ne devine jamais : confie-la à ton collègue en coulisses et continue la conversation pendant qu'il cherche."""

COULISSES = """Tu travailles en coulisses pour l'assistant vocal du 115 (urgence sociale, France), qui parle au téléphone avec une personne sans abri ou en grande difficulté. Il te confie une question ; il dira lui-même ta réponse.
Réfléchis bien, puis réponds en français, en une à trois phrases courtes et simples, faciles à dire au téléphone : pas de liste, pas d'abréviation, pas de lien.
N'invente jamais une adresse, un horaire, un numéro ou une règle : si tu n'es pas sûr, dis ce qui est sûr et ce qu'un écoutant du 115 pourra vérifier. En cas de danger pour la santé ou la vie, dis-le clairement (15, 112). Ne pose aucune question : c'est l'assistant qui mène l'entretien."""


class AppelLive:
    def __init__(self, twilio_ws) -> None:
        self.tw = twilio_ws
        self.oa = None
        self.journal = Journal("live")
        self.sid: str | None = None
        self.sortie = bytearray()  # voix du modèle pas encore envoyée à Twilio
        self.dernier_son = 0.0  # dernier morceau de voix reçu du modèle
        self.mots_appelant = 0  # mots de l'appelant depuis ce dernier morceau
        self.lignes: list[dict] = []  # transcription : {"role", "content"}
        self.micro: list[bytes] = []
        self.ia: list[bytes] = []
        self.secondes = 0.0
        self.t0 = time.monotonic()
        self.telephone = ""  # numéro de l'appelant (paramètre « de » de Twilio)

    # ------------------------------------------------------------------ transcription

    def _ajouter(self, qui: str, texte: str) -> None:
        if self.lignes and self.lignes[-1]["role"] == qui:
            self.lignes[-1]["content"] += texte
        else:
            if self.lignes:
                d = self.lignes[-1]
                self.journal.log("IA" if d["role"] == "assistant" else "entendu", f"« {d['content'].strip()} »")
                self.journal.ligne(d["role"], d["content"].strip())
            self.lignes.append({"role": qui, "content": texte})

    # ------------------------------------------------------------------ GPT-Live

    async def _ouvrir(self) -> None:
        consignes, accueil = role("115", False)
        self.oa = await websockets.connect(URL, additional_headers={"Authorization": f"Bearer {env('OPENAI_API_KEY')}"}, max_size=None)
        session = {
            "model": env("LIVE_MODELE", "gpt-live-1.1"),
            "instructions": consignes + DELEGATION,
            "audio": {"format": {"type": "audio/pcmu", "rate": 8000}, "output": {"voice": env("LIVE_VOIX", "brise")}},
            "input": [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text":
                       f"L'appel commence. Parle français. Dis d'abord exactement : « {accueil} » Puis écoute la réponse."}]}],
            "delegation": {"type": "responses", "responses": {
                "model": env("LIVE_PENSEUR", "gpt-5.5"),
                "instructions": COULISSES,
                "reasoning": {"effort": env("LIVE_REFLEXION", "medium")},
            }},
        }
        await self.oa.send(json.dumps({"type": "session.start", "event_id": "debut", "session": session}))
        self.journal.log("live", f"{session['model']} · voix {session['audio']['output']['voice']} · coulisses "
                                 f"{session['delegation']['responses']['model']} ({session['delegation']['responses']['reasoning']['effort']})")

    async def _ecouter_openai(self) -> None:
        async for brut in self.oa:
            m = json.loads(brut)
            t = m.get("type", "")
            if t == "session.output_audio.delta":
                b = base64.b64decode(m["delta"])
                self.sortie += b
                self.ia.append(b)
                self.dernier_son = time.monotonic()
                self.mots_appelant = 0
            elif t == "session.input_transcript.delta":
                self.mots_appelant += len(m.get("delta", "").split())
                self._ajouter("user", m.get("delta", ""))
            elif t == "session.output_transcript.delta":
                self._ajouter("assistant", m.get("delta", ""))
            elif t == "session.started":
                self.journal.log("prêt", f"session {m.get('session', {}).get('id', '?')}")
            elif t == "session.delegation.created":
                self.journal.log("coulisses", "GPT-Live confie une question au penseur")
            elif t == "response.event":
                ev = m.get("event", {})
                if ev.get("type") == "response.output_item.done":
                    item = ev.get("item", {})
                    if item.get("type") == "message":
                        texte = " ".join(c.get("text", "") for c in item.get("content", []) if isinstance(c, dict))
                        self.journal.log("coulisses", f"réponse : « {texte.strip()} »"[:600])
                elif ev.get("type") == "response.completed":
                    u = ev.get("response", {}).get("usage", {})
                    self.journal.log("coulisses", f"fini · {u.get('input_tokens', 0)} tokens lus, {u.get('output_tokens', 0)} écrits")
            elif t == "session.usage.updated":
                self.secondes = m.get("usage", {}).get("seconds", self.secondes)
            elif t == "error":
                self.journal.log("erreur", json.dumps(m.get("error", m), ensure_ascii=False)[:400])
            elif t == "session.closed":
                self.journal.log("fin", f"session fermée ({m.get('reason')})")
                return

    # ------------------------------------------------------------------ Twilio

    async def _envoyer_twilio(self, msg: dict) -> None:
        try:
            await self.tw.send(json.dumps(msg))
        except websockets.ConnectionClosed:
            pass

    async def _parler(self) -> None:
        """Voix du modèle → Twilio, au rythme réel (20 ms par trame, 60 ms d'avance). Coupe si l'appelant a pris la parole."""
        t0, k = None, 0
        while True:
            maintenant = time.monotonic()
            if self.sortie and self.mots_appelant >= MOTS_COUPURE and maintenant - self.dernier_son > SILENCE_MODELE_S:
                self.journal.log("coupure", f"l'appelant parle, le modèle s'est tu : {len(self.sortie) / 8000:.1f} s de voix jetées")
                self.sortie.clear()
                await self._envoyer_twilio({"event": "clear", "streamSid": self.sid})
            if not self.sortie:
                t0 = None
                await asyncio.sleep(0.01)
                continue
            if t0 is None:
                t0, k = maintenant, 0
            trame = bytes(self.sortie[:TRAME])
            del self.sortie[:TRAME]
            await self._envoyer_twilio({"event": "media", "streamSid": self.sid, "media": {"payload": base64.b64encode(trame).decode()}})
            k += 1
            attente = t0 + (k - AVANCE) * 0.02 - time.monotonic()
            if attente > 0:
                await asyncio.sleep(attente)

    async def gerer(self) -> None:
        taches: list[asyncio.Task] = []
        try:
            async for brut in self.tw:
                m = json.loads(brut)
                ev = m.get("event")
                if ev == "start":
                    self.sid = m["start"]["streamSid"]
                    print(f"📞 Appel reçu ({m['start'].get('customParameters', {}).get('de', 'numéro masqué')})")
                    self.telephone = m["start"].get("customParameters", {}).get("de", "")
                    await self._ouvrir()
                    taches = [asyncio.create_task(self._ecouter_openai()), asyncio.create_task(self._parler())]
                    taches[0].add_done_callback(lambda _: asyncio.ensure_future(self.tw.close()))
                elif ev == "media" and self.oa is not None:
                    self.micro.append(base64.b64decode(m["media"]["payload"]))
                    try:  # même format des deux côtés : le son passe tel quel
                        await self.oa.send(json.dumps({"type": "session.input_audio.append", "audio": m["media"]["payload"]}))
                    except websockets.ConnectionClosed:
                        break
                elif ev == "stop":
                    break
        except websockets.ConnectionClosed:
            pass
        finally:
            if self.oa is not None:
                try:
                    await self.oa.send(json.dumps({"type": "session.close"}))
                    await asyncio.wait_for(taches[0], 3)
                except Exception:
                    pass
                await self.oa.close()
            for t in taches:
                t.cancel()
            await self._terminer()
            print("📴 Appel terminé")

    # ------------------------------------------------------------------ fin d'appel

    async def _terminer(self) -> None:
        self._ajouter("fin", "")  # écrit la dernière réplique dans le journal
        self.lignes = [l for l in self.lignes if l["role"] != "fin" and l["content"].strip()]
        duree = self.secondes or (time.monotonic() - self.t0)
        self.journal.log("coût", f"GPT-Live {duree:.0f} s ≈ {duree / 60 * 0.05:.3f} $ (+ coulisses et fiche)")
        if any(l["role"] == "user" for l in self.lignes):
            try:
                fiche = await self._fiche()
                (self.journal.dossier / "fiche.json").write_text(json.dumps(fiche, ensure_ascii=False, indent=2))
                self.journal.log("FICHE", json.dumps(fiche, ensure_ascii=False))
            except Exception as e:
                self.journal.log("FICHE", f"non rédigée : {e!r}"[:300])
        # Copie de test du SI SIAO (si SISIAO_URL est défini) : le pré-dossier entre aussitôt dans la file MIKI.
        await sisiao.transmettre(self.lignes, self.telephone, self.journal.debut, self.journal)
        for nom, blocs in (("micro.wav", self.micro), ("ia.wav", self.ia)):
            if blocs:
                x = (np.clip(ulaw_vers_float(b"".join(blocs)), -1, 1) * 32767).astype(np.int16)
                with wave.open(str(self.journal.dossier / nom), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(8000)
                    w.writeframes(x.tobytes())
        self.journal.terminer([], None)

    async def _fiche(self) -> dict:
        texte = "\n".join(f"{'IA' if l['role'] == 'assistant' else 'Appelant'} : {l['content'].strip()}" for l in self.lignes)
        corps = {"model": env("LIVE_PENSEUR", "gpt-5.5"), "reasoning_effort": "low", "response_format": {"type": "json_object"},
                 "messages": [{"role": "system", "content": CONSIGNES_FICHE}, {"role": "user", "content": texte}]}
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {env('OPENAI_API_KEY')}"}, json=corps)
            r.raise_for_status()
            fiche = json.loads(r.json()["choices"][0]["message"]["content"])
        fiche["_modele"] = corps["model"]
        return fiche


async def gerer(ws) -> None:
    await AppelLive(ws).gerer()


def main() -> None:
    charger_env()
    if not env("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY manquante dans .env")
    try:
        asyncio.run(servir(None, numero_a_appeler(), gerer))
    except KeyboardInterrupt:
        print("\nServeur arrêté. (Pour rendre le numéro à l'ancien callbot : .venv/bin/python -m appel.twilio --remettre)")


if __name__ == "__main__":
    main()
