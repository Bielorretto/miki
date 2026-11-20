"""
Branchement du numéro Twilio sur notre serveur d'appels (API REST Twilio, clés dans .env).

  - La 1re fois, l'ancienne configuration du numéro est sauvegardée dans appel/sauvegarde_twilio.json
    (trunk SIP « callbot-livekit » vers LiveKit). LiveKit n'est jamais modifié.
  - À chaque lancement : le numéro pointe vers l'adresse du tunnel (elle change à chaque fois).
  - Retour à l'ancien callbot :  .venv/bin/python -m appel.twilio --remettre
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from commun.config import charger_env, env

SAUVEGARDE = Path(__file__).parent / "sauvegarde_twilio.json"
API = "https://api.twilio.com/2010-04-01"
TRUNKING = "https://trunking.twilio.com/v1"


def _client() -> tuple[httpx.Client, str]:
    compte, cle, secret = env("TWILIO_ACCOUNT_SID"), env("TWILIO_API_KEY_SID"), env("TWILIO_API_KEY_SECRET")
    if not (compte and cle and secret and env("TWILIO_PHONE_NUMBER")):
        raise SystemExit("Clés Twilio manquantes dans .env (TWILIO_ACCOUNT_SID, TWILIO_API_KEY_SID, TWILIO_API_KEY_SECRET, TWILIO_PHONE_NUMBER)")
    return httpx.Client(auth=(cle, secret), timeout=20), compte


def _numero(c: httpx.Client, compte: str) -> dict:
    r = c.get(f"{API}/Accounts/{compte}/IncomingPhoneNumbers.json", params={"PhoneNumber": env("TWILIO_PHONE_NUMBER")})
    r.raise_for_status()
    numeros = r.json()["incoming_phone_numbers"]
    if not numeros:
        raise SystemExit("Numéro Twilio introuvable sur ce compte")
    return numeros[0]


def brancher(adresse_voix: str) -> str:
    """Fait pointer le numéro vers adresse_voix (TwiML). Renvoie le numéro."""
    c, compte = _client()
    n = _numero(c, compte)
    if not SAUVEGARDE.exists():
        SAUVEGARDE.write_text(json.dumps({"numero": n["phone_number"], "sid": n["sid"], "trunk_sid": n.get("trunk_sid"),
                                          "voice_url": n.get("voice_url"), "voice_method": n.get("voice_method")}, indent=2))
    if n.get("trunk_sid"):
        # Un numéro rattaché à un trunk SIP ignore son adresse « voix » : on le détache (côté Twilio seulement).
        r = c.delete(f"{TRUNKING}/Trunks/{n['trunk_sid']}/PhoneNumbers/{n['sid']}")
        if r.status_code not in (204, 404):
            r.raise_for_status()
    r = c.post(f"{API}/Accounts/{compte}/IncomingPhoneNumbers/{n['sid']}.json",
               data={"VoiceUrl": adresse_voix, "VoiceMethod": "GET"})
    r.raise_for_status()
    return n["phone_number"]


def appeler(vers: str, adresse_voix: str) -> str:
    """Le bot appelle `vers` (ex. +33612345678) depuis le numéro Twilio. Renvoie l'identifiant de l'appel."""
    c, compte = _client()
    r = c.post(f"{API}/Accounts/{compte}/Calls.json",
               data={"To": vers, "From": env("TWILIO_PHONE_NUMBER"), "Url": adresse_voix, "Method": "GET"})
    if r.status_code >= 400:
        detail = r.json().get("message", r.text[:200])
        if "permission" in detail.lower() or r.json().get("code") in (21215, 13227):
            detail += " → active la France dans Twilio : Voice → Settings → Geo permissions."
        raise SystemExit(f"Twilio refuse l'appel : {detail}")
    return r.json()["sid"]


def remettre() -> None:
    """Rattache le numéro à son ancien trunk (l'ancien callbot LiveKit répond de nouveau)."""
    s = json.loads(SAUVEGARDE.read_text())
    c, compte = _client()
    c.post(f"{API}/Accounts/{compte}/IncomingPhoneNumbers/{s['sid']}.json",
           data={"VoiceUrl": s.get("voice_url") or "", "VoiceMethod": s.get("voice_method") or "POST"}).raise_for_status()
    if s.get("trunk_sid"):
        r = c.post(f"{TRUNKING}/Trunks/{s['trunk_sid']}/PhoneNumbers", data={"PhoneNumberSid": s["sid"]})
        if r.status_code not in (200, 201, 409):
            r.raise_for_status()
    print(f"{s['numero']} est de nouveau rattaché à son ancienne configuration (trunk {s.get('trunk_sid')}).")


if __name__ == "__main__":
    charger_env()
    if "--remettre" in sys.argv:
        remettre()
    else:
        print(__doc__)
