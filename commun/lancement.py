"""Options de la ligne de commande, communes aux deux programmes."""

from __future__ import annotations

import argparse
import asyncio

from .config import Config, charger_env
from .roles import role
from .modeles import telecharger


def lancer(classe) -> None:
    cfg = configuration(classe)
    try:
        asyncio.run(classe(cfg).lancer())
    except KeyboardInterrupt:
        pass


def configuration(classe, audio_defaut: str = "auto") -> Config:
    """Lit les options de la ligne de commande et prépare la configuration (modèles téléchargés si besoin)."""
    charger_env()
    p = argparse.ArgumentParser(description=classe.__doc__ or classe.nom)
    p.add_argument("--audio", default=audio_defaut, help="auto | mac | pulse (téléphone) | fichier:chemin.wav (test)")
    p.add_argument("--langue", default="fr", help="fr | en | multi (détection auto, moins fiable dans le bruit)")
    p.add_argument("--juge", default="groq", choices=["groq", "openai", "mistral"])
    p.add_argument("--penseur", default="groq", choices=["openai", "groq", "mistral"], help="programme cascade seulement")
    p.add_argument("--role", default="115", choices=["115", "libre"], help="115 (accueil urgence sociale) ou libre")
    p.add_argument("--consignes", default=None, help="consignes personnalisées (remplace le rôle)")
    a = p.parse_args()
    cfg = Config(audio=a.audio, langue=a.langue, juge=a.juge, penseur=a.penseur, role=a.role)
    cfg.consignes, cfg.accueil = role(a.role, classe.avec_fiche)
    if a.consignes:
        cfg.consignes, cfg.accueil = a.consignes, None
    telecharger()
    return cfg
