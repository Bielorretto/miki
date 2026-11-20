https://github.com/user-attachments/assets/88b51066-c43c-43fe-a5af-2f40df1b1937



# Miki — l'assistante vocale qui répond à chaque appel du 115

> Aujourd'hui, **seuls 27% des appels au 115 sont traités**.
> Miki décroche tous les autres, recueille la situation de chaque appelant et la transmet aux écoutants dans un dossier.
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

Miki est une assistante vocale à intelligence artificielle qui prend en charge les appelants pendant leur attente. On l'appelle sur un vrai numéro de téléphone.

- **Elle décroche et se présente** : elle annonce qu'elle est une intelligence artificielle et demande l'accord de la personne avant de poser ses questions.
- **Elle écoute et pose des questions simples**, une à la fois, avec douceur : prénom et nom, âge, homme ou femme, situation (seule ou accompagnée, enfants, grossesse, santé, handicap, besoin urgent) et depuis quand la personne est à la rue. Elle ne demande jamais d'adresse.
- **Elle fait épeler le prénom et le nom**, puis relit les lettres pour les faire confirmer.
- **Elle résume ce qu'elle a compris** et le fait valider, puis demande s'il reste des questions et raccroche avec l'accord de la personne.
- **Elle rédige automatiquement un dossier** à la fin de l'appel, pour l'écoutant qui prendra le relais.

Si la personne décrit un danger vital immédiat (malaise, blessure grave, violences en cours, idées suicidaires), Miki lui dit d'appeler le 15 ou le 112. Elle ne promet jamais de place ni de délai, et ne répond pas aux questions sans rapport avec l'appel.

### Le score de priorité (prévu)

Le prochain objectif est d'ajouter au dossier un score de priorité calculé par une grille fixe, et non par l'IA : l'IA extrait les faits, la grille décide. Le score serait ainsi transparent, reproductible et vérifiable.

| Score | Niveau | Critères |
|---|---|---|
| 5 | Vitale | Danger vital, violences, mineur seul |
| 4 | Très haute | Enfants présents, grossesse, problème de santé |
| 3 | Haute | 65 ans et plus, handicap, première nuit à la rue |
| 2 | Moyenne | Sans solution pour ce soir |
| 1 | Basse | Aucun de ces critères |

## Ce que ça change

- **Pour les appelants** : chacun obtient un dossier, sans passer des heures au téléphone.
- **Pour les écoutants** : les dossiers arrivent déjà remplis, ce qui leur fait gagner du temps sur chaque appel.
- **Pour la FAS et la DIHAL** : des statistiques sur l'ensemble des appelants, et pas seulement sur ceux qui ont été décrochés (voir ci-dessous).

## Des statistiques enfin fiables

C'est l'autre apport majeur de Miki.

### Aujourd'hui : on ne connaît qu'une petite partie des appelants

Les statistiques du 115 reposent sur les appels décrochés. Or 89 % des appels ne le sont jamais : on ne sait pas qui sont ces personnes ni ce dont elles ont besoin. La demande réelle d'hébergement d'urgence est donc largement invisible, et les chiffres utilisés pour piloter le dispositif ne reflètent qu'une petite partie de la réalité.

### Avec Miki : chaque appel devient une donnée

Comme Miki répond à tous les appels, chacun produit un dossier structuré, toujours au même format. Agrégés et anonymisés, ces dossiers permettent de mesurer :

- **le volume réel de la demande**, y compris celle qui n'aboutit à aucune prise en charge ;
- **le profil des appelants** : âge, sexe, personnes seules ou familles, présence d'enfants ;
- **les publics vulnérables** : part de femmes enceintes, de personnes handicapées ou malades ;
- **l'ancienneté à la rue**, et notamment le nombre de personnes qui y passent leur première nuit ;
- **les langues parlées** par les appelants ;
- **l'évolution dans le temps** : par heure, par jour, par saison, par exemple lors d'une vague de froid.

### À quoi ça sert

Pour la FAS, la DIHAL et les SIAO, ces données sont une mine d'or :

- **piloter l'hébergement d'urgence** : anticiper les pics de demande ;
- **adapter l'offre aux publics** : places pour familles, pour femmes enceintes, accessibles aux personnes handicapées ;
- **justifier les moyens** auprès des pouvoirs publics avec des chiffres qui couvrent l'ensemble de la demande, et non une fraction.

Un point de vigilance : une même personne peut appeler plusieurs fois. Pour compter des personnes et pas seulement des appels, il faudra rapprocher les appels d'une même personne, tout en respectant le RGPD.

## Où en est le projet

### La vision

Miki décroche chaque appel du 115, sans attente et en parallèle. Chaque appelant repart avec un dossier créé, les écoutants traitent les dossiers par ordre de priorité, et les institutions disposent enfin de chiffres fiables.

### Ce qui fonctionne aujourd'hui (prototype)

- **De vrais appels téléphoniques** : un numéro Twilio est relié au programme ; on appelle le numéro, ou Miki appelle le numéro de son choix (`--appeler`).
- Une conversation vocale en français, en temps réel, avec une réponse qui commence en moins d'une seconde environ.
- Un déroulé d'appel complet : accueil, accord, questions, épellation du prénom et du nom, résumé, validation, « d'autres questions ? », au revoir et raccrochage.
- Une conversation robuste au bruit et aux interruptions : la télé, la rue ou un toussotement ne coupent pas Miki ; si la personne parle vraiment, Miki s'arrête.
- Une relance après 3 secondes de silence, et une demande de répétition quand la transcription n'a pas de sens.
- Un dossier JSON rédigé à la fin de chaque appel, même si la personne a raccroché avant la fin.
- La redirection vers le 15 ou le 112 en cas de danger vital.
- Un journal complet de chaque appel (événements à la milliseconde, latences, audio), enregistré en local.

### Ce qui reste à construire

- Le score de priorité, calculé par une grille fixe à partir du dossier.
- Plusieurs appels en même temps sur le même numéro, et un hébergement permanent (aujourd'hui, le programme tourne sur une machine personnelle derrière un tunnel).
- L'interface des écoutants, avec la file des dossiers triés par priorité.
- Un stockage sécurisé des dossiers (voir la section RGPD).
- L'agrégation des dossiers en statistiques anonymisées, avec un tableau de bord pour la FAS et la DIHAL.
- Le rapprochement des appels d'une même personne, pour compter des personnes et pas seulement des appels.
- Une meilleure reconnaissance des lettres épelées au téléphone (confusions G/J et M/N).
- Des tests en conditions réelles avec des écoutants du 115.

## Données personnelles et RGPD

Miki recueille des données sensibles au sens du RGPD (article 9), notamment de santé, de grossesse et de handicap. Le projet est conçu pour les traiter avec précaution :

- **Transparence** : Miki annonce dès le début qu'elle est une intelligence artificielle, et elle demande l'accord de la personne avant de poser ses questions.
- **Minimisation** : seules les informations utiles à la prise en charge sont demandées, jamais d'adresse, et la personne peut refuser de répondre à n'importe quelle question.
- **Statistiques anonymisées** : les données transmises aux institutions seront agrégées et ne permettront pas d'identifier les personnes.

Avant une mise en production, il faudra :

- héberger les données chez un hébergeur certifié HDS (hébergeur de données de santé) ;
- utiliser des fournisseurs d'IA hébergés en Europe, ou des modèles hébergés en interne ;
- fixer une durée de conservation des dossiers ;
- réaliser une analyse d'impact (AIPD) avec le délégué à la protection des données de l'opérateur du 115.

## Fonctionnement technique

Miki est une **cascade** écrite en Python, sans framework d'agent vocal : oreille (transcription) → penseur (modèle de langage) → voix (synthèse vocale). Le défi principal est la **latence** : pour qu'une conversation paraisse naturelle, Miki doit répondre en moins d'une seconde environ. La voix commence donc dès la première phrase du penseur, sans attendre la fin de sa réponse, et tout ce qui est lent (dossier, suivi) se fait à côté.

### Le pipeline (appel téléphonique)

```
           Appelant (téléphone)
                   │
                   ▼
   Twilio Media Streams ──► websocket (son μ-law 8 kHz, dans les deux sens)
     via un tunnel Cloudflare
                   │
                   ▼
   Écoute locale : Silero (voix humaine ?) + volume
     + Smart Turn (la phrase est-elle finie ?)
                   │
                   ▼
   Deepgram nova-3 ──► texte (français)
                   │
                   ▼
   Filtre + juge (gpt-oss-20b) : est-ce bien l'appelant ?
                   │
          ┌────────┴──────────────┐
          ▼                       ▼
   PENSEUR (Groq               SUIVI (gpt-oss-20b, en fond) :
   gpt-oss-120b)    ◄───────   ce qui est déjà dit, refusé,
   réponse mot à mot  note      ce qui manque
          │
          ▼
   ElevenLabs v3 (voix Lucie) ──► Twilio ──► appelant
          │
          ▼   fin de l'appel
   DOSSIER (gpt-oss-120b) ──► fiche.json
```

### Les briques

| Étape | Technologie | Rôle |
|---|---|---|
| Téléphonie | **Twilio Media Streams** + tunnel **Cloudflare** | Relie le numéro au programme ; le numéro est rebranché automatiquement à chaque lancement |
| Détection de la voix | **Silero VAD** + volume | Distingue une voix humaine du bruit (rue, métro, télé) |
| Fin de tour | **Smart Turn v3** | Écoute l'intonation et dit si la phrase est finie ; sinon Miki attend la suite |
| Transcription | **Deepgram nova-3** (français) | Transforme la voix en texte, en streaming |
| Juge | **gpt-oss-20b sur Groq** | Vérifie que ce qui a été entendu vient bien de l'appelant, et non d'une annonce ou d'une télé |
| Penseur | **gpt-oss-120b sur Groq** (réflexion « medium »), secours **OpenAI** | Mène la conversation ; si Groq est saturé (erreur 429), OpenAI prend le relais pour que Miki ne se taise jamais |
| Suivi | **gpt-oss-20b sur Groq**, en tâche de fond | Tient à jour ce que l'appelant a déjà dit ou refusé, pour que le penseur ne redemande rien |
| Synthèse vocale | **ElevenLabs v3 Conversational** (voix Lucie) | Donne sa voix à Miki, en français ; Flash v2.5 possible via `ELEVEN_MODELE` |
| Dossier | **gpt-oss-120b sur Groq**, secours OpenAI | Rédige le dossier JSON à la fin de l'appel, à partir de la transcription |

### Un modèle qui parle, d'autres qui écrivent

Le modèle qui parle ne s'occupe jamais du dossier : il ne peut donc ni le réciter, ni s'en distraire. Ses consignes (`commun/roles.py`) tiennent en un seul texte court, sans contradiction : phrases courtes, une question à la fin, vouvoiement, pas de promesse, épellation des noms, 15 ou 112 en cas de danger vital.

- **Le suivi** relit la conversation après chaque réponse et glisse une note interne au penseur : ce qui est acquis, ce qui a été refusé, ce qui manque.
- **Le dossier** est rédigé à la fin par un modèle à part, à partir de la transcription. Il contient : `prenom`, `nom`, `age`, `sexe`, `situation`, `duree_a_la_rue`, `langue`, `urgence_signalee`, `consentement` et `a_verifier` (les points incertains pour l'écoutant). Il n'invente rien : `null` pour toute information inconnue ou refusée.

### Le bruit et les interruptions

- **Anti-écho et anti-bruit WebRTC** sur ordinateur ; au téléphone, c'est le téléphone de l'appelant qui retire l'écho.
- **Seul l'audio utile part à la transcription** (de 0,2 s avant la voix à 0,15 s après) : le bruit autour ne devient jamais de faux mots.
- **Filtre du texte** : texte vide, écho de Miki ou phrase coupée sont ignorés ou mis en attente.
- **Barge-in en deux temps** : si l'appelant parle, le son de Miki baisse ; elle ne s'arrête que si de vrais mots confirment l'interruption. Le bruit ne peut donc jamais la couper.
- **Épellation** : quand Miki fait épeler, l'écoute attend toutes les lettres avant de répondre, et la relecture se fait sans attente.
- **Phrases fixes pré-enregistrées** (« Pardon, pouvez-vous répéter ? ») : dites sans attendre la synthèse vocale.

### Ce que produit chaque appel

Chaque appel crée un dossier `sessions/<date>_<programme>/`, qui n'est pas versionné :

- `fiche.json` : le dossier de l'appelant ;
- `journal.txt` : tout ce qui s'est passé, à la milliseconde (voix détectée, fin de tour et pourquoi, texte entendu, décisions du filtre et du juge, barge-in, latences) ;
- `session.json` : la conversation complète, y compris les morceaux ignorés ;
- `micro.wav` et `ia.wav` : le son de l'appelant et la voix de Miki.

### Les programmes

`bash lancer.sh` affiche un menu :

| Choix | Programme | Principe |
|---|---|---|
| 1 | `realtime` | OpenAI Realtime (parole → parole), au micro de l'ordinateur ou du téléphone |
| 2 | `cascade` | La cascade de Miki, au micro de l'ordinateur ou du téléphone |
| 3 | `eleven` | ElevenLabs Realtime, pour comparer |
| 4 | `appel` | **Miki au téléphone** : le numéro Twilio est branché sur la cascade |
| 5 | `live` | Expérimental, au téléphone : l'appel parle directement à GPT-Live 1.1 (le modèle du mode vocal de ChatGPT, full-duplex, voix française « brise »), qui confie les questions de fond à GPT-5.5 en coulisses ; fiche rédigée par GPT-5.5 |

### Les fichiers

```
appel/       Miki au téléphone : serveur websocket Twilio, tunnel Cloudflare, branchement du numéro
cascade/     oreille Deepgram, penseur, voix ElevenLabs, rédaction du dossier (fiche.py)
commun/      écoute, audio, filtre, juge, empreinte vocale, conversation (chef d'orchestre), rôles, journal
live/        programme 5 (pont Twilio ⇄ GPT-Live)
realtime/    programme 1 (OpenAI Realtime)
eleven/      programme 3 (ElevenLabs Realtime)
pc/          installation et lancement sur Mac
telephone/   installation et lancement sur Android (Termux + Debian)
outils/      tester_ecoute.py : passe un WAV dans l'écoute et montre ses décisions
lancer.sh    une seule commande pour tout installer et lancer
```

## Installation et lancement

Prérequis : Python 3 et des clés API Groq, Deepgram, ElevenLabs et OpenAI (secours), plus un compte Twilio avec un numéro pour les appels téléphoniques.

```bash
bash lancer.sh        # la première fois, tout s'installe (venv, dépendances, modèles) et .env est créé
                      # mets tes clés dans .env (jamais dans le code), puis relance
bash lancer.sh 4      # Miki au téléphone : laisse tourner, puis appelle le numéro Twilio
bash lancer.sh 4 --appeler +336XXXXXXXX   # ou c'est Miki qui t'appelle
```

Sur Mac, `pc/installer_mac.sh` installe tout ; sur Android, `telephone/1_dans_termux.sh` puis `telephone/2_installer.sh`. Les options utiles :

```bash
--penseur groq|openai|mistral   # cerveau de la conversation (défaut groq)
--juge groq|openai|mistral      # vérificateur rapide (défaut groq)
--role 115|libre                # rôle (défaut 115)
--langue fr|en|multi            # langue parlée (défaut fr)
--audio fichier:essai.wav       # test sans micro : le fichier sert de micro
```

La liste des clés et des réglages (modèles, voix) est dans `.env.example`. Pour rendre le numéro Twilio à son ancienne configuration : `.venv/bin/python -m appel.twilio --remettre`.

---

# Miki — The voice assistant that answers every 115 call

> Today, **only 27% of calls to 115 are handled**.
> Miki picks up all the others, gathers each caller's situation, and forwards it to call handlers in a file.
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

Miki is an AI voice assistant that supports callers while they wait. She is reached through a real phone number.

- **She picks up and introduces herself**: she says she is an artificial intelligence and asks for the person's consent before asking questions.
- **She listens and asks simple questions**, one at a time, gently: first and last name, age, man or woman, situation (alone or with others, children, pregnancy, health, disability, urgent need), and how long the person has been on the street. She never asks for an address.
- **She has the first and last name spelled out**, then reads the letters back for confirmation.
- **She summarizes what she understood** and has it validated, then asks whether there are other questions and hangs up with the person's agreement.
- **She automatically writes a file** at the end of the call, for the call handler who will take over.

If the person describes an immediate life-threatening danger (malaise, serious injury, ongoing violence, suicidal thoughts), Miki tells them to call 15 or 112. She never promises a bed or a timeframe, and does not answer questions unrelated to the call.

### Priority score (planned)

The next goal is to add a priority score to the file, calculated by a fixed rubric, not by AI: the AI extracts facts, the rubric decides. The score would therefore be transparent, reproducible, and auditable.

| Score | Level | Criteria |
|---|---|---|
| 5 | Life-threatening | Life-threatening danger, violence, unaccompanied minor |
| 4 | Very high | Children present, pregnancy, health problem |
| 3 | High | 65 and over, disability, first night on the street |
| 2 | Medium | No solution for tonight |
| 1 | Low | None of these criteria |

## What it changes

- **For callers**: everyone gets a file, without spending hours on the phone.
- **For call handlers**: files arrive already filled in, saving time on every call.
- **For FAS and DIHAL**: statistics on all callers, not just those who were answered (see below).

## Finally reliable statistics

This is Miki's other major contribution.

### Today: we only know a small portion of callers

115 statistics are based on answered calls. But 89% of calls are never answered: we do not know who these people are or what they need. The real demand for emergency accommodation is therefore largely invisible, and the figures used to steer the system reflect only a small part of reality.

### With Miki: every call becomes data

Because Miki answers all calls, each one produces a structured file, always in the same format. Aggregated and anonymized, these files make it possible to measure:

- **the real volume of demand**, including demand that does not result in any support;
- **the profile of callers**: age, sex, single people or families, presence of children;
- **vulnerable groups**: share of pregnant women, people with disabilities or illnesses;
- **how long people have been on the street**, including the number of people spending their first night there;
- **the languages spoken** by callers;
- **changes over time**: by hour, day, season, for example during a cold snap.

### What it is for

For FAS, DIHAL, and SIAOs, this data is a goldmine:

- **steering emergency accommodation**: anticipating demand peaks;
- **adapting supply to populations**: beds for families, pregnant women, accessible to people with disabilities;
- **justifying resources** to public authorities with figures that cover all demand, not just a fraction.

One point of vigilance: the same person may call several times. To count people and not just calls, calls from the same person will need to be matched, while complying with GDPR.

## Where the project stands

### The vision

Miki answers every 115 call, without waiting and in parallel. Every caller leaves with a created file, call handlers process files in order of priority, and institutions finally have reliable figures.

### What works today (prototype)

- **Real phone calls**: a Twilio number is connected to the program; you call the number, or Miki calls a number of your choice (`--appeler`).
- A real-time voice conversation in French, with replies starting in about one second or less.
- A complete call flow: greeting, consent, questions, spelling of first and last name, summary, validation, "any other questions?", goodbye, and hang-up.
- A conversation robust to noise and interruptions: TV, street noise, or a cough do not cut Miki off; if the person really speaks, Miki stops.
- A follow-up after 3 seconds of silence, and a request to repeat when the transcript makes no sense.
- A JSON file written at the end of each call, even if the person hung up early.
- Redirection to 15 or 112 in case of life-threatening danger.
- A complete log of each call (millisecond events, latencies, audio), saved locally.

### What remains to be built

- The priority score, calculated by a fixed rubric from the file.
- Several simultaneous calls on the same number, and permanent hosting (today, the program runs on a personal machine behind a tunnel).
- The call handler interface, with the queue of files sorted by priority.
- Secure storage of files (see the GDPR section).
- Aggregation of files into anonymized statistics, with a dashboard for FAS and DIHAL.
- Matching calls from the same person, to count people and not just calls.
- Better recognition of spelled letters over the phone (G/J and M/N confusions).
- Real-world tests with 115 call handlers.

## Personal data and GDPR

Miki collects sensitive data within the meaning of the GDPR (Article 9), including health, pregnancy, and disability data. The project is designed to handle it carefully:

- **Transparency**: Miki announces from the start that she is an artificial intelligence, and asks for the person's consent before asking questions.
- **Minimization**: only information useful for support is requested, never an address, and the person may refuse to answer any question.
- **Anonymized statistics**: data transmitted to institutions will be aggregated and will not allow people to be identified.

Before production, it will be necessary to:

- host data with an HDS-certified provider (health data hosting provider);
- use AI providers hosted in Europe, or models hosted internally;
- set a retention period for files;
- carry out a data protection impact assessment (DPIA) with the data protection officer of the 115 operator.

## Technical operation

Miki is a **cascade** written in Python, without a voice-agent framework: ear (transcription) → thinker (language model) → voice (speech synthesis). The main challenge is **latency**: for a conversation to feel natural, Miki must respond in under about one second. The voice therefore starts from the thinker's first sentence, without waiting for the end of its reply, and everything slow (file, tracking) runs on the side.

### The pipeline (phone call)

```
           Caller (phone)
                   │
                   ▼
   Twilio Media Streams ──► websocket (μ-law 8 kHz audio, both ways)
     through a Cloudflare tunnel
                   │
                   ▼
   Local listening: Silero (human voice?) + volume
     + Smart Turn (is the sentence finished?)
                   │
                   ▼
   Deepgram nova-3 ──► text (French)
                   │
                   ▼
   Filter + judge (gpt-oss-20b): is it really the caller?
                   │
          ┌────────┴──────────────┐
          ▼                       ▼
   THINKER (Groq               TRACKER (gpt-oss-20b, background):
   gpt-oss-120b)    ◄───────   what was already said, refused,
   streamed reply     note      what is missing
          │
          ▼
   ElevenLabs v3 (Lucie voice) ──► Twilio ──► caller
          │
          ▼   end of call
   FILE (gpt-oss-120b) ──► fiche.json
```

### The building blocks

| Step | Technology | Role |
|---|---|---|
| Telephony | **Twilio Media Streams** + **Cloudflare** tunnel | Connects the number to the program; the number is rewired automatically at each launch |
| Voice detection | **Silero VAD** + volume | Tells a human voice apart from noise (street, metro, TV) |
| Turn end | **Smart Turn v3** | Listens to intonation and says whether the sentence is finished; otherwise Miki waits for more |
| Transcription | **Deepgram nova-3** (French) | Converts voice to text, in streaming |
| Judge | **gpt-oss-20b on Groq** | Checks that what was heard really comes from the caller, not an announcement or a TV |
| Thinker | **gpt-oss-120b on Groq** ("medium" reasoning), **OpenAI** fallback | Leads the conversation; if Groq is overloaded (429 error), OpenAI takes over so Miki never goes silent |
| Tracker | **gpt-oss-20b on Groq**, in the background | Keeps track of what the caller has already said or refused, so the thinker never asks again |
| Speech synthesis | **ElevenLabs v3 Conversational** (Lucie voice) | Gives Miki her voice, in French; Flash v2.5 available via `ELEVEN_MODELE` |
| File | **gpt-oss-120b on Groq**, OpenAI fallback | Writes the JSON file at the end of the call, from the transcript |

### One model talks, others write

The model that talks never handles the file: it can neither recite it nor be distracted by it. Its instructions (`commun/roles.py`) are a single short text, without contradictions: short sentences, one question at the end, formal "vous", no promises, spelling of names, 15 or 112 in case of life-threatening danger.

- **The tracker** rereads the conversation after each reply and slips an internal note to the thinker: what is known, what was refused, what is missing.
- **The file** is written at the end by a separate model, from the transcript. It contains: `prenom`, `nom`, `age`, `sexe`, `situation`, `duree_a_la_rue`, `langue`, `urgence_signalee`, `consentement`, and `a_verifier` (uncertain points for the call handler). It invents nothing: `null` for any unknown or refused information.

### Noise and interruptions

- **WebRTC echo and noise cancellation** on computers; on the phone, the caller's phone removes the echo.
- **Only useful audio is sent to transcription** (from 0.2 s before the voice to 0.15 s after): surrounding noise never becomes fake words.
- **Text filter**: empty text, Miki's own echo, or cut-off sentences are ignored or held.
- **Two-step barge-in**: if the caller speaks, Miki's volume drops; she only stops if real words confirm the interruption. Noise can therefore never cut her off.
- **Spelling**: when Miki asks for spelling, listening waits for all the letters before replying, and the read-back happens without delay.
- **Pre-recorded fixed phrases** ("Sorry, could you repeat?"): spoken without waiting for speech synthesis.

### What each call produces

Each call creates a folder `sessions/<date>_<program>/`, which is not versioned:

- `fiche.json`: the caller's file;
- `journal.txt`: everything that happened, to the millisecond (voice detected, turn end and why, text heard, filter and judge decisions, barge-in, latencies);
- `session.json`: the full conversation, including ignored fragments;
- `micro.wav` and `ia.wav`: the caller's audio and Miki's voice.

### The programs

`bash lancer.sh` shows a menu:

| Choice | Program | Principle |
|---|---|---|
| 1 | `realtime` | OpenAI Realtime (speech → speech), on the computer's or phone's microphone |
| 2 | `cascade` | Miki's cascade, on the computer's or phone's microphone |
| 3 | `eleven` | ElevenLabs Realtime, for comparison |
| 4 | `appel` | **Miki on the phone**: the Twilio number is connected to the cascade |
| 5 | `live` | Experimental, on the phone: the call talks directly to GPT-Live 1.1 (the model behind ChatGPT voice, full-duplex, French voice "brise"), which hands hard questions to GPT-5.5 in the background; case file written by GPT-5.5 |

### Files

```
appel/       Miki on the phone: Twilio websocket server, Cloudflare tunnel, number wiring
cascade/     Deepgram ear, thinker, ElevenLabs voice, file writing (fiche.py)
commun/      listening, audio, filter, judge, voiceprint, conversation (orchestrator), roles, log
live/        program 5 (Twilio ⇄ GPT-Live bridge)
realtime/    program 1 (OpenAI Realtime)
eleven/      program 3 (ElevenLabs Realtime)
pc/          install and launch on Mac
telephone/   install and launch on Android (Termux + Debian)
outils/      tester_ecoute.py: runs a WAV through listening and shows its decisions
lancer.sh    one command to install and launch everything
```

## Installation and launch

Requirements: Python 3 and Groq, Deepgram, ElevenLabs, and OpenAI (fallback) API keys, plus a Twilio account with a number for phone calls.

```bash
bash lancer.sh        # the first time, everything installs (venv, dependencies, models) and .env is created
                      # put your keys in .env (never in the code), then relaunch
bash lancer.sh 4      # Miki on the phone: leave it running, then call the Twilio number
bash lancer.sh 4 --appeler +336XXXXXXXX   # or Miki calls you
```

On Mac, `pc/installer_mac.sh` installs everything; on Android, `telephone/1_dans_termux.sh` then `telephone/2_installer.sh`. Useful options:

```bash
--penseur groq|openai|mistral   # conversation brain (default groq)
--juge groq|openai|mistral      # fast checker (default groq)
--role 115|libre                # role (default 115)
--langue fr|en|multi            # spoken language (default fr)
--audio fichier:essai.wav       # test without a microphone: the file acts as the microphone
```

The list of keys and settings (models, voices) is in `.env.example`. To restore the Twilio number's previous configuration: `.venv/bin/python -m appel.twilio --remettre`.
