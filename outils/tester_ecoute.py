"""Passe un fichier WAV dans l'écoute (plus vite que le temps réel) et affiche ce qu'elle décide.

    python -m outils.tester_ecoute chemin.wav
"""

import sys
import time
import wave

import numpy as np

from commun.audio import resample
from commun.config import Detection
from commun.ecoute import Ecoute

chemin = sys.argv[1]
with wave.open(chemin) as w:
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    x = resample(x, w.getframerate(), 16000)

journal = []


def emettre(nom, data):
    if nom == "audio":
        return
    info = {k: v for k, v in data.items() if k != "audio"}
    if nom == "fin_tour":
        info["duree_audio_s"] = round(len(data["audio"]) / 16000, 2)
    journal.append(f"{e.horloge:7.2f}s  {nom:14s} {info if info else ''}")


e = Ecoute(Detection(), emettre)
t = time.perf_counter()
for i in range(0, len(x), 160):
    e.micro(x[i : i + 160])
    # laisse le temps au calcul Smart Turn (fait en parallèle dans l'app)
    if e.etat == "attente":
        time.sleep(0.01)  # temps réel pendant l'attente : Smart Turn a le temps de répondre
print("\n".join(journal))
print(f"\n{len(x)/16000:.1f} s d'audio traitées en {time.perf_counter()-t:.1f} s")
