"""
Micro et haut-parleur, identiques pour les deux programmes.

- Le micro est lu en blocs de 10 ms à 48 kHz, ramené à 16 kHz, puis nettoyé par l'anti-écho WebRTC
  (bibliothèque livekit, utilisée en local : aucun compte ni connexion) qui retire la voix de l'IA.
- Le haut-parleur lit une file de sons ; on peut baisser le volume en douceur (barge-in), tout couper,
  et savoir précisément combien de millisecondes de la réponse ont été entendues.

Quatre sorties possibles :
  mac      micro et haut-parleur de l'ordinateur (sounddevice / PortAudio)
  pulse    téléphone : PulseAudio de Termux (parec / pacat)
  fichier  tests : le « micro » est un fichier WAV lu en temps réel, la sortie est enregistrée
  twilio   appel téléphonique : le son arrive et repart par le websocket de Twilio (μ-law 8 kHz), voir appel/serveur.py.
           Pas d'anti-écho chez nous : c'est le téléphone de l'appelant qui retire l'écho.
"""

from __future__ import annotations

import subprocess
import threading
import time
import wave
from collections import deque
from typing import Callable

import numpy as np

DEVICE_RATE = 48000
RATE = 16000  # tout le traitement se fait à 16 kHz
BLOC = DEVICE_RATE // 100  # 10 ms


class Reechantillonneur:
    """Changement de fréquence propre (filtre passe-bas à fenêtre de Kaiser), en continu par petits blocs.
    Nécessaire pour le téléphone : l'interpolation linéaire étouffe la voix et ajoute des parasites
    (« Mohamed » devenait « Dieu khmaled »)."""

    def __init__(self, src: int, dst: int, taps_par_phase: int = 16) -> None:
        from math import gcd

        g = gcd(src, dst)
        self.L, self.M = dst // g, src // g  # on monte de L, on descend de M
        coupure = 0.5 / max(self.L, self.M)  # fréquence de coupure (en part de la fréquence montée)
        n = taps_par_phase * max(self.L, self.M) | 1
        t = np.arange(n) - (n - 1) / 2
        h = 2 * coupure * np.sinc(2 * coupure * t) * np.kaiser(n, 8.0)
        self.h = (h * self.L / h.sum()).astype(np.float32)
        self.reste = np.zeros(n - 1, np.float32)  # fin du bloc précédent (continuité du filtre)
        self.phase = 0  # position de décimation

    def __call__(self, x: np.ndarray) -> np.ndarray:
        if self.L > 1:
            up = np.zeros(len(x) * self.L, np.float32)
            up[:: self.L] = x
        else:
            up = x.astype(np.float32)
        y = np.convolve(np.concatenate([self.reste, up]), self.h, mode="valid")
        self.reste = np.concatenate([self.reste, up])[-(len(self.h) - 1):]
        out = y[self.phase :: self.M]
        self.phase = (self.phase - len(y)) % self.M
        return out.astype(np.float32)


# μ-law (G.711), le format du téléphone. (audioop n'existe plus depuis Python 3.13.)
def ulaw_vers_float(b: bytes) -> np.ndarray:
    u = ~np.frombuffer(b, np.uint8).astype(np.int32) & 0xFF
    signe = u & 0x80
    exposant = (u >> 4) & 0x07
    mantisse = u & 0x0F
    x = (((mantisse << 3) + 0x84) << exposant) - 0x84
    return (np.where(signe, -x, x) / 32768.0).astype(np.float32)


def float_vers_ulaw(x: np.ndarray) -> bytes:
    v = (np.clip(x, -1, 1) * 32767).astype(np.int32)
    signe = (v < 0).astype(np.int32) << 7
    v = np.minimum(np.abs(v), 32635) + 0x84
    exposant = np.clip(np.floor(np.log2(v)).astype(np.int32) - 7, 0, 7)
    mantisse = (v >> (exposant + 3)) & 0x0F
    return (~(signe | (exposant << 4) | mantisse) & 0xFF).astype(np.uint8).tobytes()


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    """Rééchantillonnage linéaire (suffisant pour de la voix)."""
    if src == dst or len(x) == 0:
        return x.astype(np.float32)
    n = int(round(len(x) * dst / src))
    t = np.linspace(0, len(x) - 1, n)
    return np.interp(t, np.arange(len(x)), x).astype(np.float32)


def pcm16_vers_float(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.int16).astype(np.float32) / 32768.0


def float_vers_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()


class Lecteur:
    """File de lecture du haut-parleur, avec volume progressif et position de lecture."""

    def __init__(self) -> None:
        self._file: deque[np.ndarray] = deque()
        self._courant = np.zeros(0, np.float32)
        self._lock = threading.Lock()
        self.gain = 1.0
        self._gain_cible = 1.0
        self.reference: deque[tuple[float, np.ndarray]] = deque(maxlen=400)  # (heure, son joué 16 kHz) pour l'anti-écho
        self.calibrage: deque[tuple[float, np.ndarray]] = deque(maxlen=800)  # 8 s de son joué, pour mesurer le retard de l'écho
        self.joue_ms = 0.0  # ce qui a été entendu de la réponse en cours
        self.en_lecture = False
        self.enregistrement: list[np.ndarray] | None = None
        self._bloque = False  # réponse prête mais en attente du feu vert du juge : rien ne sort
        self.sur_coupure: Callable[[], None] | None = None  # téléphone : vider aussi le tampon de Twilio

    def bloquer(self, oui: bool) -> None:
        self._bloque = oui

    def ajouter(self, pcm: np.ndarray, rate: int) -> None:
        """Ajoute du son (float -1..1) à la suite de la réponse en cours."""
        x = resample(pcm, rate, DEVICE_RATE)
        with self._lock:
            self._file.append(x)

    def nouvelle_reponse(self) -> None:
        self.joue_ms = 0.0

    def couper(self) -> None:
        self._bloque = False
        with self._lock:
            self._file.clear()
            self._courant = np.zeros(0, np.float32)
        self.en_lecture = False
        if self.sur_coupure:
            self.sur_coupure()

    def volume(self, cible: float) -> None:
        self._gain_cible = cible

    @property
    def vide(self) -> bool:
        with self._lock:
            return not self._file and len(self._courant) == 0

    def tirer(self, n: int = BLOC) -> np.ndarray:
        """Donne les n prochains échantillons à 48 kHz (appelé par la carte son)."""
        out = np.zeros(n, np.float32)
        rempli = 0
        with self._lock:
            while rempli < n and not self._bloque:
                if len(self._courant) == 0:
                    if not self._file:
                        break
                    self._courant = self._file.popleft()
                k = min(n - rempli, len(self._courant))
                out[rempli : rempli + k] = self._courant[:k]
                self._courant = self._courant[k:]
                rempli += k
        self.en_lecture = rempli > 0
        if rempli:
            self.joue_ms += rempli / DEVICE_RATE * 1000
        # Volume progressif (sur ~20 ms) pour éviter les clics.
        if self.gain != self._gain_cible:
            ecart = self._gain_cible - self.gain
            nouveau = self._gain_cible if abs(ecart) <= 0.5 else self.gain + 0.5 * np.sign(ecart)
            out *= np.linspace(self.gain, nouveau, n, dtype=np.float32)
            self.gain = float(nouveau)
        elif self.gain != 1.0:
            out *= self.gain
        ref = resample(out, DEVICE_RATE, RATE)
        t = time.monotonic()
        self.reference.append((t, ref))
        self.calibrage.append((t, ref))
        if self.enregistrement is not None:
            self.enregistrement.append(ref)
        return out


class AntiEcho:
    """Anti-écho + anti-bruit WebRTC (local).

    Sur le téléphone, la voix de l'IA revient dans le micro ~0,4 s après avoir été envoyée au haut-parleur
    (tampons de PulseAudio / Android). L'anti-écho WebRTC ne sait pas chercher aussi loin : on retarde donc
    nous-mêmes le son de référence de `retard_ms` pour qu'il arrive en même temps que son écho.
    Le retard est mesuré automatiquement pendant la phrase d'accueil (Audio.mesurer_retard).
    """

    def __init__(self, actif: bool = True, delai_ms: int = 60, retard_ms: float = 0.0) -> None:
        self.apm = None
        self.retard_ms = retard_ms
        if not actif:
            return
        try:
            from livekit import rtc

            self._rtc = rtc
            self.apm = rtc.AudioProcessingModule(echo_cancellation=True, noise_suppression=True, high_pass_filter=True, auto_gain_control=False)
            self.apm.set_stream_delay_ms(delai_ms)
        except Exception as e:  # pragma: no cover
            print(f"[audio] anti-écho indisponible : {e}")

    def _frame(self, x: np.ndarray):
        return self._rtc.AudioFrame(data=float_vers_pcm16(x), sample_rate=RATE, num_channels=1, samples_per_channel=len(x))

    def traiter(self, micro: np.ndarray, reference: deque) -> np.ndarray:
        if self.apm is None:
            reference.clear()
            return micro
        limite = time.monotonic() - self.retard_ms / 1000
        while reference and reference[0][0] <= limite:
            _, ref = reference.popleft()
            if len(ref) == RATE // 100:
                self.apm.process_reverse_stream(self._frame(ref))
        f = self._frame(micro)
        self.apm.process_stream(f)
        return pcm16_vers_float(bytes(f.data))


class Audio:
    """Point d'entrée : démarre le micro et le haut-parleur, appelle `sur_micro(bloc_16k)` toutes les 10 ms."""

    def __init__(self, mode: str, sur_micro: Callable[[np.ndarray], None], anti_echo: bool = True) -> None:
        self.mode = mode
        self.sur_micro = sur_micro
        self.lecteur = Lecteur()
        # Retard de départ (corrigé par la mesure) : ~0,4 s sur le téléphone, presque rien sur Mac.
        self.echo = AntiEcho(anti_echo and mode not in ("twilio",) and not mode.startswith("fichier"), retard_ms=0.0 if mode == "mac" else 200.0)
        self.micro_brut: deque[tuple[float, np.ndarray]] = deque(maxlen=900)  # micro avant anti-écho (calibrage)
        self.enregistrement_micro: list[np.ndarray] = []
        self.enregistrer = True
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._procs: list[subprocess.Popen] = []
        self._stream_in = None
        self._stream_out = None
        self.fin_fichier = threading.Event()

    # ------------------------------------------------------------------ commun

    def _micro_48k(self, x48: np.ndarray) -> None:
        x16 = resample(x48, DEVICE_RATE, RATE)[: RATE // 100]
        if len(x16) < RATE // 100:
            x16 = np.pad(x16, (0, RATE // 100 - len(x16)))
        self.micro_brut.append((time.monotonic(), x16))
        propre = self.echo.traiter(x16, self.lecteur.reference)
        if self.enregistrer:
            self.enregistrement_micro.append(propre)
        self.sur_micro(propre)

    # ------------------------------------------------------------------ Appel téléphonique (Twilio)

    def twilio_entree(self, ulaw: bytes) -> None:
        """Son de l'appelant (μ-law 8 kHz, par paquets de 20 ms) → 16 kHz filtré → traitement par blocs de 10 ms."""
        if not hasattr(self, "_monte"):
            self._monte, self._tampon16 = Reechantillonneur(8000, RATE), np.zeros(0, np.float32)
        self._tampon16 = np.concatenate([self._tampon16, self._monte(ulaw_vers_float(ulaw))])
        n = RATE // 100
        while len(self._tampon16) >= n:
            x16, self._tampon16 = self._tampon16[:n], self._tampon16[n:]
            self.micro_brut.append((time.monotonic(), x16))
            if self.enregistrer:
                self.enregistrement_micro.append(x16)
            self.sur_micro(x16)

    def twilio_sortie(self) -> bytes:
        """20 ms de voix de l'IA en μ-law 8 kHz (du silence s'il n'y a rien à dire)."""
        if not hasattr(self, "_descend"):
            self._descend = Reechantillonneur(DEVICE_RATE, 8000)
        return float_vers_ulaw(self._descend(self.lecteur.tirer(2 * BLOC)))

    def mesurer_retard(self) -> tuple[float, float, float] | None:
        """Retard (ms) entre le son joué et son écho dans le micro, la force de la ressemblance (0..1) et la netteté du pic.
        À appeler juste après une phrase de l'IA (sans que l'utilisateur parle)."""
        ref, mic = list(self.lecteur.calibrage), list(self.micro_brut)
        if len(ref) < 200 or len(mic) < 200:
            return None
        t0 = min(ref[0][0], mic[0][0])
        n = int((max(ref[-1][0], mic[-1][0]) - t0) / 0.01) + 2
        a, m = np.zeros(n * 160, np.float32), np.zeros(n * 160, np.float32)
        for t, x in ref:
            i = int(round((t - t0) / 0.01)) * 160
            a[i : i + len(x)] = x[: max(0, len(a) - i)]
        for t, x in mic:
            i = int(round((t - t0) / 0.01)) * 160
            m[i : i + len(x)] = x[: max(0, len(m) - i)]
        if np.sqrt(np.mean(a**2)) < 0.005:
            return None  # l'IA n'a pas assez parlé
        # On compare des enveloppes en dB (volume toutes les 10 ms, plancher -50 dB) : robuste et rapide.
        def env(x: np.ndarray) -> np.ndarray:
            e = 20 * np.log10(np.sqrt((x.reshape(-1, 160) ** 2).mean(1)) + 1e-4)
            e = np.maximum(e, -50.0)
            return e - e.mean()

        ea, em = env(a), env(m)
        scores = []
        for k in range(0, 80):  # 0 à 800 ms
            x, y = ea[: len(ea) - k], em[k:]
            scores.append(float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9)))
        r = np.array(scores)
        k = int(r.argmax())
        # Pic net = bien au-dessus des autres retards (sinon c'est du hasard).
        return k * 10.0, float(r[k]), float(r[k] - np.median(r))

    def demarrer(self) -> None:
        mode = self.mode
        if mode == "auto":
            import platform

            mode = "mac" if platform.system() == "Darwin" else "pulse"
        if mode == "mac":
            self._demarrer_sounddevice()
        elif mode == "pulse":
            self._demarrer_pulse()
        elif mode == "twilio":
            pass  # le son est poussé par le serveur d'appels (twilio_entree / twilio_sortie)
        elif mode.startswith("fichier:"):
            self._demarrer_fichier(mode.split(":", 1)[1])
        else:
            raise ValueError(f"mode audio inconnu : {mode}")

    def arreter(self) -> None:
        self._stop.set()
        for p in self._procs:
            p.kill()
        for s in (self._stream_in, self._stream_out):
            if s is not None:
                s.stop()
                s.close()

    # ------------------------------------------------------------------ Mac / PC

    def _demarrer_sounddevice(self) -> None:
        import sounddevice as sd

        def entree(indata, frames, t, status):
            self._micro_48k(indata[:, 0].copy())

        def sortie(outdata, frames, t, status):
            outdata[:, 0] = self.lecteur.tirer(frames)

        self._stream_in = sd.InputStream(samplerate=DEVICE_RATE, channels=1, dtype="float32", blocksize=BLOC, callback=entree, latency="low")
        self._stream_out = sd.OutputStream(samplerate=DEVICE_RATE, channels=1, dtype="float32", blocksize=BLOC, callback=sortie, latency="low")
        self._stream_out.start()
        self._stream_in.start()

    # ------------------------------------------------------------------ Téléphone (PulseAudio de Termux)

    def _demarrer_pulse(self) -> None:
        env = {"PULSE_SERVER": "tcp:127.0.0.1:4713"}
        import os

        e = {**os.environ, **env}
        rec = subprocess.Popen(
            ["parec", "--rate", str(DEVICE_RATE), "--channels", "1", "--format", "s16le", "--latency-msec", "20"],
            stdout=subprocess.PIPE, env=e,
        )
        play = subprocess.Popen(
            ["pacat", "--playback", "--rate", str(DEVICE_RATE), "--channels", "1", "--format", "s16le", "--latency-msec", "150"],
            stdin=subprocess.PIPE, env=e,
        )
        self._procs += [rec, play]

        def lire():
            taille = BLOC * 2
            while not self._stop.is_set():
                b = rec.stdout.read(taille)
                if not b:
                    break
                self._micro_48k(pcm16_vers_float(b))

        def ecrire():
            # On écrit au rythme réel, avec 80 ms d'avance : un petit retard de Python ne crée plus de coupure
            # (sinon la voix sonne « robotique »).
            t0 = time.monotonic()
            k = 0
            avance = 8
            while not self._stop.is_set():
                play.stdin.write(float_vers_pcm16(self.lecteur.tirer(BLOC)))
                play.stdin.flush()
                k += 1
                attente = t0 + (k - avance) * 0.01 - time.monotonic()
                if attente > 0:
                    time.sleep(attente)

        for f in (lire, ecrire):
            th = threading.Thread(target=f, daemon=True)
            th.start()
            self._threads.append(th)

    # ------------------------------------------------------------------ Tests : fichier WAV

    def _demarrer_fichier(self, chemin: str) -> None:
        with wave.open(chemin) as w:
            rate = w.getframerate()
            x = pcm16_vers_float(w.readframes(w.getnframes()))
            if w.getnchannels() > 1:
                x = x.reshape(-1, w.getnchannels()).mean(axis=1)
        x48 = resample(x, rate, DEVICE_RATE)

        def boucle():
            t0 = time.monotonic()
            k = 0
            while not self._stop.is_set():
                debut = k * BLOC
                bloc = x48[debut : debut + BLOC]
                if len(bloc) < BLOC:
                    bloc = np.pad(bloc, (0, BLOC - len(bloc)))
                    if debut >= len(x48) + DEVICE_RATE * 8:
                        self.fin_fichier.set()
                # Écho simulé : un peu de la voix de l'IA revient dans le micro.
                sortie = self.lecteur.tirer(BLOC)
                self._micro_48k(bloc + sortie * 0.05)
                k += 1
                attente = t0 + k * 0.01 - time.monotonic()
                if attente > 0:
                    time.sleep(attente)

        th = threading.Thread(target=boucle, daemon=True)
        th.start()
        self._threads.append(th)
