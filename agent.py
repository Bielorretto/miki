"""POC agent vocal 115 — architecture 1 (cascade LiveKit), mode console.

Lancer :  python agent.py console
"""

import asyncio
import csv
import json
import logging
import os
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from openai import AsyncOpenAI
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ChatMessage,
    ConversationItemAddedEvent,
    JobContext,
    JobProcess,
    cli,
    inference,
)
from livekit.plugins import cartesia, deepgram, elevenlabs, groq, silero

from prompts import GREETING_TEXT, TALKER_PROMPT, THINKER_PROMPT

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger("agent-115")
OUT_DIR = Path(__file__).parent / "sessions"


class Assistant115(Agent):
    """Agent d'accueil : aucun outil, il ne fait que poser des questions."""

    def __init__(self) -> None:
        super().__init__(instructions=TALKER_PROMPT)


# Grille de priorité : calculée en Python à partir des critères extraits, pour être
# reproductible et auditable (le LLM extrait les faits, il ne décide pas du score).
PRIORITY_GRID = [
    (5, ("danger_vital", "violences", "mineur_seul")),
    (4, ("enfants_presents", "grossesse", "probleme_sante")),
    (3, ("age_65_plus", "handicap", "premiere_nuit_rue")),
    (2, ("sans_solution_ce_soir",)),
]
PRIORITY_LABELS = {5: "vitale", 4: "très haute", 3: "haute", 2: "moyenne", 1: "basse"}


def compute_priority(criteres: dict) -> dict:
    motifs = [c for _, keys in PRIORITY_GRID for c in keys if criteres.get(c)]
    score = next((lvl for lvl, keys in PRIORITY_GRID if any(criteres.get(k) for k in keys)), 1)
    return {"score": score, "niveau": PRIORITY_LABELS[score], "motifs": motifs}


class Thinker:
    """LLM puissant en parallèle : remplit la fiche, détecte l'urgence, guide le parleur."""

    def __init__(self, session: AgentSession, agent: Assistant115) -> None:
        self.session = session
        self.agent = agent
        # "fournisseur:modèle", essayés dans l'ordre (repli si saturé ou quota dépassé)
        self.models = os.environ.get("THINKER_MODELS", "groq:openai/gpt-oss-120b").split(",")
        self.groq = AsyncOpenAI(
            api_key=os.environ.get("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1"
        )
        self.gemini = genai.Client() if os.environ.get("GOOGLE_API_KEY") else None
        self.last: dict = {}
        self.vital_alerted = False
        self._task: asyncio.Task | None = None
        self._pending = False

    def trigger(self) -> None:
        if self._task and not self._task.done():
            self._pending = True  # relancer après l'analyse en cours
            return
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            self._pending = False
            try:
                await self._analyze()
            except Exception:
                logger.exception("erreur du penseur")
            if not self._pending:
                return

    def transcript(self) -> str:
        return "\n".join(
            f"{'APPELANT' if m.role == 'user' else 'ACCUEIL'}: {m.text_content}"
            for m in self.session.history.items
            if isinstance(m, ChatMessage) and m.role in ("user", "assistant") and m.text_content
        )

    async def finalize(self) -> None:
        """Dernière analyse en fin d'appel, pour intégrer les derniers échanges."""
        if self._task and not self._task.done():
            await self._task
        await self._analyze(final=True)

    async def _call(self, model: str, transcript: str) -> str:
        provider, name = model.split(":", 1)
        if provider == "groq":
            resp = await self.groq.chat.completions.create(
                model=name,
                reasoning_effort="medium",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": THINKER_PROMPT},
                    {"role": "user", "content": transcript},
                ],
            )
            return resp.choices[0].message.content
        resp = await self.gemini.aio.models.generate_content(
            model=name,
            contents=transcript,
            config=genai_types.GenerateContentConfig(
                system_instruction=THINKER_PROMPT, response_mime_type="application/json"
            ),
        )
        return resp.text

    async def _analyze(self, final: bool = False) -> None:
        transcript = self.transcript()
        if not transcript:
            return
        t0 = time.perf_counter()
        for model in self.models:
            try:
                raw = await self._call(model.strip(), transcript)
                break
            except Exception as e:
                logger.warning("penseur : %s indisponible (%s), modèle suivant", model, str(e)[:80])
        else:
            return
        self.last = json.loads(raw)
        self.last["priorite"] = compute_priority(self.last.get("criteres", {}))
        prio = self.last["priorite"]
        logger.info(
            "🧠 penseur %s (%.1fs) priorité=%d (%s) | manque=%s | consigne=%s",
            model,
            time.perf_counter() - t0,
            prio["score"],
            ", ".join(prio["motifs"]) or "aucun motif",
            self.last.get("infos_manquantes"),
            self.last.get("consigne"),
        )
        if final:
            return

        fiche = {k: v for k, v in self.last.items() if k not in ("consigne", "infos_manquantes")}
        await self.agent.update_instructions(
            f"{TALKER_PROMPT}\n\nFICHE ACTUELLE (ne redemande pas ce qui est connu) : "
            f"{json.dumps(fiche, ensure_ascii=False)}"
            f"\nINFORMATIONS MANQUANTES : {', '.join(self.last.get('infos_manquantes') or []) or 'aucune'}"
            f"\n\nCONSIGNE DU SUPERVISEUR, À SUIVRE EN PRIORITÉ pour ta prochaine réponse "
            f"(sauf si la personne vient de dire quelque chose d'urgent) : "
            f"{self.last.get('consigne') or 'aucune'}"
        )

        if self.last.get("criteres", {}).get("danger_vital") and not self.vital_alerted:
            self.vital_alerted = True
            logger.warning("🚨 DANGER VITAL détecté par le penseur")
            self.session.generate_reply(
                instructions="Danger vital détecté : dis calmement à la personne d'appeler tout de "
                "suite le 15 ou le 112. Rappelle que tu ne peux pas le faire à sa place."
            )


class LatencyLog:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._user_metrics: dict = {}

    def on_item(self, msg: ChatMessage) -> None:
        if msg.role == "user":
            self._user_metrics = dict(msg.metrics)
            return
        m = msg.metrics
        if "e2e_latency" not in m:
            return
        row = {
            "e2e_ms": m["e2e_latency"] * 1000,
            "fin_de_tour_ms": self._user_metrics.get("end_of_turn_delay", 0) * 1000,
            "stt_ms": self._user_metrics.get("transcription_delay", 0) * 1000,
            "llm_ttft_ms": m.get("llm_node_ttft", 0) * 1000,
            "tts_ttfb_ms": m.get("tts_node_ttfb", 0) * 1000,
        }
        self.rows.append(row)
        flag = "✅" if row["e2e_ms"] <= 600 else "⚠️"
        logger.info(
            "⏱ %s e2e=%.0fms | fin de tour=%.0f | STT=%.0f | LLM=%.0f | TTS=%.0f",
            flag, row["e2e_ms"], row["fin_de_tour_ms"], row["stt_ms"],
            row["llm_ttft_ms"], row["tts_ttfb_ms"],
        )

    def summary(self) -> str:
        if not self.rows:
            return "aucune mesure"
        e2e = sorted(r["e2e_ms"] for r in self.rows)
        p95 = e2e[min(len(e2e) - 1, int(len(e2e) * 0.95))]
        return f"{len(e2e)} tours | P50={statistics.median(e2e):.0f}ms | P95={p95:.0f}ms"


def build_tts():
    if os.environ.get("TTS_PROVIDER", "elevenlabs") == "cartesia":
        kw = {"voice": v} if (v := os.environ.get("CARTESIA_VOICE_ID")) else {}
        return cartesia.TTS(model="sonic-3", language="fr", **kw)
    kw = {"voice_id": v} if (v := os.environ.get("ELEVEN_VOICE_ID")) else {}
    # débit de parole : 0.8 (lent) → 1.2 (rapide), 1.0 = normal
    kw["voice_settings"] = elevenlabs.VoiceSettings(
        stability=0.5, similarity_boost=0.75, speed=float(os.environ.get("ELEVEN_SPEED", "0.9"))
    )
    return elevenlabs.TTS(model=os.environ.get("ELEVEN_MODEL", "eleven_flash_v2_5"), language="fr", **kw)


def build_llm():
    model = os.environ.get("TALKER_MODEL", "qwen/qwen3.8-27b")
    # jamais de raisonnement long dans le chemin critique
    kw = {}
    if "gpt-oss" in model:
        kw["reasoning_effort"] = "low"
    elif "qwen" in model:
        kw["reasoning_effort"] = "none"
    return groq.LLM(model=model, temperature=0.4, **kw)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


# laisse le temps à l'analyse finale du penseur avant de couper le process
server = AgentServer(setup_fnc=prewarm, shutdown_process_timeout=30)


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(
            model=os.environ.get("STT_MODEL", "nova-3"),
            language=os.environ.get("STT_LANGUAGE", "fr"),
        ),
        llm=build_llm(),
        tts=build_tts(),
        turn_handling={
            "turn_detection": inference.TurnDetector(version="v1-mini"),
            # patient avec les pauses : jusqu'à 3 s si la phrase semble inachevée
            "endpointing": {"min_delay": 0.4, "max_delay": 3.0},
        },
    )
    agent = Assistant115()
    thinker = Thinker(session, agent)
    latency = LatencyLog()

    @session.on("conversation_item_added")
    def _on_item(ev: ConversationItemAddedEvent) -> None:
        if not isinstance(ev.item, ChatMessage):
            return
        latency.on_item(ev.item)
        if ev.item.role == "user":
            thinker.trigger()

    async def _save() -> None:
        OUT_DIR.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        if latency.rows:
            with open(OUT_DIR / f"{stamp}-latence.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=latency.rows[0].keys())
                w.writeheader()
                w.writerows(latency.rows)
        try:
            await asyncio.wait_for(thinker.finalize(), timeout=20)
        except Exception:
            logger.exception("analyse finale impossible, dernière fiche conservée")
        fiche = {k: v for k, v in thinker.last.items() if k != "consigne"}
        appel = {
            "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "priorite": fiche.pop("priorite", None),
            **fiche,
            "transcription": thinker.transcript(),
        }
        (OUT_DIR / f"{stamp}-appel.json").write_text(json.dumps(appel, ensure_ascii=False, indent=2))
        logger.info("📋 Fiche d'appel :\n%s", json.dumps(appel, ensure_ascii=False, indent=2))
        logger.info("📊 Latence : %s — résultats dans %s", latency.summary(), OUT_DIR)

    ctx.add_shutdown_callback(_save)

    await session.start(agent=agent, room=ctx.room, record=False)
    # accueil fixe : instantané, et certains modèles refusent de générer sans message utilisateur
    session.say(GREETING_TEXT)


if __name__ == "__main__":
    cli.run_app(server)
