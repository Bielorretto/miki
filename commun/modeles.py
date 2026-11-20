"""Modèles locaux (onnxruntime, sur le processeur) : Silero (parole ou non) et Smart Turn (phrase finie ou non)."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

ort.set_default_logger_severity(3)

from .config import RACINE
from .whisper_features import compute_whisper_log_mel_features

DOSSIER = RACINE / "models"
URLS = {
    "silero_vad.onnx": "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx",
    "smart-turn-v3.2-cpu.onnx": "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/smart-turn-v3.2-cpu.onnx",
}


def telecharger() -> None:
    import urllib.request

    DOSSIER.mkdir(exist_ok=True)
    for nom, url in URLS.items():
        f = DOSSIER / nom
        if not f.exists():
            print(f"Téléchargement de {nom}…")
            urllib.request.urlretrieve(url, f)


def _session(chemin: Path, threads: int = 1) -> ort.InferenceSession:
    if not chemin.exists():
        telecharger()
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    so.log_severity_level = 3
    return ort.InferenceSession(str(chemin), sess_options=so, providers=["CPUExecutionProvider"])


class Silero:
    """Probabilité de parole humaine par trame de 32 ms (512 échantillons à 16 kHz)."""

    TRAME = 512
    CONTEXTE = 64

    def __init__(self, reset_silence: bool = False) -> None:
        self.s = _session(DOSSIER / "silero_vad.onnx")
        # Téléphone : entre les phrases, le réseau envoie un silence numérique parfait (-73 dB constant).
        # Au bout de quelques secondes, la mémoire de Silero se dérègle et il ne reconnaît plus la voix (0 %).
        # On la remet à zéro après 0,5 s de ce silence.
        self.reset_silence = reset_silence
        self._calme = 0
        self.reset()

    def reset(self) -> None:
        self.etat = np.zeros((2, 1, 128), np.float32)
        self.contexte = np.zeros(self.CONTEXTE, np.float32)

    def __call__(self, trame: np.ndarray) -> float:
        if self.reset_silence:
            self._calme = self._calme + 1 if float(np.mean(trame.astype(np.float32) ** 2)) < 1e-6 else 0  # < -60 dB
            if self._calme == 16:  # 16 × 32 ms ≈ 0,5 s
                self.reset()
        x = np.concatenate([self.contexte, trame.astype(np.float32)])[None, :]
        out, self.etat = self.s.run(None, {"input": x, "state": self.etat, "sr": np.array(16000, np.int64)})
        self.contexte = trame[-self.CONTEXTE :].astype(np.float32)
        return float(out[0][0])


class SmartTurn:
    """Écoute la fin d'une phrase (intonation, rythme) et dit si l'utilisateur a fini de parler."""

    def __init__(self) -> None:
        self.s = _session(DOSSIER / "smart-turn-v3.2-cpu.onnx", threads=2)

    def __call__(self, audio: np.ndarray) -> tuple[float, float]:
        """Renvoie (probabilité « fini », durée du calcul en ms)."""
        t = time.perf_counter()
        n = 8 * 16000
        a = audio[-n:] if len(audio) > n else np.pad(audio, (n - len(audio), 0))
        feats = compute_whisper_log_mel_features(a.astype(np.float32), do_normalize=True)[None, :, :]
        p = float(self.s.run(None, {"input_features": feats})[0][0][0])
        return p, (time.perf_counter() - t) * 1000
