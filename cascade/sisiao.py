"""
Branchement sur le SI SIAO (copie de test) : à la fin de l'appel, la conversation est analysée et le
pré-dossier est envoyé au SI SIAO, qui le place aussitôt dans la file d'attente MIKI des écoutants.

Rien ne change si SISIAO_URL n'est pas défini dans .env (le dossier sessions/ reste la seule sortie).
  SISIAO_URL=http://127.0.0.1:8000     # le SI SIAO qui tourne sur le même poste
  MIKI_JETON=…                          # facultatif : même valeur côté SI SIAO s'il est sur une autre machine

L'analyse est faite par le même modèle que la fiche (cascade/fiche.py, FICHE=groq ou openai), avec des
consignes propres au SI SIAO : ménage complet (accompagnants, enfants), grossesse, handicap, urgence,
langue. Résultat et réponse du SI SIAO : sessions/<appel>/sisiao.json.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

import httpx

from commun.config import env

from . import fiche as fiche_dossier

CONSIGNES = """Tu prépares le pré-dossier d'un appel au 115 (urgence sociale) pour le SI SIAO, à partir de sa transcription : « IA » est l'assistant vocal, « Appelant » est la personne.
La transcription automatique du téléphone fait des erreurs : fie-toi d'abord à ce que l'appelant a confirmé, en particulier l'orthographe épelée des noms.
Réponds uniquement par un objet JSON valide, avec exactement ces clés :
- "source" : "Usager" si la personne appelle pour elle-même, "Tiers" si quelqu'un appelle pour elle, "Maraude" si c'est une équipe de maraude ;
- "personnes" : liste de toutes les personnes du ménage qui ont besoin d'un hébergement, la personne concernée en premier (pas le tiers qui appelle), puis chaque personne qui l'accompagne (conjoint, enfant…). Pour chacune : "nom" et "prenom" (écrits normalement, null si inconnus), "sexe" ("Homme", "Femme" ou null), "date_naissance" (AAAA-MM-JJ si la date complète est dite, sinon null), "annee_naissance" (AAAA si seule l'année est dite, sinon null), "age" (entier si seul l'âge est dit, sinon null), "enceinte" (true seulement si dit), "date_terme" (AAAA-MM-JJ, déduite du mois de grossesse si dit, sinon null), "pmr" (true seulement si un fauteuil roulant ou une mobilité réduite est dit), "handicap" (texte court ou null). Un enfant dont on ne connaît que l'âge est une personne avec seulement son âge ;
- "ville" : la ville où elle se trouve ce soir, ou null ; "code_postal" : seulement s'il a été dit, sinon null ; "adresse" : le quartier, la rue ou le repère s'ils ont été dits, sinon null ;
- "telephone_rappel" : un autre numéro donné pour la rappeler, sinon null ; "rappel_impossible" : true si elle a dit qu'on ne peut pas la rappeler à ce numéro ;
- "animaux" : {"Chien": n, "Chat": n, "Autres": n} pour les animaux qui l'accompagnent, {} sinon ;
- "urgence_vitale" : true seulement si l'appelant a décrit un danger vital immédiat ; "urgence_detail" : ce danger en une phrase, ou null ;
- "autre_vulnerabilite" : un problème de santé, une sortie d'hôpital ou une autre fragilité sérieuse dite par l'appelant, en une phrase, ou null. N'y mets jamais la grossesse, le handicap, l'âge des enfants ni la mobilité : ils sont déjà dans "personnes" ;
- "langue" : la langue parlée par l'appelant, en français (« Français », « Anglais »…) ; "niveau_francais" : "Courant", "Quelques mots" ou "Aucun" ; "interprete" : true si un interprète sera nécessaire ;
- "animal" : "Oui" si l'appelant a un animal avec lui, "Non" s'il a dit ne pas en avoir, sinon null ;
- "resume" : trois phrases au plus, factuelles, pour l'écoutant qui rappellera : situation, depuis quand à la rue (première nuit dehors ?), détresse exprimée, et qui appelle si c'est un tiers ;
- "a_verifier" : parmi "nom", "prenom", "date_naissance", "telephone", "adresse", ceux dont la réponse est incertaine (orthographe non confirmée, âge approximatif, rappel impossible à ce numéro, lieu imprécis), ou [].
N'invente rien et n'interprète rien : null pour toute information inconnue ou refusée."""


def _personnes(liste) -> list[dict]:
    annee = datetime.now().year
    out = []
    for p in liste or []:
        if not isinstance(p, dict):
            continue
        q = {k: p.get(k) for k in ("nom", "prenom", "sexe", "enceinte", "date_terme", "pmr", "handicap")
             if p.get(k) not in (None, "", False)}
        if isinstance(p.get("date_naissance"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p["date_naissance"]):
            q["date_naissance"] = p["date_naissance"]
        elif str(p.get("annee_naissance") or "").isdigit() and 1900 < int(p["annee_naissance"]) <= annee:
            q["annee_naissance"] = str(int(p["annee_naissance"]))
        elif isinstance(p.get("age"), (int, float)) and 0 <= p["age"] < 120:
            q["annee_naissance"] = str(annee - int(p["age"]))
        out.append(q)
    return out


async def transmettre(historique: list[dict], telephone: str, debut: datetime, journal) -> None:
    """Analyse l'appel et l'envoie au SI SIAO. Ne lève jamais : tout est noté dans le journal."""
    url = env("SISIAO_URL").rstrip("/")
    if not url or not any(m["role"] == "user" for m in historique):
        return
    trace = {"envoye": None, "reponse": None}
    try:
        analyse = await fiche_dossier.rediger(historique, CONSIGNES)
        a_verifier = list(analyse.get("a_verifier") or [])
        if analyse.get("rappel_impossible") and "telephone" not in a_verifier:
            a_verifier.append("telephone")
        donnees = {
            "telephone": analyse.get("telephone_rappel") or telephone or "",
            "source": analyse.get("source") or "Usager",
            "duree_secondes": round((datetime.now() - debut).total_seconds()),
            "personnes": _personnes(analyse.get("personnes")),
            "transcription": fiche_dossier.transcription(historique),
            "a_verifier": a_verifier,
            **{k: analyse.get(k) for k in ("urgence_vitale", "urgence_detail", "autre_vulnerabilite", "langue",
                                          "niveau_francais", "interprete", "animal", "animaux", "resume",
                                          "ville", "code_postal", "adresse")},
        }
        trace["envoye"] = {k: v for k, v in donnees.items() if k != "transcription"}
        entetes = {"X-Miki-Jeton": env("MIKI_JETON")} if env("MIKI_JETON") else {}
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{url}/api/miki/appels", json=donnees, headers=entetes)
        trace["reponse"] = {"statut": r.status_code, "corps": r.json() if "json" in r.headers.get("content-type", "") else r.text[:300]}
        if r.status_code == 200:
            j = r.json()
            journal.log("SI SIAO", f"pré-dossier {j['numero']} dans la file ({j['profil']}, {j['places']} place(s) compatibles)")
            print(f"📋 SI SIAO : pré-dossier {j['numero']} ajouté à la file d'attente MIKI")
        else:
            journal.log("SI SIAO", f"refusé ({r.status_code}) : {str(trace['reponse']['corps'])[:200]}")
            print(f"⚠️  SI SIAO : envoi refusé ({r.status_code})")
    except Exception as e:
        trace["erreur"] = repr(e)[:300]
        journal.log("SI SIAO", f"non transmis : {e!r}"[:300])
        print(f"⚠️  SI SIAO : non transmis ({e.__class__.__name__})")
    (journal.dossier / "sisiao.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2))
