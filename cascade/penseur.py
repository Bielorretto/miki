"""
Cerveau du programme 2 : n'importe quel modèle avec une API compatible OpenAI (OpenAI, Groq, Mistral…).
La réponse arrive mot à mot et est découpée en phrases : la voix commence dès la première phrase.

Changer de penseur :  --penseur mistral   (clé MISTRAL_API_KEY dans .env ; modèle : PENSEUR_MODELE=…)
"""

from __future__ import annotations

import json
import re
from typing import AsyncIterator

import asyncio

import httpx

from commun.config import env, modele_juge, modele_penseur

# Fin de phrase : ponctuation suivie d'un espace, ou collée à la phrase suivante (« ?Quel », « ?[En attente…] », fréquent avec Groq).
FIN_PHRASE = re.compile(r"[.!?…:;]+(?:\s+|(?=[A-ZÀÂÇÉÈÊÎÔÛ\[(]))")  # « ?... » compte comme une seule fin
VIRGULE = re.compile(r",\s+")
QUESTION = re.compile(r"[?!]+(?:\s+|(?=[A-ZÀÂÇÉÈÊÎÔÛ\[(]))")  # « ? » et « ! » : jamais une abréviation, pas de longueur minimale


# « - Sexe : homme » : ElevenLabs lit mal les libellés de liste (« Sexe ? homicide »). Le « : » devient une virgule,
# avant le découpage en phrases (qui coupe aussi aux « : »).
LIBELLE = re.compile(r"(^|\n)[ \t]*(?:[-*•]|\d+[.)])[ \t]*\**([^\n:*]{1,30}?)\**[ \t]*:[ \t]*")

# Fiche en cours, tenue à jour en parallèle par un petit modèle : le penseur sait ce qui est déjà recueilli
# (il ne redemande pas une durée déjà donnée, n'insiste pas après un refus).
SUIVI = """Tu lis la transcription d'un appel au 115 entre l'assistant vocal (IA) et l'appelant.
Tiens à jour ce que l'appelant a DÉJÀ dit. Réponds en JSON avec les clés : prenom, nom, age, sexe, situation, duree_a_la_rue, sante, refus.
- Valeurs courtes en français, telles que l'appelant les a dites (orthographe épelée et confirmée pour prenom et nom, avec « confirmé » ou « à confirmer »).
- situation : seul ou accompagné, enfants, grossesse, besoin urgent. sante : santé, handicap, douleur.
- refus : liste des informations que l'appelant ne veut pas ou ne peut pas donner.
- null si l'information n'a pas encore été donnée. N'invente rien, n'interprète rien."""


def _fin(tampon: str) -> re.Match | None:
    """Première fin de phrase. Au moins 12 caractères pour « . » (« M. », « 3. »), mais pas pour « ? » :
    après un découpage à la virgule, « Mohamed ? » doit déclencher le garde-fou."""
    m, q = FIN_PHRASE.search(tampon, 12), QUESTION.search(tampon)
    return q if q is not None and (m is None or q.start() < m.start()) else m


def _nettoyer(phrase: str) -> str:
    """Texte prêt pour la voix : points de suspension après une ponctuation retirés, écriture inclusive simplifiée."""
    phrase = re.sub(r"([?!.])\s*(?:\.{2,}|…)", r"\1", phrase.strip())
    # Markdown (listes, gras, titres) : lu tel quel par la voix. Une puce devient une fin de phrase.
    phrase = re.sub(r"\s*\n\s*(?:[-*•]|\d+[.)])\s+", ". ", phrase)
    phrase = re.sub(r"^(?:[-*•]|#+)\s+", "", phrase)
    phrase = re.sub(r"\*\*|__|`", "", phrase)
    # Retour à la ligne sans ponctuation (« … avec votre femme\nEst-ce correct ? ») : c'est une fin de phrase.
    phrase = re.sub(r"(?<![.!?:;,])\s*\n\s*", ". ", phrase)
    phrase = re.sub(r"\s*\n\s*", " ", phrase).strip()
    phrase = re.sub(r"([:.;!?])\s*\.(?=\s|$)", r"\1", phrase)
    # Écriture inclusive, illisible à voix haute : « un(e) écoutant(e) », « seul·e » → « un écoutant », « seul ».
    return re.sub(r"(?<=\w)(?:\((?:e|es|s|ne|le|se|ice|rice)\)|·(?:e|es|ne|le|se|rice)\b(?:·s)?)", "", phrase)


class Penseur:
    def __init__(self, fournisseur: str, consignes: str, suivi: bool = False) -> None:
        self.url, self.cle, self.modele = modele_penseur(fournisseur)
        if not self.cle:
            raise SystemExit(f"clé manquante pour le penseur « {fournisseur} » dans .env")
        self.historique: list[dict] = [{"role": "system", "content": consignes}]
        self.fiche: str | None = None  # contenu après <FICHE> : jamais envoyé à la voix
        self.fin = False  # balise <FIN> reçue
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5))
        # Secours si le penseur refuse (Groq : limite de tokens par minute → 429) : OpenAI, sans quoi l'IA se tairait.
        self.secours = modele_penseur("openai") if fournisseur != "openai" else None
        self.secours_utilise = False
        self.log = None  # journal de l'appel (facultatif)
        # Fiche en cours (rôle 115) : petit modèle rapide (celui du juge), en tâche de fond après chaque réponse.
        self.suivi: dict | None = None
        self._suivi_tache: asyncio.Task | None = None
        self._suivi_modele = modele_juge(env("SUIVI", "groq")) if suivi else None
        # Programme 5 (live) : note interne de plus (réponse du penseur de fond), consigne d'une prise de parole
        # spontanée (sans nouvelle phrase de l'appelant), et rappel quand le modèle demande à réfléchir (<PENSER>).
        self.note: str | None = None
        self.consigne: str | None = None
        self.sur_penser = None  # fonction (question à étudier, dernière phrase de l'appelant)
        self.attente = "Je regarde ça, un instant."  # dite si le modèle appelle l'outil « penser » sans rien dire avant

    def _etat(self) -> str | None:
        """Ce qui est déjà recueilli, en une ligne, pour le penseur."""
        if not self.suivi:
            return None
        noms = {"prenom": "prénom", "nom": "nom", "age": "âge", "sexe": "sexe", "situation": "situation",
                "duree_a_la_rue": "depuis quand à la rue", "sante": "santé"}
        connu = [f"{n} : {self.suivi[k]}" for k, n in noms.items() if self.suivi.get(k) not in (None, "", [])]
        refus = self.suivi.get("refus") or []
        if not connu and not refus:
            return None
        texte = "Note interne (pour toi seul, ne la lis jamais). Déjà recueilli, ne pas redemander : " + ("; ".join(connu) or "rien") + "."
        if refus:
            texte += " Refusé, ne pas insister : " + ", ".join(map(str, refus)) + "."
        manque = [n for k, n in noms.items() if self.suivi.get(k) in (None, "", [])]
        if manque:
            texte += " Encore inconnu : " + ", ".join(manque) + "."
        return texte

    async def _mettre_a_jour_suivi(self) -> None:
        url, cle, modele = self._suivi_modele
        lignes = [f"{'IA' if m['role'] == 'assistant' else 'Appelant'} : {m['content']}" for m in self.historique[1:] if m["role"] != "system"]
        corps = {
            "model": modele,
            "messages": [
                {"role": "system", "content": SUIVI},
                {"role": "user", "content": "\n".join(lignes[-60:])},
            ],
            "response_format": {"type": "json_object"},
        }
        if "gpt-oss" in modele:
            corps["reasoning_effort"] = "low"
        if modele.startswith("gpt-5"):
            corps["reasoning_effort"] = "none"
        try:
            r = await self.client.post(f"{url}/chat/completions", headers={"Authorization": f"Bearer {cle}"}, json=corps, timeout=8)
            r.raise_for_status()
            v = json.loads(r.json()["choices"][0]["message"]["content"])
            if isinstance(v, dict):
                # Une information connue n'est jamais effacée par un oubli du petit modèle (null au tour suivant).
                ancien = self.suivi or {}
                self.suivi = {k: (v.get(k) if v.get(k) not in (None, "", []) else ancien.get(k)) for k in set(ancien) | set(v)}
                if self.log:
                    self.log("suivi", self._etat() or "rien encore")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # on garde la fiche précédente
            if self.log:
                self.log("suivi", f"erreur {e!r}"[:160])

    async def phrases(self, texte_utilisateur: str | None) -> AsyncIterator[str]:
        """Donne la réponse phrase par phrase."""
        messages = list(self.historique)
        if texte_utilisateur:
            messages.append({"role": "user", "content": texte_utilisateur})
        else:
            messages.append({"role": "user", "content": self.consigne or "(L'appel commence : salue l'utilisateur en une phrase courte.)"})
        if (etat := "\n\n".join(e for e in (self._etat(), self.note) if e)):
            # La note va à la fin des consignes du début : gpt-oss n'attend des consignes qu'au début de la conversation
            # (un message « system » au milieu le fait dérailler : il récite son raisonnement, « Très très très… »).
            messages[0] = {"role": "system", "content": f"{messages[0]['content']}\n\n{etat}"}
        self.secours_utilise = False
        tampon = ""
        premier = True
        cache = None  # tout ce qui suit un « < » (début de balise FICHE) n'est jamais prononcé
        muet = False  # après sa question l'IA se tait : on ne lit plus que les balises (FICHE, FIN)
        async for delta in self._flux(messages):
            if cache is not None:
                cache += delta
                continue
            if muet:
                if "<" in delta:
                    cache = delta.split("<", 1)[1]
                continue
            tampon += delta.replace("\u2011", "-").replace("\u202f", " ")
            tampon = LIBELLE.sub(lambda m: f"{m.group(1)}- {m.group(2).strip()}, ", tampon)
            if "<" in tampon:
                tampon, cache = tampon.split("<", 1)
            # Une phrase est prête dès qu'une ponctuation finale est suivie d'un espace
            # (au moins 12 caractères, pour ne pas envoyer « M. » ou « 3. » seuls).
            while (m := _fin(tampon)) is not None:
                # 1er morceau : on coupe aussi à la virgule (≥ 3 mots) pour que la voix démarre plus tôt.
                if premier and (v := VIRGULE.search(tampon, 12)) is not None and v.start() < m.start() and len(tampon[: v.start()].split()) >= 3:
                    m = v
                premier = False
                phrase = _nettoyer(tampon[: m.end()])
                if phrase:
                    yield phrase
                tampon = tampon[m.end():]
                if "?" in phrase[-4:]:  # « ? », « ?... », « ?… »
                    # Garde-fou : après sa question, l'IA attend. Certains modèles (gpt-oss sur Groq) enchaînent
                    # en inventant la réponse de l'utilisateur (« Je suis un homme. ») : on ne prononce pas la suite
                    # (mais une balise FICHE / FIN qui suit est gardée).
                    muet = True
                    if "<" in tampon:
                        cache = tampon.split("<", 1)[1]
                    tampon = ""
                    break
            if not muet and premier and (v := VIRGULE.search(tampon, 12)) is not None and len(tampon[: v.start()].split()) >= 3:
                premier = False
                yield tampon[: v.end()].strip()
                tampon = tampon[v.end():]
        if _nettoyer(tampon):
            yield _nettoyer(tampon)
        if cache is not None:
            if re.search(r"FIN\s*/?>", cache):
                self.fin = True  # l'IA a dit au revoir (consigne : balise <FIN>) : l'appel se termine après sa voix
            if self.sur_penser and (m := re.search(r"PENSER\s*>(.*?)(?:<|$)", cache, re.S)) and m.group(1).strip():
                self.sur_penser(m.group(1).strip(), texte_utilisateur)
            if (m := re.search(r"FICHE\s*>(.*)", cache, re.S)) is not None:  # FICHE avant ou après FIN
                self.fiche = re.sub(r"<?FIN\s*/?>", "", m.group(1))

    def _corps(self, modele: str, messages: list[dict]) -> dict:
        corps = {"model": modele, "messages": messages, "stream": True}
        if "gpt-oss" in modele:
            # « medium » : un peu plus de réflexion (+0,1 s), nettement meilleur pour suivre la conversation (banc d'essai du 2026-11-09).
            corps["reasoning_effort"] = env("PENSEUR_REFLEXION", "medium")
        if modele.startswith("gpt-5"):
            corps["reasoning_effort"] = "none"
        return corps

    async def _flux(self, messages: list[dict]) -> AsyncIterator[str]:
        """Texte de la réponse, morceau par morceau. Si le penseur refuse avant le 1er mot (429, panne), le secours répond."""
        essais = [(self.url, self.cle, self.modele)]
        if self.secours and self.secours[1]:
            essais.append(self.secours)
        parti = False  # déjà des mots envoyés : plus de secours possible (la réponse serait dite deux fois)
        for i, (url, cle, modele) in enumerate(essais):
            dernier = i == len(essais) - 1
            try:
                async with self.client.stream("POST", f"{url}/chat/completions", headers={"Authorization": f"Bearer {cle}"}, json=self._corps(modele, messages)) as r:
                    if r.status_code >= 400:
                        erreur = RuntimeError(f"penseur {r.status_code} : {(await r.aread())[:200]!r}")
                        if dernier:
                            raise erreur
                        continue
                    self.secours_utilise = i > 0
                    outil = ""  # programme 5 : arguments de l'outil « penser » (le modèle confie une question au penseur de fond)
                    async for ligne in r.aiter_lines():
                        if not ligne.startswith("data:"):
                            continue
                        d = ligne[5:].strip()
                        if d == "[DONE]":
                            break
                        try:
                            ch = json.loads(d)["choices"][0]["delta"]
                        except (KeyError, IndexError, json.JSONDecodeError):
                            continue
                        for tc in ch.get("tool_calls") or []:
                            outil += (tc.get("function") or {}).get("arguments") or ""
                        delta = ch.get("content") or ""
                        if delta:
                            parti = True
                            yield delta
                    if outil:
                        try:
                            question = str(json.loads(outil).get("question") or "").strip()
                        except (json.JSONDecodeError, AttributeError):
                            question = outil.strip()
                        if question:
                            if not parti:
                                yield self.attente + " "
                            yield f"<PENSER>{question}</PENSER>"
                    return
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError):
                if dernier or parti:
                    raise

    def retenir(self, utilisateur: str | None, ia: str) -> None:
        """Ajoute l'échange à l'historique (ce que l'utilisateur a vraiment entendu en cas de coupure)."""
        if utilisateur:
            self.historique.append({"role": "user", "content": utilisateur})
        if ia:
            self.historique.append({"role": "assistant", "content": ia})
        # Tout l'appel est gardé (prénom, nom… restent connus pour le résumé) ; seule sécurité : un appel qui
        # tournerait en boucle au-delà de 300 messages.
        if len(self.historique) > 301:
            self.historique = self.historique[:1] + self.historique[-300:]
        if self._suivi_modele and utilisateur:
            if self._suivi_tache and not self._suivi_tache.done():
                self._suivi_tache.cancel()
            self._suivi_tache = asyncio.create_task(self._mettre_a_jour_suivi())
