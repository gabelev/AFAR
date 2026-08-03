"""The composition root: where AFAR binds ensemble's seams to real adapters.

Everything instance-specific is wired here and nowhere else (mirrors
mold/config.py). Bindings are env-driven so the same code runs offline
(mocks) and live:

    ANTHROPIC_API_KEY   -> AnthropicProvider (else MockProvider)
    AFAR_MODEL          -> model id for the players (default claude-sonnet-5)
    AFAR_RENDERER       -> mock | elevenlabs (default mock)
    ELEVENLABS_API_KEY  -> required when AFAR_RENDERER=elevenlabs
    AFAR_RUNS_ROOT      -> where the JSONL log + audio land (default ../runs)

Conductor knobs (the spend controls — see afar/conductor.py):

    AFAR_ENABLED        -> "1" runs the piece; anything else idles + heartbeats
                           (default "0": the master switch ships OFF)
    AFAR_SETS_PER_DAY   -> pacing target, float (default 3.0)
    AFAR_DAILY_AUDIO_MINUTES -> hard ceiling on generated audio-minutes per
                           UTC day (default 110 — the $500/mo sizing; replaces
                           AFAR_DAILY_GEN_CAP: with variable take lengths,
                           minutes are what cost money, so minutes are the gate)
    AFAR_FAILURE_BACKOFF_MIN -> minutes before retrying after a failed set,
                           doubling per consecutive failure, capped at the
                           pace interval (default 15)
    AFAR_EXPERIMENT_MODE -> "1" restores the experiment parameters: the
                           schedule's weighted condition draw (contact :
                           isolation : parallel at 3:1:1, deterministic from
                           the schedule seed) books every set, exactly the
                           pre-sessions behavior. Default "0" — the live
                           piece: the Producer books each session
                           (together/alone) and parallel is never booked.
                           The lab is one flag away; the piece runs on the
                           office's judgment.
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
        "line": "I'm laying a floor first — slow bass, three quiet layers. Leave things on it.",
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
        "line": "Cut the second bar of the guitar and kept the hiss. The gap stays.",
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
        "line": "Four chords, played plain, back to the top. I'll play them again next round.",
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
    player_id = "silt"
    for pid, marker in (("silt", "You are SILT"), ("rust", "You are RUST"), ("keep", "You are KEEP")):
        if marker in system:
            player_id = pid
            break
    album = _mock_album(messages, player_id)
    if album is not None:
        return album
    for pid, marker in (("silt", "You are SILT"), ("rust", "You are RUST"), ("keep", "You are KEEP")):
        if marker in system:
            return json.dumps(_MOCK_INTENTS[pid])
    staff = _mock_staff(messages)
    if staff is not None:
        return staff
    return "[mock]"


def _mock_album(messages: Sequence[Message], player_id: str) -> str | None:
    """Deterministic offline stand-in for `Player.write_album`.

    Detected by the album prompt's machine-readable TRACKS: line — the same
    idiom the staff mocks use (ROUNDS: / ACTS:) — so the mock answers the
    record it was actually asked for, at the size the conductor budgeted. Any
    persona that is not one of the house three (a roster act) borrows SILT's
    DNA: `Album.from_json` stamps the real artist_id over it anyway, and the
    offline path only needs a VALID record, not a characterful one.
    """
    user = messages[-1].content if messages else ""
    if "TRACKS:" not in user or '"tracks"' not in user:
        return None
    n_tracks = 3
    for line in user.splitlines():
        if line.startswith("TRACKS:"):
            try:
                n_tracks = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
            break
    dna = _MOCK_INTENTS.get(player_id, _MOCK_INTENTS["silt"])
    obsessions = list(dna["lyricalObsessions"])
    return json.dumps(
        {
            "title": f"[mock] The {player_id.title()} Pressing",
            "description": (
                f"[mock] {n_tracks} songs cut in one sitting, all of them about "
                f"{obsessions[0]}."
            ),
            "rationale": "[mock] The record I would make with what I have heard.",
            "tracks": [
                {
                    "title": f"[mock] {obsessions[i % len(obsessions)].title()} {i + 1}",
                    "note": f"[mock] song {i + 1} keeps the {obsessions[i % len(obsessions)]}.",
                    "intent": {
                        **dna,
                        "lyrics": f"{dna['lyrics']}\nmock verse {i + 1}",
                        "rationale": f"[mock] song {i + 1} of the record.",
                    },
                }
                for i in range(n_tracks)
            ],
        }
    )


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
                "release_description": "[mock] Three takes from one room, pressed as they fell.",
                "take_titles": {
                    pid: {"title": f"Mock Take ({pid})", "why": f"[mock] {pid} sang it"}
                    for pid in _listed("ACTS:")
                },
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
    if '"duration_s"' in text and "how long should" in text:
        return json.dumps(
            {"duration_s": 30, "why": "[mock] a sketch session — keep the takes short"}
        )
    if '"session_form"' in text and "book the room" in text:
        return json.dumps(
            {"session_form": "together", "why": "[mock] the brief wants a room that answers back"}
        )
    if '"palette_notes"' in text and "Write the brief" in text:
        return json.dumps(
            {
                "brief": "[mock] The field is quiet and this world is not. "
                "Reach for the thread the last release left hanging.",
                "palette_notes": ["[mock] keep it close-mic'd", "[mock] slow is fine"],
            }
        )
    if '"placement"' in text and "Shelve this session's tape" in text:
        return json.dumps(
            {
                "placement": "companion",
                "tape_title": "Mock Session Tape",
                "arc": "[mock] Started sparse, ended settled.",
                "callouts": [],
                "liner_notes": (
                    "[mock] Everything played in this room is on this tape, in the "
                    "order it was played. Nothing recorded is ever worthless."
                ),
            }
        )
    if "Write the liner notes for this release" in text:
        return (
            "[mock] Three acts, one room, and the cut you are holding. What the "
            "sleeve does not show, the session tape keeps."
        )
    if "brought one record with them" in text:
        return (
            "[mock] The record they brought to town: made elsewhere, kept whole, "
            "shelved here where it belongs."
        )
    if '"valence"' in text and '"disagreements_with_critic"' in text:
        return json.dumps(
            {
                "valence": "liked",
                "reaction": "[mock] Played it twice. The quiet one got me; the rest I respect more than I love.",
                "disagreements_with_critic": ["[mock] The Critic is too hard on the closer."],
            }
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
    # Conductor spend controls (defaults keep every existing caller working).
    enabled: bool = False  # AFAR_ENABLED — the master switch; ships OFF
    sets_per_day: float = 3.0  # AFAR_SETS_PER_DAY — pacing target
    daily_audio_minutes: float = 110.0  # AFAR_DAILY_AUDIO_MINUTES — the hard daily gate
    failure_backoff_min: float = 15.0  # AFAR_FAILURE_BACKOFF_MIN — post-failure retry delay
    experiment_mode: bool = False  # AFAR_EXPERIMENT_MODE — "1" = the schedule's condition draw


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


#: Token budget for the biggest call the piece makes: a whole record — up to
#: six tracks, each carrying full DNA, sung lyrics and a rationale. ensemble's
#: 4096 default truncates a six-track album mid-JSON, which reads downstream as
#: an unparseable reply and burns the retry ladder on a length problem.
ALBUM_MAX_TOKENS = 16000


def _build_model() -> tuple[ModelProvider, bool]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return MockProvider(responder=_mock_players), False
    from ensemble.providers.anthropic import AnthropicProvider

    return (
        AnthropicProvider(
            api_key,
            model=os.environ.get("AFAR_MODEL", "claude-sonnet-5"),
            max_tokens=ALBUM_MAX_TOKENS,
        ),
        True,
    )


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
    sets_per_day = float(os.environ.get("AFAR_SETS_PER_DAY", "3"))
    if sets_per_day <= 0:
        raise ValueError(f"AFAR_SETS_PER_DAY must be > 0, got {sets_per_day}")
    daily_audio_minutes = float(os.environ.get("AFAR_DAILY_AUDIO_MINUTES", "110"))
    if daily_audio_minutes < 0:
        raise ValueError(f"AFAR_DAILY_AUDIO_MINUTES must be >= 0, got {daily_audio_minutes}")
    failure_backoff_min = float(os.environ.get("AFAR_FAILURE_BACKOFF_MIN", "15"))
    if failure_backoff_min <= 0:
        raise ValueError(f"AFAR_FAILURE_BACKOFF_MIN must be > 0, got {failure_backoff_min}")
    return AfarConfig(
        model=model,
        renderer=_build_renderer(runs_root),
        runs_root=runs_root,
        live=live,
        code_sha=_code_sha(),
        enabled=os.environ.get("AFAR_ENABLED", "0") == "1",
        sets_per_day=sets_per_day,
        daily_audio_minutes=daily_audio_minutes,
        failure_backoff_min=failure_backoff_min,
        experiment_mode=os.environ.get("AFAR_EXPERIMENT_MODE", "0") == "1",
    )
