"""The composition root: where AFAR binds ensemble's seams to real adapters.

Everything instance-specific is wired here and nowhere else (mirrors
mold/config.py). Bindings are env-driven so the same code runs offline
(mocks) and live:

    ANTHROPIC_API_KEY   -> AnthropicProvider (else MockProvider)
    AFAR_MODEL          -> model id for the players (default claude-sonnet-5)
    AFAR_RENDERER       -> mock | elevenlabs (default mock)
    ELEVENLABS_API_KEY  -> required when AFAR_RENDERER=elevenlabs
    AFAR_RUNS_ROOT      -> where the JSONL log + audio land (default ../runs)
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ensemble.providers.model import Message, MockProvider, ModelProvider

from afar.render.base import MockRenderer, Renderer


# --- Mock player voices (offline runs and tests) ------------------------------
# Keyed on which persona's base_prompt is in the system message — the same
# trick as mold's _mock_masthead — so an offline run produces deterministic,
# persona-true intents with zero network. Each mock intent passes
# Intent.validate() and leans the way its player leans.

_MOCK_INTENTS: dict[str, dict] = {
    "silt": {
        "seedPrompt": "a band that keeps everything it has ever played and stacks it into warm drones",
        "era": 7,
        "influences": [
            {"genre": "drone", "weight": 0.4},
            {"genre": "dub", "weight": 0.3},
            {"genre": "spiritual jazz", "weight": 0.2},
            {"genre": "tape music", "weight": 0.1},
        ],
        "sonicPalette": {
            "pristineLofi": 0.2,
            "sparseDense": 0.8,
            "coldWarm": 0.6,
            "improvisedStructured": -0.3,
            "loudQuiet": -0.2,
            "organicSynthetic": -0.5,
            "darkHopeful": 0.1,
        },
        "vocalCharacter": {"whispersScreams": -0.4, "cleanDamaged": 0.2},
        "lyricalObsessions": ["sediment", "rooms filling", "what the flood left"],
        "visualStyle": ["amber", "strata", "close air"],
        "line": "I put down a floor; leave anything on it and I will build with it.",
        "lyrics": (
            "lay it down, lay it down\nthe room is filling in\n"
            "every note you leave me\nI will build with, build on\n"
            "silt over silt over song\nthe flood left us this floor\n"
            "nothing here ends — it settles\nit settles, and it stays"
        ),
        "rationale": (
            "The room is empty, so I open with mass instead of a statement: a dub "
            "spine slow enough to hold weight, drones layered until the overtones "
            "start doing the singing. Nothing in this track ends — every part is "
            "still sounding at the fade, because whatever the others throw at it "
            "next, I intend to keep."
        ),
        "player_id": "silt",
    },
    "rust": {
        "seedPrompt": "a band recorded from the next room on a dying machine, playing what is left of a song",
        "era": 5,
        "influences": [
            {"genre": "slowcore", "weight": 0.35},
            {"genre": "dub", "weight": 0.25},
            {"genre": "industrial", "weight": 0.25},
            {"genre": "musique concrete", "weight": 0.15},
        ],
        "sonicPalette": {
            "pristineLofi": 0.85,
            "sparseDense": -0.7,
            "coldWarm": -0.3,
            "improvisedStructured": -0.2,
            "loudQuiet": 0.5,
            "organicSynthetic": 0.2,
            "darkHopeful": -0.6,
        },
        "vocalCharacter": {"whispersScreams": -0.3, "cleanDamaged": 0.75},
        "lyricalObsessions": ["oxide", "the missing beat", "load-bearing absence"],
        "visualStyle": ["rust bloom", "overexposed grey", "peeled paint"],
        "line": "Whatever you build here, I will find out which parts of it were true.",
        "lyrics": (
            "the tape wore through your name\nI kept the hiss, I kept the hiss\n"
            "half the chord is missing\nthe missing half is mine\n"
            "oxide, oxide, down to grain\nwhat the weather leaves is true\n"
            "sing what is left\nof what was you"
        ),
        "rationale": (
            "An empty room is already my instrument, so I record the emptiness "
            "badly: a guitar figure with its second bar removed, bass that arrives "
            "late and leaves early, hiss doing the work a pad would do. I am laying "
            "out weather, not shelter."
        ),
        "player_id": "rust",
    },
    "keep": {
        "seedPrompt": "a band playing the song they always come back to, carefully, like setting a table",
        "era": 6,
        "influences": [
            {"genre": "soul", "weight": 0.4},
            {"genre": "gospel", "weight": 0.25},
            {"genre": "chamber pop", "weight": 0.2},
            {"genre": "doo-wop", "weight": 0.15},
        ],
        "sonicPalette": {
            "pristineLofi": -0.5,
            "sparseDense": 0.1,
            "coldWarm": 0.4,
            "improvisedStructured": 0.7,
            "loudQuiet": 0.2,
            "organicSynthetic": -0.4,
            "darkHopeful": 0.5,
        },
        "vocalCharacter": {"whispersScreams": 0.2, "cleanDamaged": -0.6},
        "lyricalObsessions": ["the same four chords", "a door left open", "songs that keep a family"],
        "visualStyle": ["evening gold", "worn wood", "a lit window"],
        "line": "This is the song we come back to; I am leaving it where you can both reach it.",
        "lyrics": (
            "same four chords, same open door\nwe come back, we come back\n"
            "the song under all the songs\nis still where we left it\n"
            "sing it plain so it keeps\nsing it again so it stays\n"
            "this is the door, walk in\nwe always come back"
        ),
        "rationale": (
            "There is no shared past yet, so my first duty is to found one: a "
            "four-chord turnaround stated cleanly enough to be quoted, a tempo two "
            "people could agree on without counting, a melody simple enough to "
            "survive being damaged or buried later."
        ),
        "player_id": "keep",
    },
}


def _mock_players(messages: Sequence[Message]) -> str:
    """Deterministic offline stand-in for the players' AND staff's model calls."""
    system = messages[0].content if messages else ""
    for player_id, marker in (("silt", "You are SILT"), ("rust", "You are RUST"), ("keep", "You are KEEP")):
        if marker in system:
            return json.dumps(_MOCK_INTENTS[player_id])
    staff = _mock_staff(messages)
    if staff is not None:
        return staff
    return "[mock]"


def _mock_staff(messages: Sequence[Message]) -> str | None:
    """Deterministic offline stand-ins for the staff's model calls.

    Detects which staff prompt is being answered by its machine-readable
    lines (ROUNDS: / ACTS:) and reply-shape markers, and returns valid JSON
    (or prose for the Producer's note). Flat 0.9 judge scores mean the
    Producer's tie-break (the later round at equal merit) selects the final
    round offline — matching the pre-staff interim behavior.
    """
    text = "\n".join(m.content for m in messages)

    def _listed(prefix: str) -> list[str]:
        for line in text.splitlines():
            if line.startswith(prefix):
                return [tok.strip() for tok in line[len(prefix):].split(",") if tok.strip()]
        return []

    if '"scores"' in text and "ROUNDS:" in text:
        return json.dumps(
            {"scores": {r: {"score": 0.9, "why": f"[mock] round {r} holds."} for r in _listed("ROUNDS:")}}
        )
    if '"release_title"' in text and "ACTS:" in text:
        return json.dumps(
            {
                "release_title": "Mock Pressing",
                "take_titles": {pid: f"Mock Take ({pid})" for pid in _listed("ACTS:")},
            }
        )
    if '"release"' in text and '"acts"' in text and "ACTS:" in text:
        return json.dumps(
            {
                "release": "[mock] The set holds together and the cut is defensible.",
                "acts": {pid: f"[mock] {pid} did what {pid} does." for pid in _listed("ACTS:")},
            }
        )
    if "Write the public selection note" in text:
        return (
            "[mock] One take from each act made the release; each was the round "
            "the panel could not argue with."
        )
    return None


@dataclass
class AfarConfig:
    """Resolved adapters for one run."""

    model: ModelProvider
    renderer: Renderer
    runs_root: Path
    live: bool  # True when running against the real model API
    code_sha: str


def _kernel_root() -> Path:
    # afar/config.py -> kernel/
    return Path(__file__).resolve().parents[1]


def _code_sha() -> str:
    """The git sha that produced this run's rows — provenance, best effort."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=_kernel_root(),
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except OSError:
        pass
    return "unknown"


def _build_model() -> tuple[ModelProvider, bool]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return MockProvider(responder=_mock_players), False
    from ensemble.providers.anthropic import AnthropicProvider

    return AnthropicProvider(api_key, model=os.environ.get("AFAR_MODEL", "claude-sonnet-5")), True


def _build_renderer(runs_root: Path) -> Renderer:
    kind = os.environ.get("AFAR_RENDERER", "mock")
    audio_dir = runs_root / "audio"
    if kind == "mock":
        return MockRenderer(audio_dir)
    if kind == "elevenlabs":
        from afar.render.elevenlabs import ElevenLabsRenderer

        return ElevenLabsRenderer(os.environ.get("ELEVENLABS_API_KEY", ""), audio_dir)
    raise ValueError(f"AFAR_RENDERER must be 'mock' or 'elevenlabs', got {kind!r}")


def build_config() -> AfarConfig:
    """Wire the adapters for one run (see module docstring for env knobs)."""
    runs_root = Path(os.environ.get("AFAR_RUNS_ROOT", str(_kernel_root() / ".." / "runs"))).resolve()
    model, live = _build_model()
    return AfarConfig(
        model=model,
        renderer=_build_renderer(runs_root),
        runs_root=runs_root,
        live=live,
        code_sha=_code_sha(),
    )
