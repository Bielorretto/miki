"""
Renvoie au SI SIAO un appel déjà terminé, à partir de sa session enregistrée (sessions/<appel>/session.json).
Utile quand l'envoi de fin d'appel a échoué, ou pour recréer un pré-dossier supprimé.

  python3 renvoyer.py                    # liste les derniers appels, avec le début de la conversation
  python3 renvoyer.py 3                  # renvoie le 3e de la liste
  python3 renvoyer.py 3 --tel 0612345678 # en précisant le numéro de rappel (sinon celui dit pendant l'appel)

Même analyse et même envoi qu'en fin d'appel (cascade/sisiao.py) : SISIAO_URL et MIKI_JETON viennent de .env.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from commun.config import charger_env

charger_env()

from cascade import sisiao  # noqa: E402  (après .env)

RACINE = Path(__file__).resolve().parent


class Trace:
    """Remplace le journal de l'appel : affiche, et écrit sisiao.json dans le dossier de la session."""

    def __init__(self, dossier: Path) -> None:
        self.dossier = dossier

    def log(self, ev: str, info: str = "") -> None:
        print(f"{ev} : {info}")


def historique(session: dict) -> list[dict]:
    return [{"role": "assistant" if l.get("role") == "assistant" else "user", "content": l.get("text", "")}
            for l in session.get("lines", []) if not l.get("ignored") and l.get("text")]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("numero", nargs="?", type=int, help="numéro de l'appel dans la liste")
    p.add_argument("--tel", default="", help="numéro de rappel de l'appelant")
    a = p.parse_args()
    sessions = sorted((d for d in (RACINE / "sessions").glob("*") if (d / "session.json").exists()), reverse=True)[:15]
    if not sessions:
        raise SystemExit("Aucun appel enregistré dans sessions/.")
    if a.numero is None:
        for i, d in enumerate(sessions, 1):
            s = json.loads((d / "session.json").read_text())
            dits = [m["content"] for m in historique(s) if m["role"] == "user"]
            envoye = "  [déjà envoyé]" if (d / "sisiao.json").exists() and '"statut": 200' in (d / "sisiao.json").read_text() else ""
            print(f"{i:2d}. {d.name}  ({s.get('seconds', '?')} s){envoye}\n    « {' / '.join(dits[:4])[:140]} »")
        print("\nPour renvoyer un appel : python3 renvoyer.py <numéro>")
        return
    if not 1 <= a.numero <= len(sessions):
        raise SystemExit("Numéro hors de la liste.")
    d = sessions[a.numero - 1]
    s = json.loads((d / "session.json").read_text())
    h = historique(s)
    # durée réelle de l'appel (transmettre la calcule depuis le début)
    debut = datetime.now() - timedelta(seconds=float(s.get("seconds") or 240))
    print(f"Analyse et envoi de {d.name}…")
    asyncio.run(sisiao.transmettre(h, a.tel, debut, Trace(d)))


if __name__ == "__main__":
    main()
