"""
La fiche du dossier, rédigée à la fin de l'appel par un modèle à part, à partir de la transcription.
Le modèle qui parle n'en sait rien : il ne peut donc ni la réciter (« je note aussi la langue ») ni s'en distraire.

Modèle : FICHE=groq (gpt-oss-120b, défaut) ou openai dans .env ; l'autre sert de secours.
"""

from __future__ import annotations

import json

import httpx

from commun.config import env, modele_penseur

CONSIGNES = """Tu rédiges le dossier d'un appel au 115 (urgence sociale) à partir de sa transcription : « IA » est l'assistant vocal, « Appelant » est la personne.
La transcription automatique du téléphone fait des erreurs (mots ou lettres déformés) : fie-toi d'abord à ce que l'appelant a confirmé.
Réponds uniquement par un objet JSON valide, avec exactement ces clés :
- "appelant" : "usager" si la personne appelle pour elle-même, sinon "tiers" ; "tiers_qui" : qui appelle pour elle (proche, passant, association), ou null ;
- "prenom", "nom" : l'orthographe épelée et confirmée par l'appelant, écrite normalement (« Diouf »), sinon telle qu'entendue, sinon null ;
- "date_naissance" : telle que dite (« 12/03/1990 », « 1990 »), ou null ; "age" : nombre entier (dit, ou déduit de la date), ou null ;
- "sexe" : comme l'appelant l'a dit, ou null ;
- "menage" : qui a besoin d'un hébergement avec elle ce soir (seule, conjoint, autres adultes, chaque enfant avec son âge), ou null ;
- "situation" : résumé court et factuel en français de ce que l'appelant a dit (santé, grossesse et terme, handicap ou mobilité, besoin urgent, détresse exprimée), ou null ;
- "animal" : l'animal qui l'accompagne (« un chien »), "aucun" si elle l'a dit, sinon null ;
- "ville" : où elle se trouve ce soir (ville, et quartier ou repère s'ils ont été dits), ou null ;
- "rappel" : true si l'écoutant peut la rappeler à ce numéro, false sinon, null si non dit ; "autre_numero" : un autre numéro donné pour la rappeler, ou null ;
- "duree_a_la_rue" : telle que l'appelant l'a décrite, ou null ; "premiere_nuit" : true si c'est sa première nuit dehors, sinon null ;
- "langue" : la langue parlée par l'appelant ;
- "urgence_signalee" : true seulement si l'appelant a décrit un danger vital immédiat ;
- "consentement" : true si l'appelant a accepté de répondre aux questions ;
- "a_verifier" : liste courte des points incertains pour l'écoutant (orthographe non confirmée, réponse peu claire), ou [].
N'invente rien et n'interprète rien : null pour toute information inconnue ou refusée."""


def transcription(historique: list[dict]) -> str:
    return "\n".join(f"{'IA' if m['role'] == 'assistant' else 'Appelant'} : {m['content']}"
                     for m in historique if m["role"] in ("user", "assistant") and m["content"])


async def rediger(historique: list[dict], consignes: str = CONSIGNES) -> dict:
    """Fiche JSON de l'appel. Lève une exception si aucun modèle n'a répondu correctement."""
    texte = transcription(historique)
    choix = env("FICHE", "groq")
    erreurs = []
    async with httpx.AsyncClient(timeout=60) as client:
        for fournisseur in (choix, "openai" if choix != "openai" else "groq"):
            url, cle, modele = modele_penseur(fournisseur)
            if fournisseur == "openai":
                modele = env("FICHE_MODELE_OPENAI", modele)
            if not cle:
                continue
            corps = {"model": modele, "response_format": {"type": "json_object"},
                     "messages": [{"role": "system", "content": consignes}, {"role": "user", "content": texte}]}
            if "gpt-oss" in modele:
                corps["reasoning_effort"] = "medium"
            try:
                r = await client.post(f"{url}/chat/completions", headers={"Authorization": f"Bearer {cle}"}, json=corps)
                r.raise_for_status()
                fiche = json.loads(r.json()["choices"][0]["message"]["content"])
                if isinstance(fiche, dict):
                    fiche["_modele"] = modele
                    return fiche
            except Exception as e:  # on essaie le secours
                erreurs.append(f"{modele} : {e!r}"[:200])
    raise RuntimeError(" ; ".join(erreurs) or "aucune clé")
