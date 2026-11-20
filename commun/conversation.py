"""
Le chef d'orchestre, commun aux deux programmes.

Il reçoit les événements de l'écoute (commun/ecoute.py) et décide :
  - tour fini → transcription → filtre (bruit ? écho ? phrase coupée ?) → juge si besoin → l'IA répond ;
  - l'IA parle et l'utilisateur parle ≥ 0,25 s → le son de l'IA baisse (pas coupé !) ;
      · de vrais mots confirmés → l'IA s'arrête et écoute (barge-in) ;
      · bruit, ou rien de confirmé en 2,5 s → le son remonte, l'IA continue.
Le bruit seul ne peut donc jamais couper l'IA.

Chaque programme fournit : transcrire(), repondre(), arreter_reponse(), et (option) des transcriptions partielles.
"""

from __future__ import annotations

import asyncio
import re
import signal
from abc import ABC, abstractmethod

import numpy as np

from .audio import Audio
from .config import Config
from .ecoute import Ecoute
from .filtre import Verdict, classer, dans_ia, mots_nouveaux, normaliser, retirer_echo
from .journal import Journal
from .juge import Juge
from .locuteur import Locuteur


REPETER = "Pardon, je n'ai pas bien compris. Pouvez-vous répéter ?"
# Rien entendu 3 s après la fin de la voix de l'IA (au téléphone) : relance, deux fois au plus. Formulée sans
# supposer que la personne s'est tue (elle a peut-être parlé sans être entendue).
RELANCES = ("Pardon, pouvez-vous répéter ?", "Pardon, pouvez-vous répéter ?")
PHRASES_FIXES = (REPETER, RELANCES[0])  # enregistrées une fois (ElevenLabs), puis dites sans attendre
SILENCE_RELANCE_S = 3.0
EPELER = re.compile(r"(?i:épel|orthograph|lettre|caractère)")
LETTRES_LUES = re.compile(r"\b[A-Z]\b(?:[ ,.-]+\b[A-Z]\b){2,}")


def demande_epeler(texte: str) -> bool:
    """L'IA demande d'épeler dans sa dernière phrase (« Pouvez-vous l'épeler ? ») : on attend toutes les lettres.
    « Je vais vous demander votre nom (en l'orthographiant…). Êtes-vous d'accord ? » n'en est pas une."""
    derniere = re.split(r"(?<=[.!?…])\s+", texte.strip())[-1]
    return bool(EPELER.search(derniere))


def relit_lettres(texte: str) -> bool:
    """L'IA relit UN mot épelé (« M, O, H, A… Est-ce correct ? ») : la réponse est le plus souvent « oui »
    (répondu sans attente), parfois une correction en lettres. Un récapitulatif relit plusieurs mots épelés
    (prénom ET nom) : là, on attend « oui/non »."""
    return not demande_epeler(texte) and len(LETTRES_LUES.findall(texte)) == 1


# Une lettre ou un mot épelé dans le texte transcrit (« Non, D-I-O-U-F », « DIOUF ») ; pas « J'ai », « OK ».
LETTRE_EPELEE = re.compile(r"\b(?!(?:OK|OUI|NON)\b)[A-Z]+\b(?!['’])")


def contient_lettres(texte: str) -> bool:
    return bool(LETTRE_EPELEE.search(texte))


CONFIRME = re.compile(r"(?i)\b(?:oui|ouais|non|correct|exact|d'accord|parfait|tout à fait|voilà|absolument|c'est (?:ça|bon))\b")


def lettres_possibles(texte: str) -> bool:
    """Après une relecture : des lettres (« DIOUF »), ou un début d'épellation lente mal transcrit (« M… » → « Me »).
    « Oui », « C'est ça », ou une vraie phrase : non."""
    t = texte.strip()
    return bool(t) and (contient_lettres(t) or (len(t.split()) <= 2 and not CONFIRME.search(t)))


def que_des_lettres(texte: str) -> bool:
    """« EMMED », « A M E D », « D-I-O-U-F » : une épellation, sans mot ordinaire."""
    t = texte.strip()
    return bool(re.fullmatch(r"[\s,.\-]*(?:[A-Z]+[\s,.\-]*)+", t)) and t.strip(" ,.-") not in ("OK", "OUI", "NON")


def lettres(texte: str) -> str:
    """Lettres épelées : Deepgram écrit la lettre O comme le chiffre 0 (« DI0UF », « M0HAMED ») ; on remet des O.
    Un nombre (« 20 ans ») n'est jamais touché."""
    texte = re.sub(r"\b[A-Z0-9]*[A-Z][A-Z0-9]*\b", lambda m: m.group().replace("0", "O"), texte)
    if len(re.findall(r"\b[A-Za-z]\b", texte)) >= 2:  # lettres séparées « D I 0 U F »
        texte = re.sub(r"\b0\b", "O", texte)
    return texte


class Conversation(ABC):
    nom = "base"
    avec_fiche = False  # le programme sait-il intercepter la fiche JSON avant la voix ?

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.journal = Journal(self.nom)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.file: asyncio.Queue = asyncio.Queue()
        self.ecoute = Ecoute(cfg.detection, self._evenement_thread, telephone=cfg.audio == "twilio")
        self.audio = Audio(cfg.audio, self.ecoute.micro)
        self.audio.enregistrer = cfg.enregistrer
        if cfg.enregistrer:
            self.audio.lecteur.enregistrement = []
        self.juge = Juge(cfg.juge)
        self.ia_texte = ""  # dernière réponse de l'IA (pour repérer son écho)
        self.repond = False  # une réponse est en cours (génération ou lecture)
        self.barge = False  # barge-in en cours de vérification
        self._barge_timer: asyncio.TimerHandle | None = None
        self._en_suspens = ""  # phrase pas finie, en attente de la suite
        self.phrase_fixe: str | None = None  # à dire telle quelle, sans le penseur (« Pardon, je n'ai pas compris »)
        self._suspens_timer: asyncio.TimerHandle | None = None
        self._tache_reponse: asyncio.Task | None = None
        self._fin = asyncio.Event()
        self.raccrocher = False  # l'IA a dit au revoir (balise <FIN>) : on termine l'appel après sa voix
        self._calme_depuis: float | None = None  # silence de l'utilisateur après la voix de l'IA (relance)
        self._relances = 0
        self._verrou = asyncio.Lock()
        self._annule = False  # la réponse en cours répondait à du bruit : ne rien en garder
        self._calibre = False
        # Empreinte vocale de l'utilisateur : les autres voix (télé, voisins) doivent passer par le juge.
        try:
            self.locuteur: Locuteur | None = Locuteur()
        except Exception as e:  # pas de modèle : on fait sans
            print(f"Reconnaissance de la voix indisponible : {e}")
            self.locuteur = None
        self.accueil = True  # l'IA dit bonjour : un petit bruit au décroché ne doit pas la couper
        self._ia_parlait = False  # l'IA parlait-elle quand ce tour a commencé ? (alors : pas d'apprentissage)
        self._tour: dict = {}
        self._question_ia = ""  # dernière vraie réponse de l'IA (pas « Pardon, pouvez-vous répéter ? »), pour le juge
        self.relecture = False  # l'IA vient de relire des lettres : « oui » sans attente, mais des lettres attendent la suite

    # ------------------------------------------------------------------ à fournir par chaque programme

    @abstractmethod
    async def connecter(self) -> None: ...

    @abstractmethod
    async def transcrire(self, audio: np.ndarray) -> str:
        """Texte du tour qui vient de finir."""

    @abstractmethod
    async def repondre(self, texte: str) -> None:
        """Génère et joue la réponse (doit pouvoir être annulée)."""

    @abstractmethod
    async def arreter_reponse(self) -> str:
        """Coupe la réponse en cours ; renvoie ce que l'utilisateur a réellement entendu."""

    async def oublier_tour(self, deja_repondu: bool = False) -> None:
        """Le tour était du bruit : l'oublier côté modèle (si besoin)."""

    async def retranscrire(self, audio: np.ndarray) -> str:
        """2e écoute du tour (fichier entier), quand la 1re n'a rien rendu alors que c'était bien la voix de l'utilisateur."""
        return ""

    def audio_utile(self, pcm: np.ndarray) -> None:
        """Audio utile en direct (pendant que l'utilisateur parle), pour un STT en continu."""

    def debut_tour(self) -> None:
        """L'utilisateur commence à parler."""

    async def fermer(self) -> None: ...

    # ------------------------------------------------------------------ boucle

    def _evenement_thread(self, nom: str, data: dict) -> None:
        """Appelé depuis le fil du micro : on repasse dans la boucle asyncio."""
        if nom == "audio":
            self.audio_utile(data["pcm"])
            return
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.file.put_nowait, (nom, data))

    @property
    def ia_parle(self) -> bool:
        return self.repond or self.audio.lecteur.en_lecture

    async def lancer(self) -> None:
        self.loop = asyncio.get_running_loop()
        for s in (signal.SIGINT, signal.SIGTERM) if self.cfg.audio != "twilio" else ():
            try:
                self.loop.add_signal_handler(s, self._fin.set)
            except NotImplementedError:
                pass
        self.journal.log("début", f"programme {self.nom} · rôle {self.cfg.role} · langue {self.cfg.langue} · audio {self.cfg.audio} · juge {self.cfg.juge}")
        await self.connecter()
        self.audio.demarrer()
        self.journal.log("prêt", "parle quand tu veux (Ctrl+C pour quitter)")
        await self._lancer_reponse("")  # l'IA dit bonjour
        consommateur = asyncio.create_task(self._consommer())
        while not self._fin.is_set() and not self.audio.fin_fichier.is_set():
            try:
                await asyncio.wait_for(self._fin.wait(), 0.2)
            except asyncio.TimeoutError:
                await self._verifier_silence()
        consommateur.cancel()
        self.audio.arreter()
        await self.fermer()
        dossier = self.journal.terminer(self.audio.enregistrement_micro, self.audio.lecteur.enregistrement)
        print(f"\nSession enregistrée dans {dossier}")

    async def _verifier_silence(self) -> None:
        """Au téléphone, pas de gros blanc : l'IA a fini de parler et n'entend rien depuis 3 s → « Pardon, pouvez-vous
        répéter ? » (phrase déjà enregistrée), deux fois au plus."""
        calme = (self.cfg.audio == "twilio" and not self.ia_parle and self.ecoute.etat == "repos" and not self._verrou.locked()
                 and not self._en_suspens and not self.raccrocher and self._relances < len(RELANCES))
        if not calme:
            self._calme_depuis = None
            return
        maintenant = self.loop.time()
        if self._calme_depuis is None:
            self._calme_depuis = maintenant
        elif maintenant - self._calme_depuis >= SILENCE_RELANCE_S:
            self._calme_depuis = None
            self.phrase_fixe = RELANCES[self._relances]
            self._relances += 1
            self.journal.log("silence", f"rien depuis {SILENCE_RELANCE_S:.0f} s → relance")
            await self._lancer_reponse("")

    async def _consommer(self) -> None:
        while True:
            nom, data = await self.file.get()
            try:
                await self._traiter(nom, data)
            except Exception as e:  # on ne laisse jamais la conversation s'arrêter sur une erreur
                self.journal.log("erreur", f"{nom} : {e!r}")

    async def _traiter(self, nom: str, data: dict) -> None:
        self.ecoute.ia_parle = self.ia_parle
        if nom == "niveau":
            self.journal.log("niveau", f"fond {data['fond']} dB · seuil {data['seuil']} dB · ta voix {data['voix'] if data['voix'] is not None else '?'} dB", afficher=False)
        elif nom == "debut_tour":
            self._ia_parlait = self.ia_parle
            self._relances = 0
            self.debut_tour()
            if self._suspens_timer:
                self._suspens_timer.cancel()
        elif nom == "debut_parole":
            self.journal.log("voix", f"début ({data['db']} dB, fond {data['fond']} dB, seuil {data['seuil']} dB)")
        elif nom == "parole_longue" and self.ia_parle and not self.barge:
            # Barge-in, étape 1 : on baisse le son de l'IA, sans la couper.
            self.barge = True
            self.audio.lecteur.volume(self.cfg.detection.volume_baisse)
            self.journal.log("barge-in", "parole pendant que l'IA parle → son baissé, vérification…")
            self._barge_timer = self.loop.call_later(self.cfg.detection.barge_confirm_ms / 1000, self._barge_annule, "rien de confirmé")
        elif nom == "parole_jetee":
            self.journal.log("voix", f"trop court ({data['duree_ms']} ms), ignoré")
            if self.barge and self.ecoute.etat == "repos":
                self._barge_annule("parole trop courte")
        elif nom == "fin_morceau":
            self.journal.log("voix", f"fin du morceau ({data['duree_ms']} ms de parole)")
        elif nom == "fin_tour":
            self.journal.log("fin tour", f"{data['raison']} · {len(data['audio']) / 16000:.2f} s d'audio utile")
            # En tâche à part : les autres événements (barge-in…) continuent d'être traités pendant la transcription.
            asyncio.create_task(self._fin_tour(data["audio"], data.get("proba", -1.0)))

    # ------------------------------------------------------------------ décisions

    async def _fin_tour(self, audio: np.ndarray, proba: float = -1.0) -> None:
        niveau, voix_db = self.ecoute._dernier_morceau_db, self.ecoute.voix
        ia_parlait = self._ia_parlait or self.ia_parle
        parole_ms = self.ecoute._parole_tour_ms
        # Empreinte vocale calculée pendant la transcription (pas de temps perdu).
        empreinte = asyncio.create_task(asyncio.to_thread(self.locuteur.empreinte, audio)) if self.locuteur else None
        # Épellation : le fichier entier est mieux compris que le flux (« NGUYEN » au lieu de « MJUYEN »), lancé en parallèle.
        fichier = asyncio.create_task(self.retranscrire(audio)) if self.ecoute.epellation or self.relecture else None
        async with self._verrou:  # un tour à la fois, dans l'ordre
            try:
                texte = await self.transcrire(audio)
                if fichier is not None and not self.ecoute.epellation and not lettres_possibles(lettres(texte)):
                    fichier.cancel()  # après une relecture, « Oui, c'est ça » : pas besoin du fichier entier
                    fichier = None
                if fichier is not None and (texte_fichier := (await fichier).strip()):
                    if texte_fichier != texte:
                        self.journal.log("épellation", f"flux « {texte} » → fichier « {texte_fichier} »")
                    texte = texte_fichier
                texte = lettres(texte)
                self.journal.log("entendu", f"« {texte} »")
                e, ms = await empreinte if empreinte else (None, 0.0)
                t = {"empreinte": e, "secondes": len(audio) / 16000, "ia_parlait": ia_parlait, "parole_ms": parole_ms, "smart_turn": proba, "alertes": []}
                if e is not None and self.locuteur.pret:
                    t["sim"] = self.locuteur.similarite(e)
                    self.journal.log("ta voix", f"ressemblance {t['sim']:.2f} ({ms:.0f} ms)")
                    if t["sim"] < self.cfg.detection.voix_min:
                        t["alertes"].append("the voice does not match the user's voice print")
                if niveau is not None and voix_db is not None and niveau < voix_db - self.cfg.detection.ecart_volume_db:
                    t["alertes"].append(f"much quieter than the user's usual voice ({niveau:.0f} dB vs {voix_db:.0f} dB)")
                if not texte.strip() and self._reecouter(t):
                    texte2 = (await self.retranscrire(audio)).strip()
                    self.journal.log("2e écoute", f"rien entendu mais c'était ta voix → « {texte2} »")
                    if texte2:
                        texte, t["reecoute"] = texte2, True
                self._tour = t
                if not texte.strip() and (t.get("sim", 0.0) >= 0.45 or self._reecouter(t)) and t["parole_ms"] >= 150:
                    # Ta voix, nette, mais aucun mot transcrit (même à la 2e écoute) : on fait répéter plutôt que se taire.
                    self.journal.log("ignoré", "«  » → texte vide")
                    await self.oublier_tour()
                    await self._faire_repeter(texte, t)
                    return
                await self._decider(texte)
            except Exception as e:
                self.journal.log("erreur", f"tour : {e!r}")

    def _reecouter(self, t: dict) -> bool:
        """Texte vide : faut-il réécouter ? Seulement si c'est sûrement l'utilisateur, pour que le bruit
        n'en profite jamais : empreinte prête, voix nettement ressemblante, au moins 150 ms de vraie parole.
        Le texte réécouté passe ensuite toujours par le juge, et n'entre jamais dans l'empreinte."""
        if self.cfg.audio == "twilio" and not t["ia_parlait"] and t["parole_ms"] >= 250:
            # Au téléphone, l'IA se taisait (pas d'écho) : un « non » d'une demi-seconde a une empreinte peu fiable (0,2-0,3).
            return True
        if self.locuteur is None or t.get("empreinte") is None or not self.locuteur.pret:
            return False
        return t.get("sim", 0.0) >= 0.35 and t["parole_ms"] >= 150

    async def transcription_partielle(self, texte: str) -> None:
        """STT en continu : confirme un barge-in sans attendre la fin de la phrase."""
        self.ecoute.texte_partiel = texte
        if not self.barge or not texte.strip():
            return
        ia = self.texte_ia_echo
        reste = retirer_echo(texte, ia, ia_parle=True)[0]
        v = classer(reste, ia, True)
        # Il faut au moins 2 mots que l'IA n'a PAS dits : « D'accord, mais » pendant « D'accord, merci… » = écho.
        if v.genre != "bruit" and mots_nouveaux(reste, ia) >= 2:
            self.journal.log("barge-in", f"confirmé en direct par « {reste} »")
            await self._couper_ia()

    async def _decider(self, brut: str) -> None:
        ia = self.texte_ia_echo
        if self.accueil and self._tour.get("parole_ms", 0.0) < 500:
            # Pendant l'accueil, un son très court (décroché, « allô », bruit de ligne) ne coupe pas l'IA :
            # sinon elle s'interrompt et recommence un nouveau bonjour.
            self.journal.log("ignoré", f"« {brut.strip()} » → son court pendant l'accueil")
            self.journal.ligne("user", brut.strip(), ignore="son court pendant l'accueil")
            await self.oublier_tour()
            if self.barge:
                self._barge_annule("son court pendant l'accueil")
            return
        if self.relecture and not self.barge and lettres_possibles(brut):
            # Correction après la relecture (« Non, c'est D, I, O, U, F ») : la personne peut épeler en plusieurs fois,
            # on attend la suite un instant (la fin de tour normale, rapide, a pu couper entre deux lettres).
            texte = f"{self._en_suspens} {brut.strip()}".strip()
            self._en_suspens = ""
            self.journal.log("épellation", f"« {texte} » : lettres après la relecture")
            self.ecoute.confirmer_voix()
            self._attendre_suite(texte)
            return
        if self.ecoute.epellation and brut.strip() and not self.barge and not self._tour.get("alertes"):
            # Réponse à « pouvez-vous épeler ? » : des lettres seules ressemblent à du bruit pour le filtre et le juge.
            # L'IA relit ensuite les lettres, la personne corrige si besoin.
            self.journal.log("épellation", f"« {brut.strip()} » gardé tel quel (lettres)")
            self.ecoute.confirmer_voix()
            await self._accepter(brut.strip())
            return
        if (self.ecoute.epellation or self.relecture) and self.barge and que_des_lettres(brut) and mots_nouveaux(brut, ia) >= 1:
            # Suite d'une épellation après une pause (« MOUH »… « AMED ») arrivée pendant que l'IA relit :
            # le juge y verrait du bruit. Ce ne sont pas les lettres que l'IA vient de lire (écho) : on coupe et on garde.
            self.journal.log("épellation", f"« {brut.strip()} » : suite des lettres pendant que l'IA parle, gardée")
            self.ecoute.confirmer_voix()
            await self._accepter(brut.strip())
            return
        # L'empreinte vocale dit nettement que c'est l'utilisateur : sa phrase n'est jamais jetée comme écho
        # (on retire seulement des morceaux d'écho collés, s'il en reste quelque chose).
        ta_voix = self.locuteur is not None and self.locuteur.pret and self._tour.get("sim", 0.0) >= 0.45
        texte, retirees = retirer_echo(brut, ia, ia_parle=self.ia_parle or self.barge)
        if ta_voix and retirees and not texte:
            texte, retirees = brut.strip(), 0
        if retirees and texte:
            self.journal.log("écho", f"{retirees} phrase(s) de l'IA retirée(s), reste « {texte} »")
        if ta_voix:
            v = classer(texte, "", ia_parle=False)  # pas de test d'écho : c'est ta voix
        elif retirees and not texte:
            v = Verdict("bruit", "écho de la voix de l'IA")
            texte = brut.strip()
        elif (self.ia_parle or self.barge) and texte and len(normaliser(texte).split()) <= 2 and dans_ia(texte, ia):
            # 1-2 mots tous dans la phrase de l'IA (« D'accord. ») pendant qu'elle parle : écho, on ne la coupe pas.
            v = Verdict("bruit", "mots de l'IA pendant qu'elle parle (écho)")
        else:
            v = classer(texte, ia, self.ia_parle)
        if v.genre == "bruit" and texte and self._tour.get("sim", 0.0) >= 0.45 and v.raison in ("mot isolé pendant que l'IA parle", "mots de l'IA pendant qu'elle parle (écho)"):
            # Réponse courte (« oui », « homme ») pendant que l'IA parle, mais l'empreinte dit clairement que c'est toi.
            self.journal.log("gardé", f"« {texte} » : mot court, mais c'est ta voix ({self._tour['sim']:.2f})")
            v = classer(texte, ia, ia_parle=False)
        bruyant = self.ecoute.fond > -40

        if v.genre == "bruit":
            self.journal.log("ignoré", f"« {texte} » → {v.raison}")
            self.journal.ligne("user", texte, ignore=v.raison)
            await self.oublier_tour()
            if self._en_suspens:  # le minuteur de la phrase en attente a été arrêté par ce bruit : on le relance
                self._suspens_timer = self.loop.call_later(1.0, lambda: asyncio.ensure_future(self._suspens_expire()))
            if self.barge:
                self._barge_annule("c'était du bruit")
            return

        if self._en_suspens:
            texte = f"{self._en_suspens} {texte}"
            self._en_suspens = ""

        alertes = self._tour.get("alertes", []) if v.genre != "bruit" else []
        a_juger = v.genre == "doute" or self.barge or (bruyant and v.genre != "finie") or alertes or self._tour.get("reecoute")
        if v.genre == "finie" and not self.barge and not alertes and not self._tour.get("reecoute"):
            a_juger = bruyant  # cas clair : le juge ne vérifie que dans le bruit
        if not a_juger:
            self.ecoute.confirmer_voix()
            await self._accepter(texte)
            return
        if alertes:
            self.journal.log("suspect", " · ".join("autre voix" if "print" in a else "volume faible" for a in alertes))

        if v.genre in ("finie", "doute") and not self.barge:
            # La réponse se prépare PENDANT que le juge réfléchit, mais aucun son ne sort avant son feu vert.
            await self._accepter_sous_reserve(texte, v, alertes)
            return

        # Barge-in, ou phrase qui semble coupée : le juge décide d'abord.
        j, ms = await self.juge.juger(self.contexte_juge, texte, alertes)
        self._log_juge(j, ms)
        if not j["speech"]:
            self.journal.ligne("user", texte, ignore="bruit selon le juge")
            await self.oublier_tour()
            if self.barge:
                self._barge_annule("bruit selon le juge")
            else:
                await self._faire_repeter(texte, self._tour)
            return
        self.ecoute.confirmer_voix()
        if v.genre == "pas_finie" and not self.barge:
            self._attendre_suite(texte)
            return
        await self._accepter(texte)

    @property
    def contexte_juge(self) -> str:
        """Après « Pardon, pouvez-vous répéter ? », le juge doit encore voir la vraie question (« Quel est votre nom ? ») :
        sinon un nom seul (« Diouf ») lui semble hors de propos → bruit → « Pardon… » en boucle."""
        if self.ia_texte in PHRASES_FIXES and self._question_ia:
            return f"{self._question_ia} {self.ia_texte}"
        return self.ia_texte

    def _log_juge(self, j: dict, ms: float, extra: str = "") -> None:
        self.journal.log("juge", f"{'parole' if j['speech'] else 'BRUIT'} · {'finie' if j['finished'] else 'pas finie'} ({ms:.0f} ms){extra}{' · ' + j['erreur'] if 'erreur' in j else ''}")

    def _attendre_suite(self, texte: str) -> None:
        """« I went to the… » : on attend la suite un instant."""
        self._en_suspens = texte
        self.journal.log("attente", f"« {texte} » semble coupée, j'attends la suite")
        self._suspens_timer = self.loop.call_later(1.5, lambda: asyncio.ensure_future(self._suspens_expire()))

    async def _accepter_sous_reserve(self, texte: str, v: Verdict, alertes: list[str]) -> None:
        juge = asyncio.create_task(self.juge.juger(self.contexte_juge, texte, alertes))
        if self.ia_parle:
            await self._couper_ia()
        lecteur = self.audio.lecteur
        lecteur.bloquer(True)
        tour = self._tour
        await self._lancer_reponse(texte)
        tache = self._tache_reponse
        try:
            j, ms = await juge
        except Exception as e:
            j, ms = {"speech": True, "finished": True, "erreur": str(e)[:80]}, 0.0
        pret = not lecteur.vide
        self._log_juge(j, ms, " · réponse déjà prête, elle attendait" if pret else " · avant le 1er son")
        # « Pas finie » selon le juge : on attend la suite, sauf si Smart Turn (l'intonation) est sûr que c'est fini
        # (le texte de Deepgram oublie souvent le « ? » d'une question).
        pas_finie = v.genre == "doute" and not j["finished"] and tour.get("smart_turn", -1.0) < 0.9
        refus = not j["speech"] or pas_finie
        if refus:
            # Jetée sans qu'aucun son ne soit sorti.
            if tache is self._tache_reponse:
                await self._annuler_en_silence()
            lecteur.bloquer(False)
            if not j["speech"]:
                self.journal.ligne("user", texte, ignore="bruit selon le juge")
                await self.oublier_tour(deja_repondu=True)
                await self._faire_repeter(texte, tour)
            else:
                self.ecoute.confirmer_voix()
                await self.oublier_tour(deja_repondu=True)
                self._attendre_suite(texte)
            return
        lecteur.bloquer(False)
        self._tour = tour
        self.ecoute.confirmer_voix()
        self._apprendre_voix()
        self.journal.log("retenu", f"« {texte} »")
        self.journal.ligne("user", texte)

    async def _faire_repeter(self, texte: str, tour: dict) -> None:
        """Le juge a dit « bruit » (ou rien n'a été transcrit) alors que l'IA attendait une réponse : au téléphone
        (pas d'écho possible), l'IA se taisait. Plutôt que le silence : « Pardon… »."""
        if self.cfg.audio != "twilio" or tour.get("ia_parlait") or self.ia_parle:
            return
        # Moins de 3 mots (« Diouf » → « Youhou », « Bioof ») : au moins 0,3 s de vraie parole, ou ta voix reconnue.
        # (Sur un mot si court l'empreinte se trompe souvent : « autre voix » ne bloque pas. Au pire, un bruit
        # fait dire « Pardon, pouvez-vous répéter ? », toujours mieux que le silence après une question.)
        if len(normaliser(texte).split()) < 3 and tour.get("parole_ms", 0.0) < 300 and tour.get("sim", 0.0) < 0.45:
            return
        self.journal.log("pas compris", f"« {texte} » : sûrement toi, mal transcrit → je fais répéter")
        self.phrase_fixe = REPETER
        await self._lancer_reponse(texte)

    async def _annuler_en_silence(self) -> None:
        """La réponse préparée est jetée : rien n'a été joué, rien n'est gardé."""
        self._annule = True
        try:
            await self.arreter_reponse()
        finally:
            self._annule = False
        if self._tache_reponse:
            self._tache_reponse.cancel()
        self.audio.lecteur.couper()
        self.repond = False

    async def _suspens_expire(self) -> None:
        if self._en_suspens and self.ecoute.etat == "repos":
            t, self._en_suspens = self._en_suspens, ""
            await self._accepter(t)

    def _apprendre_voix(self) -> None:
        """Phrase acceptée : on affine l'empreinte de l'utilisateur, seulement si c'est sûr
        (l'IA ne parlait pas — pas d'écho possible — et la voix ressemble déjà bien, une fois l'empreinte prête)."""
        t, self._tour = self._tour, {}
        e = t.get("empreinte")
        if self.locuteur is None or e is None or t.get("ia_parlait") or t.get("alertes") or t.get("reecoute"):
            return
        if self.locuteur.pret and t.get("sim", 0.0) < 0.45:
            return
        pret = self.locuteur.pret
        self.locuteur.apprendre(e, t["secondes"])
        if self.locuteur.pret and not pret:
            self.journal.log("ta voix", f"empreinte prête ({self.locuteur.n} phrases, {self.locuteur.secondes:.1f} s)")

    async def _accepter(self, texte: str) -> None:
        self._apprendre_voix()
        if self.ia_parle:
            await self._couper_ia()
        self.journal.log("retenu", f"« {texte} »")
        self.journal.ligne("user", texte)
        await self._lancer_reponse(texte)

    async def _lancer_reponse(self, texte: str) -> None:
        self.repond = True
        self.ecoute.ia_parle = True
        self.audio.lecteur.nouvelle_reponse()
        self._tache_reponse = asyncio.create_task(self._reponse(texte))

    async def _reponse(self, texte: str) -> None:
        try:
            await self.repondre(texte)
            # On attend la fin de la lecture.
            while not self.audio.lecteur.vide:
                await asyncio.sleep(0.05)
            if self.raccrocher:
                self.journal.log("fin", "l'IA a dit au revoir → on raccroche")
                await asyncio.sleep(0.5)
                self._fin.set()
                return
            asyncio.create_task(self._calibrer())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.journal.log("erreur", f"réponse : {e!r}")
        finally:
            self.repond = False
            if not texte:
                self.accueil = False

    async def _calibrer(self) -> None:
        """Après chaque phrase de l'IA (dès l'accueil) : mesure le retard de son écho et règle l'anti-écho.
        Le retard change d'un appel à l'autre (tampons audio) : on le remesure à chaque fois."""
        if self.audio.echo.apm is None:
            return  # pas d'anti-écho chez nous (fichier, appel téléphonique)
        await asyncio.sleep(0.8)  # le temps que la fin de l'écho arrive dans le micro
        r = await asyncio.to_thread(self.audio.mesurer_retard)
        if r is None:
            return
        ms, score, net = r
        ancien = self.audio.echo.retard_ms
        if score >= 0.2 and net >= 0.1:
            # Marge de 50 ms : la référence doit arriver un peu AVANT l'écho (l'anti-écho rattrape le reste).
            nouveau = max(0.0, ms - 50)
            if self._calibre:
                nouveau = 0.5 * ancien + 0.5 * nouveau if abs(nouveau - ancien) < 80 else nouveau
            self._calibre = True
            self.audio.echo.retard_ms = nouveau
            self.journal.log("anti-écho", f"écho mesuré à {ms:.0f} ms (ressemblance {score:.2f}, pic {net:.2f}) → retard {nouveau:.0f} ms")
        else:
            self.journal.log("anti-écho", f"pas d'écho net (ressemblance {score:.2f}, pic {net:.2f}), retard gardé à {ancien:.0f} ms")

    def texte_ia_courant(self) -> str:
        """Ce que l'IA est en train de dire (pour reconnaître son écho avant la fin de sa phrase)."""
        return ""

    @property
    def texte_ia_echo(self) -> str:
        return f"{self.ia_texte} {self.texte_ia_courant()}".strip()

    async def _couper_ia(self) -> None:
        """Barge-in confirmé (ou nouvelle phrase) : l'IA s'arrête et on garde ce qui a été entendu."""
        if self._barge_timer:
            self._barge_timer.cancel()
        self.barge = False
        if not self.ia_parle:
            self.audio.lecteur.volume(1.0)
            return
        entendu = await self.arreter_reponse()
        if self._tache_reponse:
            self._tache_reponse.cancel()
        self.audio.lecteur.couper()
        self.audio.lecteur.volume(1.0)
        self.repond = False
        self.journal.log("coupure", f"l'IA s'arrête ; entendu par l'utilisateur : « {entendu} »")
        self.journal.ligne("assistant", entendu + " …", coupe=True)

    def _barge_annule(self, raison: str) -> None:
        if not self.barge:
            return
        self.barge = False
        if self._barge_timer:
            self._barge_timer.cancel()
        self.audio.lecteur.volume(1.0)
        self.journal.log("barge-in", f"annulé ({raison}) → le son remonte, l'IA continue")

    def ia_a_dit(self, texte: str) -> None:
        """À appeler par le programme quand la réponse complète est connue."""
        self.ia_texte = texte
        if texte not in PHRASES_FIXES:
            self._question_ia = texte
        self.journal.log("IA", f"« {texte} »")
        # L'IA demande d'épeler : le tour suivant attend toutes les lettres (voir Ecoute.epellation).
        if texte != REPETER and texte not in RELANCES:  # « Pardon… » pendant une épellation : on attend toujours des lettres
            self.ecoute.epellation = demande_epeler(texte)
            self.relecture = relit_lettres(texte)
            if self.ecoute.epellation:
                self.journal.log("épellation", "j'attends toutes les lettres avant de répondre")
        self.journal.ligne("assistant", texte)
