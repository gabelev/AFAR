"""DNA -> ElevenLabs music_v2 composition plan. A faithful port of afar_music's
`lib/generation/mapping.ts` + `styleTokens.ts`.

Structural levers, not adjectives: era sets BPM + production tokens, influences
and bipolar sliders contribute ranked style tokens, the vocal pad claims
guaranteed slots, and improvised<->structured maps to the chunk's
context_adherence enum.

Shape verified against the current API reference (api-reference/music/compose):
- music_v2's CompositionPlan is chunks-only. positive_global_styles /
  negative_global_styles are the music_v1 MusicPrompt schema and are ignored
  by music_v2 — chunk positive_styles/negative_styles are what the model
  reads ("styles for the first chunk are the most important").
- The docs recommend ~6-7 positive styles and say empty negatives are
  typical, so tokens compete for a small budget instead of all being sent.
- context_adherence is a per-chunk enum (documented default "high").
- Chunk text is lyrics; the ~200-char limit is per LINE (multi-line is fine).

Parity notes (this file must keep matching mapping.test.ts oracles):
- JS Math.round is round-half-UP; Python round() is banker's rounding. Every
  Math.round in the TS source becomes `_js_round` here — using round() would
  silently shift BPMs on .5 boundaries. (influenceTokens uses Math.ceil, which
  IS Python's math.ceil.)
- The plan is a plain dict in the exact API JSON shape (not a dataclass): it IS
  the request payload, and keeping it structural makes the prompt_sha honest.
- Provenance strings ("sonicPalette.organicSynthetic") are byte-identical to
  the TS ones so artifacts from both codebases join the same log.
- Sorting must stay STABLE (JS Array.prototype.sort and Python sorted both
  are): budget ties resolve by insertion order in both codebases.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from afar.intent import ERAS, SONIC_AXES, VOCAL_AXES, Intent

# Below this magnitude an axis is considered neutral and contributes nothing.
NEUTRAL_DEADZONE = 0.15
# Only leans at least this strong ban the opposing pole.
NEGATIVE_LEAN_THRESHOLD = 0.6
# Docs recommend 6-7 styles on the first chunk; more dilutes all of them.
POSITIVE_STYLE_BUDGET = 7
# Docs: leaving negatives empty is typical — send only the strongest few bans.
NEGATIVE_STYLE_BUDGET = 4
LYRIC_LINE_MAX_CHARS = 180
LYRIC_MAX_LINES = 8
TRACK_DURATION_MS = 30_000

ContextAdherence = str  # "low" | "medium" | "high"

_INF = float("inf")


def _js_round(x: float) -> int:
    """JS Math.round semantics: round half toward +infinity (round-half-up)."""
    return math.floor(x + 0.5)


# --- Style token vocabulary (verbatim from styleTokens.ts) --------------------
# Deliberately OUTSIDE the DNA schema so the vocabulary can be tuned between
# runs without a migration. `left` is the -1 pole, `right` the +1 pole,
# matching the axis field names (pristineLofi: left=pristine, right=lofi).
# Tokens are ordered strongest-first: magnitude decides how many are taken.

AXIS_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "pristineLofi": {
        "left": ("pristine production", "polished", "hi-fi clarity"),
        "right": ("lo-fi", "tape saturation", "cassette hiss"),
    },
    "sparseDense": {
        "left": ("sparse arrangement", "minimal instrumentation", "negative space"),
        "right": ("dense arrangement", "layered instrumentation", "wall of sound"),
    },
    "coldWarm": {
        "left": ("cold tone", "icy digital timbre", "detached"),
        "right": ("warm tone", "analog warmth", "cozy timbre"),
    },
    "improvisedStructured": {
        "left": ("improvised feel", "loose performance", "jam-like spontaneity"),
        "right": ("structured songwriting", "tight arrangement", "precise performance"),
    },
    "loudQuiet": {
        "left": ("loud", "aggressive dynamics", "in-the-red energy"),
        "right": ("quiet", "hushed dynamics", "intimate"),
    },
    "organicSynthetic": {
        # No "live drums" here: era/axis tokens describe production, never force
        # instrumentation (a whisper-folk artist at organic -0.9 was getting a
        # full drum kit).
        "left": ("organic instrumentation", "acoustic instruments", "natural room acoustics"),
        "right": ("synthetic textures", "electronic synthesis", "drum machines"),
    },
    "darkHopeful": {
        "left": ("dark mood", "brooding", "ominous undertow"),
        "right": ("hopeful mood", "uplifting", "radiant"),
    },
}
assert tuple(AXIS_TOKENS) == SONIC_AXES  # iteration order = provenance order

# 2D vocal pad vocabulary, ordered MILD -> EXTREME per pole (unlike the sonic
# axes, which are strongest-first). Magnitude bands decide how deep into the
# list a value reaches — a dot just past center must NOT mean screaming.
VOCAL_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "whispersScreams": {
        "left": ("soft intimate vocals", "whispered vocals", "breathy delivery"),
        "right": ("powerful belted vocals", "screamed vocals", "throat-shredding intensity"),
    },
    "cleanDamaged": {
        "left": ("clean vocals", "pure vocal tone"),
        "right": ("raspy weathered vocal texture", "damaged vocal texture", "distorted vocals"),
    },
}
assert tuple(VOCAL_TOKENS) == VOCAL_AXES

# Cross-axis combination: when sparse, quiet, and organic all lean together,
# say "solo, no band" outright instead of leaving the model free to add a
# rhythm section. Threshold applies to each axis (sparse <= -t, quiet >= t,
# organic <= -t).
SOLO_PERFORMANCE_COMBO: dict[str, Any] = {
    "threshold": 0.4,
    "positive": ("intimate solo performance",),
    "negative": ("full band arrangement", "drum kit", "percussion"),
}

# Era -> default BPM and production-era tokens. Keyed by ERAS entries.
# Era tokens are production-era descriptors only — no genre words and no
# instrumentation ("rock and roll", "trap hi-hats", "gated reverb drums"
# were dragging every artist of an era toward one genre's sound).
ERA_STYLES: dict[str, dict[str, Any]] = {
    "far-past": {"bpm": 80, "tokens": ("ancient folk tradition", "pre-industrial acoustics")},
    "1950s": {"bpm": 100, "tokens": ("1950s era production", "mono-era recording")},
    "1960s": {"bpm": 110, "tokens": ("1960s analog production", "vintage tube warmth")},
    "1970s": {"bpm": 105, "tokens": ("1970s studio production", "analog tape sound")},
    "1980s": {"bpm": 118, "tokens": ("1980s production", "big analog reverb")},
    "1990s": {"bpm": 112, "tokens": ("1990s production", "radio-era mixing")},
    "2000s": {"bpm": 115, "tokens": ("2000s digital production", "radio-polished mix")},
    "2010s": {"bpm": 120, "tokens": ("2010s production", "streaming-era polish")},
    "2020s": {"bpm": 122, "tokens": ("2020s contemporary production", "hyper-detailed mix")},
    "2030s": {"bpm": 126, "tokens": ("near-future production", "AI-flavored sound design")},
    "far-future": {"bpm": 132, "tokens": ("far-future sound design", "post-human textures")},
}
assert tuple(ERA_STYLES) == ERAS


@dataclass(frozen=True)
class PlanWithProvenance:
    """A composition plan plus where it came from.

    `plan` is the exact API JSON shape: chunks-only, with positive_styles /
    negative_styles / context_adherence ON the chunk (music_v2 reads nothing
    else). `provenance` lists the DNA field paths whose tokens made the
    TRANSMITTED plan — stored on the track artifact so any token can be
    traced back to the slider that produced it.
    """

    plan: dict[str, Any]
    context_adherence: ContextAdherence
    provenance: list[str]


def _take_by_magnitude(tokens: Sequence[str], magnitude: float) -> list[str]:
    """Take the strongest `count` tokens for a magnitude in (0,1]."""
    count = min(len(tokens), math.ceil(abs(magnitude) * len(tokens)))
    return list(tokens[:count])


def map_bipolar_axis(
    value: float, poles: Mapping[str, Sequence[str]]
) -> dict[str, list[str]]:
    """One bipolar value -> candidate tokens for the active pole and, only when
    the lean is strong, a single ban on the opposing pole's strongest token.
    Mild leans state a preference without negating anything."""
    if abs(value) < NEUTRAL_DEADZONE:
        return {"positive": [], "negative": []}
    active = poles["left"] if value < 0 else poles["right"]
    opposing = poles["right"] if value < 0 else poles["left"]
    return {
        "positive": _take_by_magnitude(active, value),
        "negative": [opposing[0]] if abs(value) >= NEGATIVE_LEAN_THRESHOLD else [],
    }


def map_vocal_axis(
    value: float, poles: Mapping[str, Sequence[str]]
) -> dict[str, list[str]]:
    """Vocal axes use MILD->EXTREME banded lists (see VOCAL_TOKENS): the band
    decides which tokens a value reaches, so a pad dot at 0.6 emits "powerful
    belted vocals" — never "screamed vocals", which needs a lean past 0.6.
    Extreme positions (>0.85) drop the mild token and speak in the pole's
    extremes. Only strong leans (>=0.6) ban the opposing pole's unmistakable
    token."""
    magnitude = abs(value)
    if magnitude < NEUTRAL_DEADZONE:
        return {"positive": [], "negative": []}
    active = poles["left"] if value < 0 else poles["right"]
    opposing = poles["right"] if value < 0 else poles["left"]
    if magnitude > 0.85:
        positive = list(active[-2:])
    elif magnitude > NEGATIVE_LEAN_THRESHOLD:
        positive = list(active[:2])
    else:
        positive = [active[0]]
    negative = (
        [opposing[min(1, len(opposing) - 1)]]
        if magnitude >= NEGATIVE_LEAN_THRESHOLD
        else []
    )
    return {"positive": positive, "negative": negative}


def influence_tokens(genre: str, weight: float) -> list[str]:
    """Influence weight -> how many style tokens that genre contributes (1-4 for
    any nonzero weight). Math.ceil, not round: a genre shown as "10%" in the UI
    must still contribute its name."""
    if weight <= 0:
        return []
    candidates = [
        genre,
        f"{genre} instrumentation",
        f"{genre} rhythms",
        f"{genre} songwriting sensibility",
    ]
    count = min(len(candidates), math.ceil(weight * 4))
    return candidates[:count]


def context_adherence_for(improvised_structured: float) -> ContextAdherence:
    """improvised<->structured in thirds -> the context_adherence enum."""
    if improvised_structured < -1 / 3:
        return "low"
    if improvised_structured <= 1 / 3:
        return "medium"
    return "high"


def clamp_lyrics(text: str) -> str:
    """Clamp lyrics line by line: the API's ~200-char limit is per LINE (200/line
    500s; 180 is the verified-safe clamp), and multi-line text is how a 30s
    chunk carries a singable word count."""
    lines = [line.strip() for line in re.split(r"\r?\n", text)]
    return "\n".join(
        _clamp_line(line) for line in [ln for ln in lines if ln][:LYRIC_MAX_LINES]
    )


def _clamp_line(line: str) -> str:
    if len(line) <= LYRIC_LINE_MAX_CHARS:
        return line
    cut = line[: LYRIC_LINE_MAX_CHARS + 1]
    last_space = cut.rfind(" ")
    return (cut[:last_space] if last_space > 0 else cut[:LYRIC_LINE_MAX_CHARS]).rstrip()


@dataclass
class _Candidate:
    """A style token competing for a budget slot, tagged with its DNA source."""

    token: str
    score: float
    source: str


def build_composition_plan(intent: Intent, lyrics: str) -> PlanWithProvenance:
    """Build the full composition plan for one track.

    `lyrics` comes from the player (driven by lyricalObsessions + mood); it is
    the only prose that lands in chunk text — all direction lives in the style
    arrays.

    Selection: a few tokens are guaranteed (BPM, era, lead genre, active vocal
    axes, the solo combo), the rest compete on magnitude for the remaining
    budget. Influence scores are boosted x1.5 because weights sum to 1 across
    four genres while axes reach +-1.
    """
    guaranteed: list[_Candidate] = []
    pool: list[_Candidate] = []
    negatives: list[_Candidate] = []

    palette = intent.sonicPalette
    era = ERAS[intent.era]
    era_style = ERA_STYLES[era]
    # Era sets the base tempo; the loud<->quiet slider modulates it so a hushed
    # artist isn't pinned to their era's radio tempo (quiet slows up to 20%,
    # loud pushes up to 10%).
    lq = palette.loudQuiet
    bpm = _js_round(era_style["bpm"] * (1 - 0.2 * lq if lq > 0 else 1 + 0.1 * -lq))
    guaranteed.append(_Candidate(f"{bpm} BPM", _INF, "era"))
    guaranteed.append(_Candidate(era_style["tokens"][0], _INF, "era"))
    for token in era_style["tokens"][1:]:
        pool.append(_Candidate(token, 0.35, "era"))

    # The heaviest influence anchors the genre with two guaranteed tokens, so
    # spread-thin weights can't let palette adjectives outvote it.
    lead_genre = intent.influences[0]
    for influence in intent.influences[1:]:
        if influence.weight > lead_genre.weight:
            lead_genre = influence
    for influence in intent.influences:
        source = f"influences.{influence.genre}"
        tokens = (
            [influence.genre, f"{influence.genre} instrumentation"]
            if influence is lead_genre
            else influence_tokens(influence.genre, influence.weight)
        )
        for k, token in enumerate(tokens):
            if influence is lead_genre:
                guaranteed.append(_Candidate(token, _INF, source))
            else:
                pool.append(_Candidate(token, influence.weight * 1.5 - 0.15 * k, source))

    for axis in AXIS_TOKENS:
        value = getattr(palette, axis)
        mapped = map_bipolar_axis(value, AXIS_TOKENS[axis])
        source = f"sonicPalette.{axis}"
        for k, token in enumerate(mapped["positive"]):
            pool.append(_Candidate(token, abs(value) - 0.25 * k, source))
        for token in mapped["negative"]:
            negatives.append(_Candidate(token, abs(value), source))

    for pad_axis in VOCAL_TOKENS:
        value = getattr(intent.vocalCharacter, pad_axis)
        mapped = map_vocal_axis(value, VOCAL_TOKENS[pad_axis])
        source = f"vocalCharacter.{pad_axis}"
        # The pad is a headline control: its lead token must not be crowded out.
        for k, token in enumerate(mapped["positive"]):
            if k == 0:
                guaranteed.append(_Candidate(token, _INF, source))
            else:
                pool.append(_Candidate(token, abs(value) - 0.1 * k, source))
        for token in mapped["negative"]:
            negatives.append(_Candidate(token, abs(value), source))

    t = SOLO_PERFORMANCE_COMBO["threshold"]
    if palette.sparseDense <= -t and palette.loudQuiet >= t and palette.organicSynthetic <= -t:
        for token in SOLO_PERFORMANCE_COMBO["positive"]:
            guaranteed.append(_Candidate(token, _INF, "sonicPalette.sparseDense"))
        for token in SOLO_PERFORMANCE_COMBO["negative"]:
            negatives.insert(0, _Candidate(token, _INF, "sonicPalette.sparseDense"))

    positive = _select_by_budget(
        guaranteed + sorted(pool, key=lambda c: c.score, reverse=True),
        POSITIVE_STYLE_BUDGET,
    )
    positive_tokens = {c.token for c in positive}
    negative = _select_by_budget(
        [
            c
            for c in sorted(negatives, key=lambda c: c.score, reverse=True)
            if c.token not in positive_tokens
        ],
        NEGATIVE_STYLE_BUDGET,
    )

    provenance = list(dict.fromkeys(c.source for c in positive + negative))
    if lyrics.strip():
        provenance.append("lyricalObsessions")

    context_adherence = context_adherence_for(palette.improvisedStructured)
    return PlanWithProvenance(
        plan={
            "chunks": [
                {
                    "text": clamp_lyrics(lyrics),
                    "duration_ms": TRACK_DURATION_MS,
                    "positive_styles": [c.token for c in positive],
                    "negative_styles": [c.token for c in negative],
                    "context_adherence": context_adherence,
                }
            ],
        },
        context_adherence=context_adherence,
        provenance=provenance,
    )


def _select_by_budget(candidates: Sequence[_Candidate], budget: int) -> list[_Candidate]:
    """First `budget` distinct tokens, preserving order."""
    seen: set[str] = set()
    selected: list[_Candidate] = []
    for candidate in candidates:
        if len(selected) >= budget:
            break
        if candidate.token in seen:
            continue
        seen.add(candidate.token)
        selected.append(candidate)
    return selected
