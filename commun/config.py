"""Réglages : clés dans .env (jamais dans le code), choix des fournisseurs, seuils de détection."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def charger_env(fichier: Path = RACINE / ".env") -> None:
    """Lit un fichier .env simple (CLE=valeur) sans écraser les variables déjà définies."""
    if not fichier.exists():
        return
    for ligne in fichier.read_text().splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, val = ligne.split("=", 1)
        os.environ.setdefault(cle.strip(), val.strip().strip('"').strip("'"))


def env(cle: str, defaut: str = "") -> str:
    return os.environ.get(cle, defaut)


@dataclass
class Detection:
    """Seuils de la détection de la voix (voir commun/ecoute.py)."""

    # Probabilité Silero au-dessus de laquelle une trame est de la parole.
    seuil_parole: float = 0.5
    # En dessous : plus de parole (hystérésis).
    seuil_silence: float = 0.35
    # Le volume doit dépasser le fond de X dB (voix proche du micro).
    ecart_fond_db: float = 6.0
    # Une fois la voix connue, on accepte jusqu'à X dB plus faible qu'elle.
    marge_voix_db: float = 16.0
    # Écart supplémentaire pendant que l'IA parle (écho résiduel).
    ecart_ia_db: float = 3.0
    # Niveau absolu minimal d'une voix (dBFS).
    min_db: float = -58.0
    # Parole continue nécessaire pour démarrer (ms).
    debut_ms: int = 96
    # Temps sans parole avant de considérer qu'un morceau est fini (ms).
    fin_ms: int = 320
    # Si Smart Turn dit « pas fini » : attente maximale de la suite (ms).
    attente_max_ms: int = 1500
    attente_texte_fini_ms: int = 600  # téléphone : Smart Turn dit « pas fini » mais le texte transcrit est une phrase finie
    # Mot seul très court (« oui », « homme ») : Smart Turn se trompe souvent, on attend moins (ms).
    mot_court_ms: int = 450
    attente_mot_court_ms: int = 500
    # L'IA a demandé d'épeler : pause entre deux lettres tolérée avant de finir le tour (ms).
    attente_epellation_ms: int = 1800
    # Épellation : probabilité Silero suffisante pour une lettre (une voyelle seule a souvent 0,2-0,4).
    seuil_parole_epellation: float = 0.15
    # Probabilité Smart Turn « phrase finie ».
    seuil_tour: float = 0.5
    # Marge gardée avant / après la voix (ms) ; le reste (bruit) est coupé.
    marge_avant_ms: int = 200
    marge_apres_ms: int = 150
    # Pause gardée au maximum entre deux morceaux d'une même phrase (ms).
    pause_max_ms: int = 250
    # Empreinte vocale : en dessous de cette ressemblance, le juge doit confirmer que c'est l'utilisateur.
    voix_min: float = 0.25
    # Phrase plus faible que la voix habituelle de plus de X dB : le juge doit confirmer.
    ecart_volume_db: float = 10.0
    # Barge-in : parole continue avant de baisser le son de l'IA (ms).
    barge_ms: int = 250
    # Volume de l'IA pendant la vérification du barge-in.
    volume_baisse: float = 0.25
    # Délai max pour confirmer un barge-in avec de vrais mots (ms).
    barge_confirm_ms: int = 2500


@dataclass
class Config:
    audio: str = "auto"  # mac | pulse | fichier:<chemin.wav>
    langue: str = "fr"  # fr | en | multi (auto : moins fiable dans le bruit)
    detection: Detection = field(default_factory=Detection)
    role: str = "115"  # 115 | libre (voir commun/roles.py)
    consignes: str = ""
    accueil: str | None = None  # première phrase fixe de l'IA (sinon elle salue librement)
    # Programme 2 : penseur (API compatible OpenAI : openai, groq, mistral).
    penseur: str = "groq"
    # Juge « est-ce bien l'utilisateur ? » (rapide) : groq par défaut.
    juge: str = "groq"
    enregistrer: bool = True
    envoyer: bool = False  # envoi du journal au serveur d'analyse (UPLOAD_URL + APP_SECRET)


PENSEURS = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4.1-mini"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "mistral-small-latest"),
}

JUGES = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-5.4-nano"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-20b"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "ministral-3b-latest"),
}


def modele_penseur(nom: str) -> tuple[str, str, str]:
    url, cle, modele = PENSEURS[nom]
    return url, env(cle), env("PENSEUR_MODELE", modele)


def modele_juge(nom: str) -> tuple[str, str, str]:
    url, cle, modele = JUGES[nom]
    return url, env(cle), env("JUGE_MODELE", modele)
