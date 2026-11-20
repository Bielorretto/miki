"""
Reconnaissance de la voix de l'utilisateur (empreinte vocale), en local.

Modèle : WeSpeaker CAM++ (VoxCeleb), ~29 Mo, onnxruntime sur le processeur (~30-80 ms par phrase).
  - Les premières phrases acceptées (parole confirmée) construisent l'empreinte de l'utilisateur.
  - Ensuite, chaque phrase est comparée à l'empreinte (similarité cosinus) :
      proche → c'est lui ; très différente → une autre voix (télé, voisin, passant).
  - L'empreinte continue de s'affiner avec chaque phrase acceptée qui lui ressemble bien.
"""

from __future__ import annotations

import time

import numpy as np

from .modeles import DOSSIER, _session

MODELE = "wespeaker_en_voxceleb_CAM++.onnx"
URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/{MODELE}"


def _mel_banque(n_fft: int = 512, n_mels: int = 80, sr: int = 16000, bas: float = 20.0, haut: float = 8000.0) -> np.ndarray:
    """Banque de filtres mel façon Kaldi (triangles sur l'échelle mel 1127·ln(1+f/700))."""
    mel = lambda f: 1127.0 * np.log(1.0 + f / 700.0)
    m_bas, m_haut = mel(bas), mel(haut)
    centres = np.linspace(m_bas, m_haut, n_mels + 2)
    freqs = mel(np.arange(n_fft // 2 + 1) * sr / n_fft)
    b = np.zeros((n_mels, n_fft // 2 + 1), np.float32)
    for i in range(n_mels):
        g, c, d = centres[i], centres[i + 1], centres[i + 2]
        monte = (freqs - g) / (c - g)
        descend = (d - freqs) / (d - c)
        b[i] = np.maximum(0.0, np.minimum(monte, descend))
    return b


_BANQUE = _mel_banque()
_FENETRE = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(400) / 399)) ** 0.85  # fenêtre « povey » de Kaldi


def fbank(audio: np.ndarray) -> np.ndarray:
    """80 fbank Kaldi (25 ms / 10 ms) d'un son 16 kHz en float [-1, 1], moyenne retirée (CMN)."""
    x = audio.astype(np.float32) * 32768.0
    n = 1 + (len(x) - 400) // 160
    if n <= 0:
        return np.zeros((0, 80), np.float32)
    idx = np.arange(400)[None, :] + 160 * np.arange(n)[:, None]
    tr = x[idx]
    tr = tr - tr.mean(1, keepdims=True)
    tr = np.concatenate([tr[:, :1] * (1 - 0.97), tr[:, 1:] - 0.97 * tr[:, :-1]], axis=1)
    tr = tr * _FENETRE
    p = np.abs(np.fft.rfft(tr, 512)) ** 2
    f = np.log(np.maximum(p @ _BANQUE.T, 1.1920929e-07)).astype(np.float32)
    return f - f.mean(0, keepdims=True)


class Locuteur:
    def __init__(self, phrases_min: int = 2, secondes_min: float = 2.0) -> None:
        f = DOSSIER / MODELE
        if not f.exists():
            import urllib.request

            print(f"Téléchargement de {MODELE}…")
            DOSSIER.mkdir(exist_ok=True)
            urllib.request.urlretrieve(URL, f)
        self.s = _session(f, threads=2)
        self.phrases_min = phrases_min
        self.secondes_min = secondes_min
        self.somme: np.ndarray | None = None
        self.n = 0
        self.secondes = 0.0

    def empreinte(self, audio: np.ndarray) -> tuple[np.ndarray | None, float]:
        """Empreinte (vecteur normalisé) d'un morceau de son 16 kHz ; renvoie aussi la durée du calcul (ms)."""
        t = time.perf_counter()
        if len(audio) < 16000 * 0.5:
            return None, 0.0
        f = fbank(audio)[None]
        e = self.s.run(None, {"feats": f})[0][0]
        return e / (np.linalg.norm(e) + 1e-9), (time.perf_counter() - t) * 1000

    @property
    def pret(self) -> bool:
        return self.somme is not None and self.n >= self.phrases_min and self.secondes >= self.secondes_min

    def similarite(self, e: np.ndarray) -> float:
        if self.somme is None:
            return 0.0
        ref = self.somme / (np.linalg.norm(self.somme) + 1e-9)
        return float(np.dot(ref, e))

    def apprendre(self, e: np.ndarray, secondes: float) -> None:
        """Ajoute une phrase confirmée de l'utilisateur à son empreinte (pondérée par la durée)."""
        poids = min(secondes, 4.0)
        self.somme = e * poids if self.somme is None else self.somme + e * poids
        self.n += 1
        self.secondes += secondes
