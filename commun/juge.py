"""
Le juge : un petit modèle rapide qui lit ce qui a été entendu et dit si c'est bien l'utilisateur
(et pas une annonce, la télé, un voisin…). Mêmes consignes que l'app.
"""

from __future__ import annotations

import json
import time

import httpx

from .config import modele_juge

CONSIGNES = """You filter the microphone of a voice conversation between an AI assistant and a user, possibly in a noisy place.
You receive the assistant's last sentence and what a speech-to-text model heard since then. Speech-to-text on noise often produces empty text, filler ("you", "Thank you.", "Bye.", "Hmm"), random words, subtitle-like phrases ("Thanks for watching"), or speech from other people, the TV or the radio.
Answer in JSON {"speech": bool, "finished": bool}.
- "speech": true if the text is plausibly the user talking in the conversation (answering, telling something, asking, reacting, asking to stop), in any language. False only for clear noise: empty or hallucinated filler, subtitle-like phrases, or speech that obviously comes from somewhere else (announcements, TV or radio news, adverts, other people talking to each other). When in doubt, true.
- If "Warning" lines are given (the voice does not match the user's voice print, or is much quieter than the user's usual voice), be strict: "speech" is true only if the text is a plausible direct reply or reaction of the caller to the assistant's last sentence (or a request to stop / repeat). A sentence that makes no sense here, or sounds like someone else talking (TV, people nearby, another conversation), is false.
- "finished": false only if the user clearly stopped in the middle of a sentence ("I think that", "and then the"). Otherwise true."""


class Juge:
    def __init__(self, fournisseur: str) -> None:
        self.url, self.cle, self.modele = modele_juge(fournisseur)
        self.client = httpx.AsyncClient(timeout=4.0)

    async def juger(self, ia: str, entendu: str, alertes: list[str] | None = None) -> tuple[dict, float]:
        """Renvoie ({speech, finished}, durée en ms). En cas de souci : on considère que c'est l'utilisateur."""
        t = time.perf_counter()
        corps = {
            "model": self.modele,
            "messages": [
                {"role": "system", "content": CONSIGNES},
                {"role": "user", "content": f"Assistant said: {ia[-600:] or '(nothing yet)'}\nHeard from the microphone: {entendu[:1500]}"
                 + "".join(f"\nWarning: {a}" for a in (alertes or []))},
            ],
            "response_format": {"type": "json_object"},
        }
        if "gpt-oss" in self.modele:
            corps["reasoning_effort"] = "low"
        if self.modele.startswith("gpt-5"):
            corps["reasoning_effort"] = "none"
        try:
            r = await self.client.post(f"{self.url}/chat/completions", headers={"Authorization": f"Bearer {self.cle}"}, json=corps)
            r.raise_for_status()
            v = json.loads(r.json()["choices"][0]["message"]["content"])
            return {"speech": bool(v.get("speech", True)), "finished": bool(v.get("finished", True))}, (time.perf_counter() - t) * 1000
        except Exception as e:
            return {"speech": True, "finished": True, "erreur": str(e)[:120]}, (time.perf_counter() - t) * 1000
