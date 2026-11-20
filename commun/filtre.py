"""
Filtre du texte transcrit — mêmes règles que l'app (app/src/lib/turnFilter.ts).

  bruit       texte vide, « you », « Thank you », écho de l'IA, mot isolé pendant que l'IA parle
  finie       phrase claire et terminée
  pas_finie   phrase qui s'arrête sur « the », « to », « and »…
  doute       le juge doit trancher
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HALLUCINATIONS = {
    "you", "thank you", "thanks", "thank you very much", "thanks for watching", "thank you for watching", "bye", "bye bye",
    "hmm", "hm", "mm", "mmm", "uh", "um", "ah", "oh", "huh", "so", "okay", "the", "a", "i", "and", "music", "applause",
    "laughter", "silence", "subtitles by the amara org community", "please subscribe", "",
    # Français
    "merci", "merci beaucoup", "sous titres réalisés par la communauté d amara org", "euh", "bah", "ben",
}
COURT_OK = {
    "yes", "no", "yeah", "yep", "nope", "sure", "maybe", "sorry", "what", "pardon", "hello", "hi", "really", "right", "exactly",
    "of course", "not really", "i dont know", "okay", "ok", "thank you", "thanks", "stop", "wait", "hey",
    "oui", "non", "ouais", "merci", "bonjour", "salut", "quoi", "attends", "stop", "daccord", "ok", "peut être",
}
SUSPENDUS = {
    "and", "but", "or", "so", "because", "the", "a", "an", "to", "of", "in", "on", "at", "with", "for", "from", "my", "your",
    "his", "her", "their", "our", "is", "are", "was", "were", "i", "we", "you", "he", "she", "they", "it", "that", "which",
    "who", "when", "if", "about", "like", "very", "really", "then", "um", "uh", "euh",
    "et", "mais", "ou", "donc", "parce", "que", "qui", "le", "la", "les", "un", "une", "des", "de", "du", "à", "au", "en",
    "dans", "sur", "avec", "pour", "mon", "ma", "mes", "ton", "ta", "je", "tu", "il", "elle", "on", "nous", "vous", "est",
}
LETTRES = re.compile(r"[a-zA-Zàâçéèêëîïôûùüÿœ]")


def normaliser(t: str) -> str:
    t = t.lower().replace("’", "").replace("'", "")
    t = re.sub(r"[^a-z0-9àâçéèêëîïôûùüÿœ\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def recouvrement(a: str, b: str) -> float:
    """Part des mots de a présents dans b."""
    wa = [w for w in a.split(" ") if w]
    if not wa:
        return 0.0
    wb = set(b.split(" "))
    return sum(1 for w in wa if w in wb) / len(wa)


def couverture(n: str, ia: str, k: int = 3) -> float:
    """Part des mots de n couverts par des suites de k mots consécutifs que l'IA a dites DANS LE MÊME ORDRE.
    « je suis d'accord » n'est pas un écho de « Je suis l'assistant… Êtes-vous d'accord ? » (mêmes mots, pas la même suite)."""
    w = [x for x in n.split(" ") if x]
    if not w:
        return 0.0
    k = min(k, len(w))
    cible = f" {ia} "
    couvert = [False] * len(w)
    for i in range(len(w) - k + 1):
        if f" {' '.join(w[i:i + k])} " in cible:
            for j in range(i, i + k):
                couvert[j] = True
    return sum(couvert) / len(w)


def dans_ia(texte: str, texte_ia: str) -> bool:
    """Le texte (court) est-il une suite de mots que l'IA a dite telle quelle ?"""
    n = normaliser(texte)
    return bool(n) and f" {n} " in f" {normaliser(texte_ia)} "


def mots_nouveaux(texte: str, texte_ia: str) -> int:
    """Nombre de mots de texte que l'IA n'a pas dits."""
    ia = set(normaliser(texte_ia).split())
    return sum(1 for w in normaliser(texte).split() if w not in ia)


def retirer_echo(brut: str, texte_ia: str, ia_parle: bool = False) -> tuple[str, int]:
    """Retire les phrases qui viennent de la voix de l'IA (écho collé). Renvoie (reste, nb retirées).

    - phrase de 3 mots ou plus reprenant des suites de mots de l'IA dans le même ordre (≥ 75 %) → écho ;
    - pendant que l'IA parle, 2 mots qu'elle vient de dire à la suite
      (« Merci Mohamed. ») → écho aussi. Un seul mot (« Seul. ») est gardé : ça peut être une réponse.
    """
    ia = normaliser(texte_ia)
    if not ia:
        return brut.strip(), 0

    def echo(p: str) -> bool:
        n = normaliser(p)
        mots = n.split(" ") if n else []
        if len(mots) >= 3 and couverture(n, ia) >= 0.75:
            return True
        return ia_parle and len(mots) == 2 and couverture(n, ia, 2) == 1.0

    phrases = re.split(r"(?<=[.?!,])\s+", brut.strip())
    gardees = [p for p in phrases if not echo(p)]
    retirees = len(phrases) - len(gardees)
    reste = " ".join(gardees).strip()
    if ia_parle and reste:
        # Bout de phrase de l'IA collé au début ou à la fin, sans ponctuation :
        # « Est-ce que j'ai des Je comprends Mohamed. » → « Est-ce que j'ai des »
        debuts = [normaliser(p) for p in re.split(r"(?<=[.?!])\s+", texte_ia) if normaliser(p)]
        coupe = _couper_bouts(reste, debuts)
        if coupe != reste:
            reste, retirees = coupe, retirees + 1
    return reste, retirees


def _couper_bouts(texte: str, phrases_ia: list[str]) -> str:
    """Retire, au début et à la fin, une suite d'au moins 2 mots qui reprend le DÉBUT d'une phrase de l'IA
    (c'est ce que le micro entend quand l'IA commence à parler). « seul en ce moment » au milieu
    d'une question de l'IA n'est donc jamais retiré d'une réponse de l'utilisateur."""
    mots = texte.split()
    norm = [normaliser(m) for m in mots]

    def dans_ia(i: int, j: int) -> bool:
        bout = " ".join(w for w in norm[i:j] if w)
        return len(bout.split()) >= 2 and any(f"{p} ".startswith(bout + " ") for p in phrases_ia)

    fin = len(mots)
    for i in range(0, len(mots) - 1):
        if dans_ia(i, len(mots)):
            fin = i
            break
    debut = 0
    for j in range(fin, 1, -1):
        if dans_ia(0, j):
            debut = j
            break
    return " ".join(mots[debut:fin]).strip()


@dataclass
class Verdict:
    genre: str  # bruit | finie | pas_finie | doute
    raison: str = ""


def classer(brut: str, texte_ia: str, ia_parle: bool) -> Verdict:
    texte = brut.strip()
    norm = normaliser(texte)
    mots = norm.split(" ") if norm else []
    if not mots or not LETTRES.search(texte):
        return Verdict("bruit", "texte vide")
    if norm in HALLUCINATIONS and norm not in COURT_OK:
        return Verdict("bruit", "texte typique du bruit")
    ia = normaliser(texte_ia)
    if ia and len(mots) >= 3 and couverture(norm, ia) > 0.6:
        return Verdict("bruit", "écho de la voix de l'IA")
    if len(mots) == 1 and norm not in COURT_OK and ia_parle:
        return Verdict("bruit", "mot isolé pendant que l'IA parle")
    dernier = mots[-1]
    question = texte.rstrip().endswith(("?", "!"))  # « What about you? » est finie
    if len(mots) >= 2 and dernier in SUSPENDUS and norm not in COURT_OK and not question:
        return Verdict("pas_finie")
    finie = len(mots) >= 2 and (question or (bool(re.search(r"[.?!]$", texte)) and not texte.endswith("...") and dernier not in SUSPENDUS))
    return Verdict("finie" if finie or norm in COURT_OK else "doute")
