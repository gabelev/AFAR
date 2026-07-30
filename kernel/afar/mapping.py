"""DNA -> ElevenLabs composition plan. A faithful port of afar_music's
`lib/generation/mapping.ts` + `styleTokens.ts`.

Structural levers, not adjectives: bipolar sliders emit BOTH positive and
negative global styles (sign picks the pole, magnitude picks how many tokens),
era sets BPM + production tokens, influence weights set token counts per genre,
the vocal pad emits vocal tokens, and improvised<->structured maps to the
context_adherence enum.

Verified API facts (afar_music docs/SPEC.md "Music API facts"):
- ONE 30s chunk; chunk text is LYRICS ONLY, clamped to 180 chars at a word
  boundary; context_adherence is an enum; respect_sections_durations false.

Parity notes (this file must keep matching mapping.test.ts oracles):
- JS Math.round is round-half-UP; Python round() is banker's rounding. Every
  Math.round in the TS source becomes `_js_round` here — using round() would
  silently shift BPMs and influence token counts on .5 boundaries.
- The plan is a plain dict in the exact API JSON shape (not a dataclass): it IS
  the request payload, and keeping it structural makes the prompt_sha honest.
- Provenance strings ("sonicPalette.organicSynthetic") are byte-identical to
  the TS ones so artifacts from both codebases join the same log.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from afar.intent import ERAS, SONIC_AXES, VOCAL_AXES, Intent

# Below this magnitude an axis is considered neutral and contributes nothing.
NEUTRAL_DEADZONE = 0.15
LYRICS_MAX_CHARS = 180
TRACK_DURATION_MS = 30_000

ContextAdherence = str  # "low" | "medium" | "high"


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
# list a value reaches — a dot just past center must NOT mean screaming:
# |v| in (deadzone, 0.55] -> first token, (0.55, 0.8] -> first two, > 0.8 -> all.
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

    `plan` is the exact API JSON shape (positive_global_styles,
    negative_global_styles, chunks). `provenance` lists the DNA field paths
    that contributed tokens — stored on the track artifact so any token can be
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
    """One bipolar value -> tokens for the active pole (goes to positive styles)
    and tokens for the opposing pole (goes to negative styles)."""
    if abs(value) < NEUTRAL_DEADZONE:
        return {"positive": [], "negative": []}
    active = poles["left"] if value < 0 else poles["right"]
    opposing = poles["right"] if value < 0 else poles["left"]
    return {
        "positive": _take_by_magnitude(active, value),
        "negative": _take_by_magnitude(opposing, value),
    }


def map_vocal_axis(
    value: float, poles: Mapping[str, Sequence[str]]
) -> dict[str, list[str]]:
    """Vocal axes use MILD->EXTREME banded lists (see VOCAL_TOKENS): the band
    decides how deep into the list a value reaches, so a pad dot just past
    center emits "powerful belted vocals", not "screamed vocals". The opposing
    pole's unmistakable tokens (everything past its first) go to negative
    styles."""
    magnitude = abs(value)
    if magnitude < NEUTRAL_DEADZONE:
        return {"positive": [], "negative": []}
    active = poles["left"] if value < 0 else poles["right"]
    opposing = poles["right"] if value < 0 else poles["left"]
    depth = len(active) if magnitude > 0.8 else 2 if magnitude > 0.55 else 1
    return {
        "positive": list(active[:depth]),
        "negative": list(opposing[1:]),
    }


def influence_tokens(genre: str, weight: float) -> list[str]:
    """Influence weight -> how many style tokens that genre contributes (0-4)."""
    candidates = [
        genre,
        f"{genre} instrumentation",
        f"{genre} rhythms",
        f"{genre} songwriting sensibility",
    ]
    count = min(len(candidates), _js_round(weight * 4))
    return candidates[:count]


def context_adherence_for(improvised_structured: float) -> ContextAdherence:
    """improvised<->structured in thirds -> the context_adherence enum."""
    if improvised_structured < -1 / 3:
        return "low"
    if improvised_structured <= 1 / 3:
        return "medium"
    return "high"


def clamp_lyrics(text: str) -> str:
    """Clamp lyrics to LYRICS_MAX_CHARS at a word boundary (>200 chars 500s the API)."""
    trimmed = text.strip()
    if len(trimmed) <= LYRICS_MAX_CHARS:
        return trimmed
    cut = trimmed[: LYRICS_MAX_CHARS + 1]
    last_space = cut.rfind(" ")
    return (cut[:last_space] if last_space > 0 else cut[:LYRICS_MAX_CHARS]).rstrip()


def _dedup(tokens: Sequence[str]) -> list[str]:
    """[...new Set(tokens)]: drop duplicates, keep first-seen order."""
    return list(dict.fromkeys(tokens))


def build_composition_plan(intent: Intent, lyrics: str) -> PlanWithProvenance:
    """Build the full composition plan for one track.

    `lyrics` comes from the player (driven by lyricalObsessions + mood); it is
    the only prose that lands in chunk text — all direction lives in the style
    arrays.
    """
    positive: list[str] = []
    negative: list[str] = []
    provenance: list[str] = []

    palette = intent.sonicPalette
    era = ERAS[intent.era]
    era_style = ERA_STYLES[era]
    # Era sets the base tempo; the loud<->quiet slider modulates it so a hushed
    # artist isn't pinned to their era's radio tempo (quiet slows up to 20%,
    # loud pushes up to 10%).
    lq = palette.loudQuiet
    bpm = _js_round(era_style["bpm"] * (1 - 0.2 * lq if lq > 0 else 1 + 0.1 * -lq))
    positive.append(f"{bpm} BPM")
    positive.extend(era_style["tokens"])
    provenance.append("era")

    # The heaviest influence anchors the genre with at least two tokens, so
    # spread-thin weights can't let palette adjectives outvote it.
    lead_genre = intent.influences[0]
    for influence in intent.influences[1:]:
        if influence.weight > lead_genre.weight:
            lead_genre = influence
    for influence in intent.influences:
        tokens = influence_tokens(influence.genre, influence.weight)
        if influence is lead_genre and len(tokens) < 2:
            tokens = [influence.genre, f"{influence.genre} instrumentation"]
        if tokens:
            positive.extend(tokens)
            provenance.append(f"influences.{influence.genre}")

    for axis in AXIS_TOKENS:
        mapped = map_bipolar_axis(getattr(palette, axis), AXIS_TOKENS[axis])
        if mapped["positive"] or mapped["negative"]:
            positive.extend(mapped["positive"])
            negative.extend(mapped["negative"])
            provenance.append(f"sonicPalette.{axis}")

    for pad_axis in VOCAL_TOKENS:
        mapped = map_vocal_axis(getattr(intent.vocalCharacter, pad_axis), VOCAL_TOKENS[pad_axis])
        if mapped["positive"] or mapped["negative"]:
            positive.extend(mapped["positive"])
            negative.extend(mapped["negative"])
            provenance.append(f"vocalCharacter.{pad_axis}")

    t = SOLO_PERFORMANCE_COMBO["threshold"]
    if palette.sparseDense <= -t and palette.loudQuiet >= t and palette.organicSynthetic <= -t:
        positive.extend(SOLO_PERFORMANCE_COMBO["positive"])
        negative.extend(SOLO_PERFORMANCE_COMBO["negative"])

    if lyrics.strip():
        provenance.append("lyricalObsessions")

    return PlanWithProvenance(
        plan={
            "positive_global_styles": _dedup(positive),
            "negative_global_styles": _dedup(negative),
            "chunks": [
                {
                    "text": clamp_lyrics(lyrics),
                    "duration_ms": TRACK_DURATION_MS,
                    # Per-chunk style arrays are required by the API but stay
                    # empty: all direction lives in the global arrays.
                    "positive_styles": [],
                    "negative_styles": [],
                }
            ],
        },
        context_adherence=context_adherence_for(palette.improvisedStructured),
        provenance=provenance,
    )
