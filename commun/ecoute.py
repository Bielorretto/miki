"""
L'écoute : décide quand l'utilisateur parle, quand il a fini, et quel audio est utile.

Toutes les 32 ms :
  1. Silero dit si c'est de la parole humaine (le bruit du métro, de la rue, du vent → non).
  2. Le volume doit dépasser le fond (une voix lointaine, la télé → trop faible).
  3. Il faut les DEUX pour dire « l'utilisateur parle ».

Fin de phrase rapide, même dans le bruit :
  - on n'attend pas le silence (il n'y en a jamais dans le bruit), mais ~0,3 s sans *parole* ;
  - Smart Turn écoute l'intonation et dit si la phrase est finie (calculé pendant l'attente, donc prêt à temps) ;
  - s'il dit « pas fini », on attend la suite au maximum 1,5 s.

Audio utile : seulement de 0,2 s avant la voix à 0,15 s après. Le bruit avant / après n'est jamais envoyé
(il ne peut donc pas devenir de faux mots), et les longues pauses entre deux morceaux sont supprimées.

Événements envoyés (nom, données) :
  debut_tour, debut_parole, audio {pcm}, parole_longue, fin_morceau {duree_ms}, parole_jetee,
  fin_tour {audio, proba, raison}, niveau {fond, seuil, voix}
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np

from .config import Detection
from .modeles import Silero, SmartTurn

TRAME = 512
TRAME_MS = TRAME / 16  # 32 ms


def texte_fini(texte: str) -> bool:
    """Phrase transcrite clairement terminée : ponctuation finale, au moins 2 mots, ne finit pas sur « et », « de »…"""
    from .filtre import classer

    return bool(texte.strip()) and texte.rstrip()[-1] in ".?!" and classer(texte, "", False).genre == "finie"


def attente_selon_texte(texte: str, fini_ms: int) -> int:
    """Attente avant de répondre d'après la transcription en direct (souvent sans point final) :
    phrase finie → fini_ms ; pas de texte, ou au moins 2 mots qui ne s'arrêtent pas sur « et », « de »… → fini_ms + 300 ms."""
    from .filtre import SUSPENDUS, normaliser

    if texte_fini(texte):
        return fini_ms
    mots = normaliser(texte).split()
    if not mots or (len(mots) >= 2 and mots[-1] not in SUSPENDUS):
        # Pas encore de texte (phrase courte : Deepgram n'a rien envoyé en direct) ou phrase qui semble complète.
        return fini_ms + 300
    return 10_000  # « je suis allé à la… » : on garde l'attente normale


def db(x: np.ndarray) -> float:
    return 20 * np.log10(max(float(np.sqrt(np.mean(x * x))), 1e-5))


class Ecoute:
    def __init__(self, det: Detection, emettre: Callable[[str, dict], None], telephone: bool = False) -> None:
        self.det = det
        self.emettre = emettre
        self.silero = Silero(reset_silence=telephone)
        self.telephone = telephone
        self.texte_partiel = ""  # transcription en direct du tour (donnée par la conversation)
        self.epellation = False  # l'IA a demandé d'épeler : les lettres sont séparées de pauses, on attend la fin
        self.smart = SmartTurn()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.ia_parle = False

        self._reste = np.zeros(0, np.float32)
        self._histo: deque[tuple[np.ndarray, float, float]] = deque(maxlen=int(det.marge_avant_ms / TRAME_MS) + 4)
        self._fond_histo: deque[float] = deque(maxlen=int(3000 / TRAME_MS))
        self.fond = -60.0
        self.voix: float | None = None  # niveau appris de la voix de l'utilisateur
        self._dernier_morceau_db: float | None = None

        self.etat = "repos"  # repos | parole | attente
        self._consecutives = 0
        self._segment: list[np.ndarray] = []
        self._segment_db: list[float] = []
        self._derniere_parole = 0
        self._envoye = 0
        self._silence = 0
        self._longue = False
        self._tour: list[np.ndarray] = []
        self._tour_avant = 0
        self._debut_voix = 0
        self._fin_morceau_t = 0.0
        self._parole_tour_ms = 0.0  # parole (ms) depuis le début du tour
        self._seq = 0
        self._spec: tuple[int, object] | None = None  # (seq, future) Smart Turn lancé en avance
        self._verdict: tuple[int, float, float] | None = None
        self._niveau_t = 0.0
        self.horloge = 0.0  # secondes d'audio traitées (fonctionne aussi plus vite que le temps réel)

    # ------------------------------------------------------------------ réglages appris

    def seuil(self) -> float:
        d = self.det
        s = max(d.min_db, self.fond + d.ecart_fond_db)
        if self.voix is not None:
            s = max(s, self.voix - d.marge_voix_db)
        return s + (d.ecart_ia_db if self.ia_parle else 0.0)

    def confirmer_voix(self) -> None:
        """Le dernier morceau était bien l'utilisateur : on apprend le niveau de sa voix."""
        if self._dernier_morceau_db is None:
            return
        v = self._dernier_morceau_db
        self.voix = v if self.voix is None else 0.8 * self.voix + 0.2 * v
        self._dernier_morceau_db = None

    # ------------------------------------------------------------------ entrée audio

    def micro(self, bloc: np.ndarray) -> None:
        """Reçoit du son à 16 kHz (n'importe quelle taille), traite par trames de 32 ms."""
        self._reste = np.concatenate([self._reste, bloc])
        while len(self._reste) >= TRAME:
            t, self._reste = self._reste[:TRAME], self._reste[TRAME:]
            self._trame(t)

    def _trame(self, x: np.ndarray) -> None:
        d = self.det
        p = self.silero(x)
        niveau = db(x)
        seuil = self.seuil()
        # Épellation : Silero hésite sur une voyelle seule (« O », « U » : 0,2-0,4) ; le niveau, lui, reste exigé.
        sp, ss = (d.seuil_parole_epellation, d.seuil_parole_epellation) if self.epellation else (d.seuil_parole, d.seuil_silence)
        voix_ici = p >= sp and niveau >= seuil
        encore = p >= ss and niveau >= seuil - 4  # pendant la parole : plus tolérant

        self.horloge += TRAME_MS / 1000
        maintenant = self.horloge
        if maintenant - self._niveau_t > 5 and self.etat != "parole":
            self._niveau_t = maintenant
            self.emettre("niveau", {"fond": round(self.fond), "seuil": round(seuil), "voix": None if self.voix is None else round(self.voix)})

        if self.etat in ("repos", "attente"):
            self._histo.append((x, p, niveau))
            if p < d.seuil_parole:
                # Le fond ne se mesure que hors de la voix : sinon, des mots courts séparés de pauses
                # (une épellation « D… I… O… ») font monter le fond jusqu'au niveau de la voix, qui n'est plus entendue.
                self._fond_histo.append(niveau)
            if len(self._fond_histo) % 4 == 0 or len(self._fond_histo) < 8:
                self.fond = float(np.percentile(self._fond_histo, 80))
            self._consecutives = self._consecutives + 1 if voix_ici else 0
            if self._consecutives * TRAME_MS >= d.debut_ms:
                self._commencer(niveau)
                return
            if self.etat == "attente":
                self._verifier_attente(maintenant)
            return

        # --- l'utilisateur parle
        self._segment.append(x)
        i = len(self._segment) - 1
        if voix_ici or encore:
            if self._silence and self._spec is not None:
                # La parole reprend : le calcul Smart Turn fait en avance n'est plus valable.
                self._seq += 1
                self._spec = None
            self._silence = 0
            self._derniere_parole = i
            self._segment_db.append(niveau)
        else:
            self._silence += 1
        # Audio utile jusqu'à la dernière parole + marge (le reste attend de savoir si la parole reprend).
        limite = min(i, self._derniere_parole + int(d.marge_apres_ms / TRAME_MS))
        while self._envoye <= limite:
            self.emettre("audio", {"pcm": self._segment[self._envoye]})
            self._tour.append(self._segment[self._envoye])
            self._envoye += 1
        if not self._longue and (self._derniere_parole - self._debut_voix + 1) * TRAME_MS >= d.barge_ms:
            self._longue = True
            self.emettre("parole_longue", {})
        silence_ms = self._silence * TRAME_MS
        if self._spec is None and silence_ms >= d.fin_ms / 2:
            # Smart Turn calculé en avance, pendant l'attente : le résultat est prêt quand on en a besoin.
            audio = np.concatenate(self._tour) if self._tour else np.zeros(0, np.float32)
            seq = self._seq
            self._spec = (seq, self.pool.submit(self.smart, audio))
        if silence_ms >= d.fin_ms:
            self._finir_morceau(maintenant)

    # ------------------------------------------------------------------ étapes

    def _commencer(self, niveau: float) -> None:
        self._seq += 1
        nouveau_tour = self.etat == "repos"
        if nouveau_tour:
            self.texte_partiel = ""
            self._tour = []
            self._parole_tour_ms = 0.0
            self.emettre("debut_tour", {})
        self._tour_avant = len(self._tour)
        self.emettre("debut_parole", {"db": round(niveau), "fond": round(self.fond), "seuil": round(self.seuil())})
        # On reprend un peu avant le début de la voix (marge).
        avant = list(self._histo)
        self._segment = [a for a, _, _ in avant]
        self._segment_db = [n for _, p, n in avant if p >= self.det.seuil_parole]
        self._derniere_parole = len(self._segment) - 1
        self._debut_voix = max(0, len(self._segment) - self._consecutives)
        self._envoye = 0
        self._silence = 0
        self._longue = False
        self._spec = None
        self._verdict = None
        self._consecutives = 0
        self._histo.clear()
        self.etat = "parole"

    def _finir_morceau(self, maintenant: float) -> None:
        d = self.det
        parole_ms = (self._derniere_parole - self._debut_voix + 1) * TRAME_MS
        if self._segment_db:
            self._dernier_morceau_db = float(np.percentile(self._segment_db, 70))
        self._histo.clear()
        if parole_ms < 120:
            self.emettre("parole_jetee", {"duree_ms": round(parole_ms)})
            self._tour = self._tour[: self._tour_avant]
            self.etat = "attente" if self._tour else "repos"
            self._fin_morceau_t = maintenant if self._tour else self._fin_morceau_t
            return
        self._parole_tour_ms += parole_ms
        self.emettre("fin_morceau", {"duree_ms": round(parole_ms)})
        self.etat = "attente"
        self._fin_morceau_t = maintenant
        spec = self._spec
        if spec is None:
            audio = np.concatenate(self._tour)
            spec = (self._seq, self.pool.submit(self.smart, audio))
        seq, fut = spec

        def resultat(f, seq=seq):
            try:
                p, ms = f.result()
                self._verdict = (seq, p, ms)
            except Exception:
                self._verdict = (seq, 1.0, 0.0)

        fut.add_done_callback(resultat)

    def _verifier_attente(self, maintenant: float) -> None:
        d = self.det
        v = self._verdict
        if self.epellation:
            # « D… I… O… U… F » : chaque lettre ressemble à une phrase finie ; seule une vraie pause termine le tour.
            if (maintenant - self._fin_morceau_t) * 1000 >= d.attente_epellation_ms:
                self._terminer_tour(-1.0, f"épellation : pas de lettre après {d.attente_epellation_ms} ms")
            return
        if v is not None and v[0] == self._seq and v[1] >= d.seuil_tour:
            self._terminer_tour(v[1], f"Smart Turn : fini ({v[1]:.2f}, {v[2]:.0f} ms)")
        else:
            # Un mot seul et court n'a pas d'intonation de fin : Smart Turn dit souvent « pas fini » à tort.
            court = self._parole_tour_ms <= d.mot_court_ms
            attente = d.attente_mot_court_ms if court else d.attente_max_ms
            if self.telephone:
                # Au téléphone, Smart Turn se trompe souvent (« Depuis 8 mois. » → 2 %) : le texte tranche.
                attente = min(attente, attente_selon_texte(self.texte_partiel, d.attente_texte_fini_ms))
            if (maintenant - self._fin_morceau_t) * 1000 >= attente:
                p = v[1] if v is not None and v[0] == self._seq else -1.0
                self._terminer_tour(p, f"pas de suite après {attente} ms" + (" (mot court)" if court else "") + (f" (Smart Turn {p:.2f})" if p >= 0 else ""))

    def _terminer_tour(self, proba: float, raison: str) -> None:
        audio = np.concatenate(self._tour) if self._tour else np.zeros(0, np.float32)
        self._tour = []
        self.etat = "repos"
        self._verdict = None
        self.emettre("fin_tour", {"audio": audio, "proba": proba, "raison": raison})

    def forcer_fin(self) -> None:
        """Fin de tour demandée (touche Entrée)."""
        if self.etat == "attente" or self._tour:
            self._terminer_tour(1.0, "forcé")
