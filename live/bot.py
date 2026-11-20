"""
Programme 5 : « live », sur le modèle de GPT-Live (OpenAI, 2026) : deux cerveaux.

  parleur  Groq gpt-oss-20b : répond tout de suite (c'est sa latence qu'on entend), mène le dossier 115.
  penseur  OpenAI gpt-5.5 (réflexion medium), en coulisses : appelé seulement quand le parleur utilise l'outil
           « penser » (function calling) ; s'il n'a rien dit avant, « Je regarde ça, un instant. » est dit aussitôt.
           La conversation continue pendant qu'il réfléchit ; sa réponse revient au parleur, qui la dit avec ses mots :
           tout de suite si l'appelant se tait, sinon dans sa réponse suivante.

Le reste est celui du programme 4 : Deepgram, ElevenLabs, Silero, Smart Turn, juge, barge-in vérifié (le son baisse,
l'IA ne s'arrête que si de vrais mots confirment l'interruption), fiche rédigée à la fin.

Lancer :  bash lancer.sh 5   (ou : python -m live.serveur [--appeler 06…])
Réglages (.env, facultatifs) : PARLEUR_MODELE, PARLEUR_REFLEXION (low|medium), PENSEUR_FOND_MODELE,
  PENSEUR_FOND_REFLEXION (low|medium|high), PENSEUR_FOND_MAX (appels au plus par appel téléphonique, défaut 6).
"""

from __future__ import annotations

import asyncio
import time

import httpx

from cascade.bot import BotCascade
from cascade.penseur import Penseur
from commun.config import Config, env

# Phrase dite si le penseur n'a pas fini au bout de quelques secondes (enregistrée une fois, dite sans attendre).
ENCORE = "Je cherche encore, un petit instant."
ENCORE_S = 8.0

DELEGUER = """

QUAND IL FAUT RÉFLÉCHIR
Tu as l'outil « penser » : un collègue plus savant y réfléchit en coulisses. Utilise-le dès qu'une question demande de réfléchir ou de savoir quelque chose dont tu n'es pas sûr, au lieu de deviner. Pour le dossier et les questions simples, réponds toi-même."""

OUTIL = {
    "type": "function",
    "function": {
        "name": "penser",
        "description": ("Confie une question à un collègue expert qui réfléchit en coulisses pendant que la conversation continue. "
                        "À utiliser pour toute question sur les droits, la police, les papiers, les démarches, la santé, l'hébergement, "
                        "ou toute situation compliquée : ne jamais deviner la réponse. Sa réponse te sera donnée ensuite."),
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "La question en français, posée de façon neutre (sans supposer la réponse), avec ce qu'il faut savoir de la situation de l'appelant."}},
            "required": ["question"],
        },
    },
}

FOND = """Tu es le penseur d'un assistant vocal téléphonique du 115 (urgence sociale, France). Tu ne parles jamais à l'appelant : l'assistant qui lui parle t'a confié une question pendant l'appel et transmettra ta réponse avec ses mots.
Réfléchis bien, puis réponds en français, en une à trois phrases courtes et simples, faciles à dire au téléphone à une personne fatiguée : pas de liste, pas d'abréviation, pas de lien.
N'invente jamais une adresse, un horaire, un numéro ou une règle : si tu n'es pas sûr, dis ce qui est sûr et ce qu'un écoutant du 115 pourra vérifier. En cas de danger pour la santé ou la vie, dis-le clairement (15, 112). Ne pose aucune question : c'est l'assistant qui mène l'entretien.

Voici les consignes de l'assistant, pour le contexte :
"""


class Parleur(Penseur):
    """Le penseur du programme 4, réglé pour répondre vite (gpt-oss-20b sur Groq)."""

    def _corps(self, modele: str, messages: list[dict]) -> dict:
        corps = super()._corps(modele, messages)
        if "gpt-oss" in modele:
            corps["reasoning_effort"] = env("PARLEUR_REFLEXION", "low")
        if self.sur_penser and not self.consigne:  # pas d'outil quand il transmet déjà une réponse du penseur
            corps["tools"] = [OUTIL]
        return corps


class PenseurFond:
    """GPT-5.5 en coulisses : une question, une réponse courte (pas de flux : personne n'attend ses mots un par un)."""

    def __init__(self, consignes: str, log) -> None:
        self.cle = env("OPENAI_API_KEY")
        self.modele = env("PENSEUR_FOND_MODELE", "gpt-5.5")
        self.reflexion = env("PENSEUR_FOND_REFLEXION", "medium")
        self.consignes = FOND + consignes
        self.log = log
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(45, connect=5))

    async def etudier(self, historique: list[dict], derniere: str | None, question: str) -> str:
        lignes = [f"{'Assistant' if m['role'] == 'assistant' else 'Appelant'} : {m['content']}" for m in historique if m["role"] != "system"]
        if derniere:
            lignes.append(f"Appelant : {derniere}")
        corps = {
            "model": self.modele,
            "messages": [
                {"role": "system", "content": self.consignes},
                {"role": "user", "content": "Transcription de l'appel :\n" + "\n".join(lignes[-80:]) + f"\n\nQuestion à étudier : {question}"},
            ],
            "reasoning_effort": self.reflexion,
            "max_completion_tokens": 4000,
        }
        t = time.perf_counter()
        r = await self.client.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {self.cle}"}, json=corps)
        r.raise_for_status()
        d = r.json()
        u = d.get("usage", {})
        reflexion = (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        self.log("penseur fond", f"{self.modele} ({self.reflexion}) en {time.perf_counter() - t:.1f} s · "
                                 f"{u.get('prompt_tokens', 0)} tokens lus, {u.get('completion_tokens', 0)} écrits dont {reflexion} de réflexion")
        return (d["choices"][0]["message"].get("content") or "").strip()


class BotLive(BotCascade):
    nom = "live"

    def __init__(self, cfg: Config) -> None:
        base = cfg.consignes
        cfg.consignes = base + DELEGUER
        super().__init__(cfg)
        historique = self.penseur.historique
        self.penseur = Parleur(cfg.penseur, cfg.consignes, suivi=cfg.role == "115")
        if cfg.penseur == "groq":
            self.penseur.modele = env("PARLEUR_MODELE", "openai/gpt-oss-20b")
        self.penseur.historique = historique
        self.penseur.log = self.journal.log
        self.penseur.sur_penser = self._demande_penser
        self.fond = PenseurFond(base, self.journal.log)
        self._max = int(env("PENSEUR_FOND_MAX", "6"))
        self._nb = 0
        self._tache_fond: asyncio.Task | None = None
        self._pense_depuis: float | None = None  # le penseur réfléchit depuis…
        self._encore_dit = False
        self._resultat: tuple[str, str] | None = None  # (question, réponse) pas encore transmise

    async def connecter(self) -> None:
        await super().connecter()
        self.journal.log("live", f"parleur {self.penseur.modele} ({env('PARLEUR_REFLEXION', 'low')}) · penseur de fond {self.fond.modele} ({self.fond.reflexion})")
        asyncio.create_task(self.voix.preparer(ENCORE))

    # ------------------------------------------------------------------ penseur de fond

    def _demande_penser(self, question: str, derniere: str | None) -> None:
        """Le parleur a écrit <PENSER>… : on lance le penseur tout de suite (pendant que la phrase d'attente est dite)."""
        if self._nb >= self._max:
            self.journal.log("penseur fond", f"limite de {self._max} questions atteinte : « {question} » non étudiée")
            self._resultat = (question, "")
            self._pense_depuis = None
            asyncio.create_task(self._transmettre())
            return
        self._nb += 1
        if self._tache_fond and not self._tache_fond.done():
            self._tache_fond.cancel()  # une nouvelle question remplace l'ancienne
        self.journal.log("penseur fond", f"question : « {question} »")
        self._tache_fond = asyncio.create_task(self._penser(question, derniere, list(self.penseur.historique)))

    async def _penser(self, question: str, derniere: str | None, historique: list[dict]) -> None:
        self._pense_depuis, self._encore_dit = self.loop.time(), False
        try:
            reponse = await self.fond.etudier(historique, derniere, question)
            self.journal.log("penseur fond", f"réponse : « {reponse} »")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.journal.log("erreur", f"penseur de fond : {e!r}"[:300])
            reponse = ""
        self._pense_depuis = None
        self._resultat = (question, reponse)
        await self._transmettre()

    def _calme(self) -> bool:
        return (not self.ia_parle and self.ecoute.etat == "repos" and not self._verrou.locked()
                and not self._en_suspens and not self.raccrocher)

    async def _transmettre(self) -> None:
        """Dès que personne ne parle, le parleur reprend la parole avec la réponse. Si l'appelant parle d'abord,
        la réponse part dans la réponse suivante du parleur (voir repondre)."""
        while self._resultat is not None and not self._fin.is_set():
            if self._calme():
                await self._lancer_reponse("")
                return
            await asyncio.sleep(0.1)

    async def _verifier_silence(self) -> None:
        if self._pense_depuis is None:
            return await super()._verifier_silence()
        # Pendant la réflexion, le silence est normal : pas de « Pardon, je ne vous ai pas entendu ».
        self._calme_depuis = None
        if not self._encore_dit and self.loop.time() - self._pense_depuis >= ENCORE_S and self._calme():
            self._encore_dit = True
            self.phrase_fixe = ENCORE
            await self._lancer_reponse("")

    # ------------------------------------------------------------------ parole

    async def repondre(self, texte: str) -> None:
        if self._resultat is not None and not self.phrase_fixe:
            question, reponse = self._resultat
            self._resultat = None
            if reponse:
                info = f"ton collègue a étudié « {question} ». Sa réponse : « {reponse} »"
            else:
                info = f"ton collègue n'a pas pu étudier « {question} » ; dis-le simplement et propose qu'un écoutant du 115 voie ça avec la personne"
            if texte:
                self.penseur.note = f"Note interne (pour toi seul) : {info}. Transmets-le avec tes mots si c'est encore utile."
            else:
                self.penseur.consigne = (f"(Note interne : {info}. Transmets-le maintenant à l'appelant avec tes mots, en une ou deux "
                                         "phrases courtes, puis reprends le dossier là où il en était, avec une seule question.)")
        try:
            await super().repondre(texte)
        finally:
            self.penseur.note = self.penseur.consigne = None

    async def fermer(self) -> None:
        if self._tache_fond and not self._tache_fond.done():
            self._tache_fond.cancel()
        await super().fermer()


if __name__ == "__main__":
    from commun.lancement import lancer

    lancer(BotLive)
