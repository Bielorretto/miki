# Miki — assistante vocale du 115

Agent vocal (LiveKit) qui accompagne les appelants du 115 pendant l'attente et prépare leur dossier pour l'agent.

Pipeline : Deepgram (STT) → Groq (parleur) + penseur (Groq / Gemini) → ElevenLabs (TTS, ou Cartesia via `TTS_PROVIDER=cartesia`).

## Installation

```bash
make install   # crée le venv et installe les dépendances
make env       # crée .env, puis remplir les clés
```

## Lancer

```bash
make console
```

Les transcriptions, fiches et mesures de latence sont écrites dans `sessions/` (non versionné).
