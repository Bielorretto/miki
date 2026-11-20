"""
Programme 2 : cascade  oreille (STT) → penseur (LLM) → voix (TTS).

  oreille  Deepgram nova-3 en continu (seul l'audio utile est envoyé, Finalize à la fin du tour)
  penseur  OpenAI / Groq / Mistral (API compatible OpenAI) — interchangeable avec --penseur
  voix     ElevenLabs v3 Conversational (voix Lucie), phrase par phrase

Même écoute, même filtre, même juge et même barge-in que le programme 1 (commun/).
Barge-in : le penseur et la voix sont coupés, et l'historique ne garde que ce que l'utilisateur a entendu.

Lancer :  python -m cascade.bot [--audio mac|pulse|fichier:chemin.wav] [--penseur openai|groq|mistral]
"""

from __future__ import annotations

import asyncio
import json
import time

import numpy as np

from commun.config import Config
from commun.conversation import PHRASES_FIXES, Conversation
from commun.lancement import lancer

from . import fiche as fiche_dossier
from . import sisiao
from .penseur import Penseur
from .stt_deepgram import Deepgram
from .tts_elevenlabs import ElevenLabs


class BotCascade(Conversation):
    nom = "cascade"
    avec_fiche = True

    def __init__(self, cfg: Config) -> None:
        super().__init__(cfg)
        self.oreille = Deepgram(cfg.langue, self.transcription_partielle, self.journal.log, par_tour=cfg.audio == "twilio")
        self.penseur = Penseur(cfg.penseur, cfg.consignes, suivi=cfg.role == "115")
        self.penseur.log = self.journal.log
        self.voix = ElevenLabs()
        self._question: str | None = None
        self._retenu = False

    async def connecter(self) -> None:
        await asyncio.gather(self.oreille.connecter(), self.voix.chauffer())
        asyncio.create_task(self._preparer_phrases())
        self.journal.log("cascade", f"oreille Deepgram {self.oreille.modele} · penseur {self.cfg.penseur} {self.penseur.modele} · voix ElevenLabs {self.voix.modele}")

    def audio_utile(self, pcm: np.ndarray) -> None:
        # Appelé depuis le fil du micro.
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.oreille.audio, pcm)

    def debut_tour(self) -> None:
        pass

    async def _preparer_phrases(self) -> None:
        for p in PHRASES_FIXES:
            try:
                await self.voix.preparer(p)
            except Exception as e:
                self.journal.log("erreur", f"phrase toute prête « {p} » : {e!r}")

    async def transcrire(self, audio: np.ndarray) -> str:
        t = time.perf_counter()
        texte = await self.oreille.finaliser(audio)
        self.journal.log("deepgram", f"texte final en {(time.perf_counter() - t) * 1000:.0f} ms")
        return texte

    async def repondre(self, texte: str) -> None:
        self._question = texte or None
        self._retenu = False
        t = time.perf_counter()

        async def phrases():
            if self.phrase_fixe:
                fixe, self.phrase_fixe = self.phrase_fixe, None
                yield fixe
                return
            if self._question is None and self.cfg.accueil:
                yield self.cfg.accueil  # phrase d'accueil fixe : pas besoin du penseur
                return
            premiere = True
            async for p in self.penseur.phrases(self._question):
                if premiere:
                    self.journal.log("penseur", f"1re phrase en {(time.perf_counter() - t) * 1000:.0f} ms")
                    premiere = False
                yield p

        async def mesurer():
            await self.voix.premier_son.wait()
            self.journal.log("voix", f"1er son en {(time.perf_counter() - t) * 1000:.0f} ms (penseur + voix)")

        m = asyncio.create_task(mesurer())
        try:
            if self.phrase_fixe and self.voix.dire_pret(self.phrase_fixe, self.audio.lecteur):
                # Phrase toujours la même (« Pardon, pouvez-vous répéter ? ») : déjà enregistrée, dite sans attendre.
                reponse, self.phrase_fixe = self.phrase_fixe, None
            else:
                reponse = await self.voix.parler(phrases(), self.audio.lecteur)
        finally:
            m.cancel()
        if self.penseur.secours_utilise:
            self.journal.log("penseur", f"secours {self.penseur.secours[2]} (le penseur principal a refusé)")
        self.penseur.retenir(self._question, reponse)
        self._question = None
        self._retenu = True
        self.ia_a_dit(reponse)
        if self.penseur.fiche:
            self._enregistrer_fiche(self.penseur.fiche)
            self.penseur.fiche = None
        if self.penseur.fin:
            self.penseur.fin = False
            if reponse.rstrip().endswith("?"):
                # <FIN> après une question (« Avez-vous d'autres besoins… ? <FIN> ») : l'IA attend une réponse, on ne raccroche pas.
                self.journal.log("fin", "balise <FIN> après une question : ignorée")
            else:
                self.raccrocher = True

    def _enregistrer_fiche(self, brut: str) -> None:
        """La fiche n'est jamais prononcée : elle est contrôlée et enregistrée dans la session."""
        import json

        texte = brut.split("</FICHE>")[0].strip()
        try:
            fiche = json.loads(texte)
            (self.journal.dossier / "fiche.json").write_text(json.dumps(fiche, ensure_ascii=False, indent=2))
            self.journal.log("FICHE", json.dumps(fiche, ensure_ascii=False))
        except json.JSONDecodeError as e:
            (self.journal.dossier / "fiche_invalide.txt").write_text(texte)
            self.journal.log("FICHE", f"JSON invalide ({e}) : {texte[:200]}")

    async def retranscrire(self, audio: np.ndarray) -> str:
        # Le flux en direct rate parfois un mot seul (« homme ») ; l'envoi du fichier entier le retrouve.
        try:
            return await self.oreille._secours(audio)
        except Exception as e:
            self.journal.log("erreur", f"2e écoute : {e!r}")
            return ""

    def texte_ia_courant(self) -> str:
        return self.voix.texte if self.repond else ""

    async def arreter_reponse(self) -> str:
        entendu = self.voix.entendu(self.audio.lecteur.joue_ms)
        self.ia_texte = self.voix.texte  # pour reconnaître son écho
        # L'IA se souviendra seulement de ce qui a été dit avant la coupure.
        resume = (entendu + " …") if entendu else "(coupé avant de parler)"
        if self._annule:
            # Réponse à du bruit : on n'en garde rien (ni la « question », ni la réponse).
            if self._retenu:
                del self.penseur.historique[-2:]
        elif self._retenu:
            # Réponse déjà écrite en entier dans l'historique, mais pas entièrement entendue : on la raccourcit.
            self.penseur.historique[-1]["content"] = resume
        else:
            self.penseur.retenir(self._question, resume)
        self._question = None
        return entendu

    async def fermer(self) -> None:
        await self.oreille.fermer()
        # La fiche est rédigée à la fin, par un modèle à part (cascade/fiche.py), même si la personne a raccroché avant.
        if any(m["role"] == "user" for m in self.penseur.historique):
            try:
                fiche = await fiche_dossier.rediger(self.penseur.historique)
                self._enregistrer_fiche(json.dumps(fiche, ensure_ascii=False))
            except Exception as e:
                self.journal.log("FICHE", f"non rédigée : {e!r}"[:300])
            # Copie de test du SI SIAO : le pré-dossier entre aussitôt dans la file d'attente MIKI.
            await sisiao.transmettre(self.penseur.historique, getattr(self, "telephone_appelant", ""),
                                     self.journal.debut, self.journal)


if __name__ == "__main__":
    lancer(BotCascade)
