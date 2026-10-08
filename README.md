# Miki — l'assistante vocale qui répond à chaque appel du 115

> Aujourd'hui, **seuls 11 % des appels au 115 sont traités**.
> Miki décroche tous les autres, recueille la situation de chaque appelant et la transmet aux écoutants avec un score de priorité.
> Et parce qu'elle répond à tout le monde, elle donne enfin une image fiable de qui appelle le 115.

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
- **Pour la FAS et la DIHAL** : des statistiques sur l'ensemble des appelants, et pas seulement sur ceux qui ont été décrochés (voir ci-dessous).

## Des statistiques enfin fiables

C'est l'autre apport majeur de Miki.

### Aujourd'hui : on ne connaît qu'une petite partie des appelants

Les statistiques du 115 reposent sur les appels décrochés. Or 89 % des appels ne le sont jamais : on ne sait pas qui sont ces personnes, où elles se trouvent ni ce dont elles ont besoin. La demande réelle d'hébergement d'urgence est donc largement invisible, et les chiffres utilisés pour piloter le dispositif ne reflètent qu'une petite partie de la réalité.

### Avec Miki : chaque appel devient une donnée

Comme Miki répond à tous les appels, chacun produit une fiche structurée, toujours au même format. Agrégées et anonymisées, ces fiches permettent de mesurer :

- **le volume réel de la demande**, y compris celle qui n'aboutit à aucune prise en charge ;
- **le profil des appelants** : âge, sexe, personnes seules ou familles, nombre et âge des enfants ;
- **les publics vulnérables** : part de femmes enceintes, de personnes handicapées, malades, âgées de 65 ans et plus, ou de mineurs seuls ;
- **l'ancienneté à la rue**, et notamment le nombre de personnes qui y passent leur première nuit ;
- **la géographie des besoins** : où se trouvent les personnes qui appellent, ville par ville et quartier par quartier ;
- **la répartition des niveaux de priorité**, pour savoir combien de situations urgentes restent sans solution ;
- **l'évolution dans le temps** : par heure, par jour, par saison, par exemple lors d'une vague de froid.

### À quoi ça sert

Pour la FAS, la DIHAL et les SIAO, ces données sont une mine d'or :

- **piloter l'hébergement d'urgence** : ouvrir des places là où la demande est la plus forte, anticiper les pics ;
- **adapter l'offre aux publics** : places pour familles, pour femmes enceintes, accessibles aux personnes handicapées, acceptant les animaux ;
- **justifier les moyens** auprès des pouvoirs publics avec des chiffres qui couvrent l'ensemble de la demande, et non une fraction.

Un point de vigilance : une même personne peut appeler plusieurs fois. Pour compter des personnes et pas seulement des appels, il faudra rapprocher les appels d'une même personne, tout en respectant le RGPD.

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
- L'agrégation des fiches en statistiques anonymisées, avec un tableau de bord pour la FAS et la DIHAL.
- Le rapprochement des appels d'une même personne, pour compter des personnes et pas seulement des appels.
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

Miki est un agent vocal construit sur [LiveKit Agents](https://github.com/livekit/agents), un framework open source pour les agents vocaux en temps réel. Le défi principal est la **latence** : pour qu'une conversation paraisse naturelle, Miki doit répondre en moins d'une seconde environ. L'architecture est donc pensée pour que rien de lent ne se trouve dans le chemin de la réponse.

### Le pipeline

```
                  Appelant (voix)
                        │
                        ▼
      Silero VAD + détecteur de fin de tour
                        │
                        ▼
      Deepgram Nova-3 ──────► transcription (français)
                        │
          ┌─────────────┴──────────────┐
          ▼                            ▼
   PARLEUR (Groq)               PENSEUR (Groq / Gemini)
   réponse rapide,              en parallèle : fiche,
   courte et orale    ◄──────   phase de l'appel, consigne
          │          consigne          │
          │                            ▼
          │                  grille de priorité (1 à 5)
          ▼
   ElevenLabs Flash v2.5 ──► voix de Miki
```

### Les briques

| Étape | Technologie | Rôle |
|---|---|---|
| Détection de la voix | **Silero VAD** | Repère quand la personne parle ou se tait |
| Fin de tour | **Détecteur de fin de tour LiveKit** | Devine si la phrase est terminée ; Miki attend jusqu'à 3 s si la personne semble chercher ses mots |
| Transcription | **Deepgram Nova-3** (français) | Transforme la voix en texte, en streaming |
| Parleur | **Groq** (Qwen, ou GPT-OSS) | Génère la réponse de Miki très rapidement, sans raisonnement long |
| Penseur | **GPT-OSS 120B sur Groq**, avec repli possible sur **Gemini** | Analyse toute la conversation, remplit la fiche et guide le parleur |
| Synthèse vocale | **ElevenLabs Flash v2.5** | Donne sa voix à Miki, en français, avec un débit légèrement ralenti (0,9) pour être bien comprise |
| Synthèse alternative | **Cartesia Sonic-3** | Autre voix possible, via `TTS_PROVIDER=cartesia` |

### Deux cerveaux : le parleur et le penseur

Un seul modèle ne peut pas être à la fois très rapide et très rigoureux. Miki en utilise donc deux :

- **Le parleur** est un modèle rapide qui répond à chaque tour de parole. Il suit les instructions de `prompts.py` : phrases courtes, une seule question à la fois, vouvoiement, empathie.
- **Le penseur** est un modèle plus puissant qui tourne en parallèle, sans jamais bloquer la conversation. Après chaque intervention de l'appelant, il relit toute la transcription et produit un JSON structuré : la fiche de l'appelant, les informations manquantes, la phase de l'appel (écoute, collecte, vérification, accompagnement) et une consigne pour le prochain tour du parleur.

Le parleur reçoit à chaque tour la fiche à jour et la consigne du penseur. Il ne redemande donc jamais une information déjà donnée, même si la personne l'a dite dans le désordre.

Si le penseur détecte un **danger vital**, il interrompt le déroulé et fait immédiatement orienter la personne vers le 15 ou le 112.

### Fiabilité

- **Score de priorité déterministe** : le penseur extrait seulement des critères factuels (vrai ou faux) ; le score est calculé par le code, à partir d'une grille fixe. Le résultat est reproductible et vérifiable.
- **Repli entre modèles** : le penseur peut essayer plusieurs modèles dans l'ordre (`THINKER_MODELS`) si l'un est saturé ou hors quota.
- **Analyse finale** : à la fin de l'appel, le penseur refait une dernière analyse pour intégrer les derniers échanges.
- **Mesure de latence** : chaque échange est chronométré, étape par étape (fin de tour, transcription, parleur, synthèse vocale), avec un objectif de 600 ms. Un résumé (médiane et P95) est produit à la fin de chaque appel.

### Ce que produit chaque appel

À la fin de l'appel, deux fichiers sont écrits dans `sessions/` :

- `…-appel.json` : la fiche complète (identité, situation, localisation, cas particuliers, critères, score de priorité) et la transcription ;
- `…-latence.csv` : les mesures de latence de chaque échange.

C'est cette fiche, toujours au même format, qui alimentera l'interface des écoutants et les statistiques.

### Les fichiers

| Fichier | Rôle |
|---|---|
| `agent.py` | L'agent vocal : pipeline, penseur, score de priorité, mesure de latence, enregistrement des appels |
| `prompts.py` | Les instructions du parleur et du penseur, et le message d'accueil |
| `Makefile` | Installation et lancement |
| `.env.example` | La liste des clés API et des réglages (modèles, voix, débit) |

## Installation et lancement

Prérequis : Python 3 et des clés API Deepgram, Groq, ElevenLabs (et éventuellement Google pour Gemini).

```bash
make install   # crée le venv et installe les dépendances
make env       # crée .env, puis remplir les clés
make console   # parler à Miki depuis le terminal
```

Les transcriptions, fiches et mesures de latence de chaque appel sont enregistrées dans `sessions/`, qui n'est pas versionné.

---

# Miki — The voice assistant that answers every 115 call

> Today, **only 11% of calls to 115 are handled**.
> Miki picks up all the others, gathers each caller's situation, and forwards it to call handlers with a priority score.
> And because she answers everyone, she finally provides a reliable picture of who calls 115.

<!-- TODO: cite the source for these figures (11%, 2-hour wait) -->

## The problem

At 115, the emergency social number for homeless people, there are far too few shelter beds and call handlers compared with call volume. Call handlers therefore have to filter calls to prioritize the most urgent situations.

But even priority callers are, for the most part, never supported:

- **89% of calls are never handled**, including those from pregnant women, people with disabilities, or families with children.
- For the 11% who are lucky enough to reach someone, **the average wait reaches 2 hours**, and most will not be considered priority.
- Hours of waiting, then, for a response that is often negative.
- Because most calls are never answered, **statistics on callers are unreliable**. Yet FAS and DIHAL need them to steer emergency accommodation and justify resources.

## The solution: Miki

Miki is an AI voice assistant that supports callers while they wait.

- **She answers all calls simultaneously.** No one is left without a response.
- **She listens and asks simple questions**, one at a time, gently: identity, situation, time spent on the street, location, and special cases (pregnancy, disability, health, children, pet).
- **She has the information validated** by reading it back to the person.
- **She automatically creates a file**, with a **priority score**, so the most urgent situations appear first for call handlers.

### Priority score

The score is calculated by a fixed rubric, not by AI: the AI extracts facts, the rubric decides. The score is therefore transparent, reproducible, and auditable.

| Score | Level | Criteria |
|---|---|---|
| 5 | Life-threatening | Life-threatening danger, violence, unaccompanied minor |
| 4 | Very high | Children present, pregnancy, health problem |
| 3 | High | 65 and over, disability, first night on the street |
| 2 | Medium | No solution for tonight |
| 1 | Low | None of these criteria |

If the person mentions life-threatening danger (malaise, serious injury, suicidal thoughts, ongoing violence), Miki immediately directs them to 15 or 112.

## What it changes

- **For callers**: everyone gets a file, without spending hours on the phone.
- **For call handlers**: files arrive already sorted by priority, making it possible to handle emergencies first.
- **For FAS and DIHAL**: statistics on all callers, not just those who were answered (see below).

## Finally reliable statistics

This is Miki's other major contribution.

### Today: we only know a small portion of callers

115 statistics are based on answered calls. But 89% of calls are never answered: we do not know who these people are, where they are, or what they need. The real demand for emergency accommodation is therefore largely invisible, and the figures used to steer the system reflect only a small part of reality.

### With Miki: every call becomes data

Because Miki answers all calls, each one produces a structured record, always in the same format. Aggregated and anonymized, these records make it possible to measure:

- **the real volume of demand**, including demand that does not result in any support;
- **the profile of callers**: age, sex, single people or families, number and age of children;
- **vulnerable groups**: share of pregnant women, people with disabilities, sick people, people aged 65 and over, or unaccompanied minors;
- **how long people have been on the street**, including the number of people spending their first night there;
- **the geography of needs**: where the people calling are located, city by city and neighborhood by neighborhood;
- **the distribution of priority levels**, to know how many urgent situations remain without a solution;
- **changes over time**: by hour, day, season, for example during a cold snap.

### What it is for

For FAS, DIHAL, and SIAOs, this data is a goldmine:

- **steering emergency accommodation**: opening beds where demand is highest, anticipating peaks;
- **adapting supply to populations**: beds for families, pregnant women, accessible to people with disabilities, accepting pets;
- **justifying resources** to public authorities with figures that cover all demand, not just a fraction.

One point of vigilance: the same person may call several times. To count people and not just calls, calls from the same person will need to be matched, while complying with GDPR.

## Where the project stands

### The vision

Miki answers every 115 call, without waiting and in parallel. Every caller leaves with a created file, call handlers process files in order of priority, and institutions finally have reliable figures.

### What works today (prototype)

- A real-time voice conversation in French, tested from a computer (microphone and speaker).
- A complete call flow: greeting, listening, consent from the person, questions, read-back, and validation.
- A structured record filled in automatically as the conversation progresses.
- Priority score calculation and redirection to 15 or 112 in case of life-threatening danger.
- Measurement of latency for each exchange and recording of each call locally.

### What remains to be built

- Telephony integration (SIP) to receive real calls, several at the same time.
- The call handler interface, with the queue of files sorted by priority.
- Secure storage of files (see the GDPR section).
- Aggregation of records into anonymized statistics, with a dashboard for FAS and DIHAL.
- Matching calls from the same person, to count people and not just calls.
- Real-world tests with 115 call handlers.

## Personal data and GDPR

Miki collects sensitive data within the meaning of the GDPR (Article 9), including health, pregnancy, and disability data. The project is designed to handle it carefully:

- **Transparency**: Miki announces from the start that she is an artificial intelligence, and asks for the person's consent before asking questions.
- **Minimization**: only information useful for support is requested, and the person may refuse to answer any question.
- **Anonymized statistics**: data transmitted to institutions is aggregated and does not allow people to be identified.

Before production, it will be necessary to:

- host data with an HDS-certified provider (health data hosting provider);
- use AI providers hosted in Europe, or models hosted internally;
- set a retention period for files;
- carry out a data protection impact assessment (DPIA) with the data protection officer of the 115 operator.

## Technical operation

Miki is a voice agent built on [LiveKit Agents](https://github.com/livekit/agents), an open-source framework for real-time voice agents. The main challenge is **latency**: for a conversation to feel natural, Miki must respond in under about one second. The architecture is therefore designed so that nothing slow is in the response path.

### The pipeline

```
                  Caller (voice)
                        │
                        ▼
      Silero VAD + turn detector
                        │
                        ▼
      Deepgram Nova-3 ──────► transcription (French)
                        │
          ┌─────────────┴──────────────┐
          ▼                            ▼
   TALKER (Groq)                THINKER (Groq / Gemini)
   fast, short,                 in parallel: record,
   spoken reply      ◄──────   call phase, instruction
          │          instruction       │
          │                            ▼
          │                  priority rubric (1 to 5)
          ▼
   ElevenLabs Flash v2.5 ──► Miki's voice
```

### The building blocks

| Step | Technology | Role |
|---|---|---|
| Voice detection | **Silero VAD** | Detects when the person is speaking or silent |
| Turn end | **LiveKit turn detector** | Guesses whether the sentence is finished; Miki waits up to 3 s if the person seems to be searching for words |
| Transcription | **Deepgram Nova-3** (French) | Converts voice to text, in streaming |
| Talker | **Groq** (Qwen, or GPT-OSS) | Generates Miki's reply very quickly, without long reasoning |
| Thinker | **GPT-OSS 120B on Groq**, with possible fallback to **Gemini** | Analyzes the whole conversation, fills the record, and guides the talker |
| Speech synthesis | **ElevenLabs Flash v2.5** | Gives Miki her voice, in French, with a slightly slowed rate (0.9) so she is easy to understand |
| Alternative synthesis | **Cartesia Sonic-3** | Another possible voice, via `TTS_PROVIDER=cartesia` |

### Two brains: the talker and the thinker

A single model cannot be both very fast and very rigorous. Miki therefore uses two:

- **The talker** is a fast model that responds at each turn. It follows the instructions in `prompts.py`: short sentences, one question at a time, formal "vous" form, empathy.
- **The thinker** is a more powerful model that runs in parallel, without ever blocking the conversation. After each caller turn, it rereads the entire transcript and produces structured JSON: the caller's record, missing information, the call phase (listening, collection, verification, support), and an instruction for the talker's next turn.

The talker receives the updated record and the thinker's instruction at each turn. It therefore never asks again for information already given, even if the person gave it out of order.

If the thinker detects a **life-threatening danger**, it interrupts the flow and immediately directs the person to 15 or 112.

### Reliability

- **Deterministic priority score**: the thinker only extracts factual criteria (true or false); the score is calculated by code, from a fixed rubric. The result is reproducible and auditable.
- **Fallback between models**: the thinker can try several models in order (`THINKER_MODELS`) if one is overloaded or out of quota.
- **Final analysis**: at the end of the call, the thinker performs one last analysis to incorporate the final exchanges.
- **Latency measurement**: each exchange is timed, step by step (turn end, transcription, talker, speech synthesis), with a target of 600 ms. A summary (median and P95) is produced at the end of each call.

### What each call produces

At the end of the call, two files are written to `sessions/`:

- `…-appel.json`: the complete record (identity, situation, location, special cases, criteria, priority score) and the transcript;
- `…-latence.csv`: latency measurements for each exchange.

It is this record, always in the same format, that will feed the call handler interface and the statistics.

### Files

| File | Role |
|---|---|
| `agent.py` | The voice agent: pipeline, thinker, priority score, latency measurement, call recording |
| `prompts.py` | The talker and thinker instructions, and the greeting message |
| `Makefile` | Installation and launch |
| `.env.example` | The list of API keys and settings (models, voice, rate) |

## Installation and launch

Prerequisites: Python 3 and API keys for Deepgram, Groq, ElevenLabs (and optionally Google for Gemini).

```bash
make install   # creates the venv and installs dependencies
make env       # creates .env, then fill in the keys
make console   # talk to Miki from the terminal
```

Transcriptions, records, and latency measurements for each call are saved in `sessions/`, which is not version-controlled.
