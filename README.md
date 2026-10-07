# Miki — l'assistante vocale qui répond à chaque appel du 115

> Aujourd'hui, **seuls 11 % des appels au 115 sont traités**.
> Miki décroche tous les autres, recueille la situation de chaque appelant et la transmet aux écoutants avec un score de priorité.

<!-- TODO : citer la source des chiffres (11 %, 2 h d'attente) -->

## Le problème

Au 115, le numéro d'urgence sociale pour les personnes sans abri, il y a bien trop peu de places d'hébergement et d'écoutants face au nombre d'appels. Les écoutants doivent donc filtrer les appels pour faire passer les situations prioritaires en premier.

Mais même les personnes prioritaires ne sont, pour la plupart, jamais prises en charge :

- **89 % des appels ne sont jamais traités**, y compris ceux de femmes enceintes, de personnes handicapées ou de familles avec enfants.
- Pour les 11 % qui ont la chance d'avoir quelqu'un au téléphone, **l'attente moyenne atteint 2 heures**, et la plupart ne seront pas jugés prioritaires.
- Des heures d'attente, donc, pour une réponse qui est souvent négative.
- Comme la majorité des appels ne sont jamais décrochés, **les statistiques sur les appelants ne sont pas fiables**. Or la FAS et la DIHAL en ont besoin pour piloter l'hébergement d'urgence et justifier les moyens.

## La solution : Miki

Miki est une assistante vocale à intelligence artificielle qui prend en charge les appelants pendant leur attente.

- **Elle répond à tous les appels, en simultané.** Personne ne reste sans réponse.
- **Elle écoute et pose des questions simples**, une à la fois, avec douceur : identité, situation, temps passé à la rue, localisation et cas particuliers (grossesse, handicap, santé, enfants, animal).
- **Elle fait valider les informations** en les relisant à la personne.
- **Elle crée automatiquement un dossier**, accompagné d'un **score de priorité**, pour que les situations les plus urgentes apparaissent en premier aux écoutants.

### Le score de priorité

Le score est calculé par une grille fixe, et non par l'IA : l'IA extrait les faits, la grille décide. Le score est donc transparent, reproductible et vérifiable.

| Score | Niveau | Critères |
|---|---|---|
| 5 | Vitale | Danger vital, violences, mineur seul |
| 4 | Très haute | Enfants présents, grossesse, problème de santé |
| 3 | Haute | 65 ans et plus, handicap, première nuit à la rue |
| 2 | Moyenne | Sans solution pour ce soir |
| 1 | Basse | Aucun de ces critères |

Si la personne évoque un danger vital (malaise, blessure grave, idées suicidaires, violence en cours), Miki l'oriente immédiatement vers le 15 ou le 112.

## Ce que ça change

- **Pour les appelants** : chacun obtient un dossier, sans passer des heures au téléphone.
- **Pour les écoutants** : les dossiers arrivent déjà triés par priorité, ce qui permet de traiter les urgences en premier.
- **Pour la FAS et la DIHAL** : des statistiques sur l'ensemble des appelants, et pas seulement sur ceux qui ont été décrochés. C'est une source précieuse pour piloter l'hébergement d'urgence et justifier les moyens.

## Où en est le projet

### La vision

Miki décroche chaque appel du 115, sans attente et en parallèle. Chaque appelant repart avec un dossier créé, les écoutants traitent les dossiers par ordre de priorité, et les institutions disposent enfin de chiffres fiables.

### Ce qui fonctionne aujourd'hui (prototype)

- Une conversation vocale en français, en temps réel, testée depuis l'ordinateur (micro et haut-parleur).
- Un déroulé d'appel complet : accueil, écoute, accord de la personne, questions, relecture et validation.
- Une fiche structurée remplie automatiquement au fil de la conversation.
- Le calcul du score de priorité et la redirection vers le 15 ou le 112 en cas de danger vital.
- La mesure de la latence de chaque échange et l'enregistrement de chaque appel en local.

### Ce qui reste à construire

- Le raccordement à la téléphonie (SIP) pour recevoir de vrais appels, plusieurs en même temps.
- L'interface des écoutants, avec la file des dossiers triés par priorité.
- Un stockage sécurisé des dossiers (voir la section RGPD).
- Des tableaux de statistiques anonymisées pour la FAS et la DIHAL.
- Des tests en conditions réelles avec des écoutants du 115.

## Données personnelles et RGPD

Miki recueille des données sensibles au sens du RGPD (article 9), notamment de santé, de grossesse et de handicap. Le projet est conçu pour les traiter avec précaution :

- **Transparence** : Miki annonce dès le début qu'elle est une intelligence artificielle, et elle demande l'accord de la personne avant de poser ses questions.
- **Minimisation** : seules les informations utiles à la prise en charge sont demandées, et la personne peut refuser de répondre à n'importe quelle question.
- **Statistiques anonymisées** : les données transmises aux institutions sont agrégées et ne permettent pas d'identifier les personnes.

Avant une mise en production, il faudra :

- héberger les données chez un hébergeur certifié HDS (hébergeur de données de santé) ;
- utiliser des fournisseurs d'IA hébergés en Europe, ou des modèles hébergés en interne ;
- fixer une durée de conservation des dossiers ;
- réaliser une analyse d'impact (AIPD) avec le délégué à la protection des données de l'opérateur du 115.

## Fonctionnement technique

Miki est construite sur [LiveKit Agents](https://github.com/livekit/agents) :

```
Appelant (voix)
     │
     ▼
Deepgram ─────────► transcription de la voix
     │
     ▼
Parleur (Groq) ───► réponse de Miki, courte et orale
     ▲
     │ consigne
Penseur (Groq / Gemini) ► fiche structurée + phase de l'appel
     │
     ├──► grille de priorité ──► score de 1 à 5
     │
     ▼
ElevenLabs ───────► voix de Miki (ou Cartesia via TTS_PROVIDER=cartesia)
```

- **Le parleur** répond à l'appelant rapidement, en phrases courtes adaptées à l'oral.
- **Le penseur** analyse toute la conversation en parallèle : il remplit la fiche, repère les informations manquantes et donne au parleur la consigne pour son prochain tour.

| Fichier | Rôle |
|---|---|
| `agent.py` | L'agent vocal : pipeline, penseur, score de priorité, enregistrement des appels |
| `prompts.py` | Les instructions de Miki (parleur) et du penseur, et le message d'accueil |

## Installation et lancement

Prérequis : Python 3 et des clés API Deepgram, Groq, ElevenLabs (et éventuellement Google pour Gemini).

```bash
make install   # crée le venv et installe les dépendances
make env       # crée .env, puis remplir les clés
make console   # parler à Miki depuis le terminal
```

Les transcriptions, fiches et mesures de latence de chaque appel sont enregistrées dans `sessions/`, qui n'est pas versionné.
