"""Intent: the Creative DNA a player commits to before a note exists.

This is a faithful port of afar_music's `lib/dna/schema.ts` — the single input
state every generation path reads from. Nothing generates from prose directly;
the DNA is the contract between a player's decision and the renderer, which is
what makes every track diff-able, hashable, and re-renderable.

Field names stay camelCase on purpose: `to_dna_dict()` must emit the exact
schema.ts JSON shape, and mapping provenance strings ("sonicPalette.coldWarm")
must match the TS ones byte-for-byte so the two codebases stay oracle-compatible.

Bipolar axes are signed -1..1: the SIGN says which pole (-1 = left/first-named
pole, +1 = right pole), the MAGNITUDE says how hard. 0 is neutral. Style tokens
live in `afar.mapping`, keyed by axis and pole — never here — so the vocabulary
tunes between runs without a schema migration.

AFAR additions on top of the DNA: `line` (the one sentence a player says out
loud — the installation's chat bubble), `lyrics` (the words the player SINGS —
the only prose that reaches the renderer's chunk text), `rationale` (the full
reasoning, kept for the log, never sent to the renderer), and `player_id` (the
stable public id: silt | rust | keep — these join URLs and the world renderer,
never rename).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields
from typing import Any, Mapping, Sequence

ERAS: tuple[str, ...] = (
    "far-past",
    "1950s",
    "1960s",
    "1970s",
    "1980s",
    "1990s",
    "2000s",
    "2010s",
    "2020s",
    "2030s",
    "far-future",
)

PLAYER_IDS: tuple[str, ...] = ("silt", "rust", "keep")

_WEIGHT_SUM_TOLERANCE = 1e-6
_INFLUENCE_COUNT = 4


@dataclass(frozen=True)
class Influence:
    """One weighted genre. Exactly four of these make up a player's blood."""

    genre: str
    weight: float


@dataclass(frozen=True)
class SonicPalette:
    """7 bipolar axes. -1 = first pole, +1 = second pole."""

    pristineLofi: float  # pristine <-> lo-fi
    sparseDense: float  # sparse <-> dense
    coldWarm: float  # cold <-> warm
    improvisedStructured: float  # improvised <-> structured
    loudQuiet: float  # loud <-> quiet
    organicSynthetic: float  # organic <-> synthetic
    darkHopeful: float  # dark <-> hopeful


SONIC_AXES: tuple[str, ...] = tuple(f.name for f in fields(SonicPalette))


@dataclass(frozen=True)
class VocalCharacter:
    """2D pad: whispers(-1) <-> screams(+1), clean(-1) <-> damaged(+1)."""

    whispersScreams: float
    cleanDamaged: float


VOCAL_AXES: tuple[str, ...] = tuple(f.name for f in fields(VocalCharacter))


@dataclass(frozen=True)
class Intent:
    """A complete, validated act of musical will: DNA plus the spoken frame.

    Frozen because an intent is a fact once made: the log stores it, the hash
    names it, and the renderer must be able to reproduce the same track from it.
    """

    seedPrompt: str
    era: int  # single ordinal index into ERAS
    influences: tuple[Influence, ...]  # exactly 4, weights sum to 1
    sonicPalette: SonicPalette
    vocalCharacter: VocalCharacter
    lyricalObsessions: tuple[str, ...]
    visualStyle: tuple[str, ...]
    # -- AFAR additions (not part of the DNA JSON shape) ----------------------
    line: str  # one spoken sentence, shown as the player's chat bubble
    lyrics: str  # multi-line sung lyrics; the renderer's chunk text
    rationale: str  # full reasoning; logged, never rendered
    player_id: str  # stable public id: silt | rust | keep

    # -- validation -----------------------------------------------------------

    def validate(self) -> "Intent":
        """Mirror every zod refinement in schema.ts, plus the AFAR additions.

        Collects all problems before raising so a re-prompted model sees the
        whole bill at once instead of fixing one field per round trip.
        """
        problems: list[str] = []

        if not isinstance(self.seedPrompt, str) or not self.seedPrompt.strip():
            problems.append("seedPrompt must be a non-empty string")

        if not isinstance(self.era, int) or isinstance(self.era, bool):
            problems.append("era must be an integer")
        elif not 0 <= self.era <= len(ERAS) - 1:
            problems.append(f"era must be in 0..{len(ERAS) - 1}")

        if len(self.influences) != _INFLUENCE_COUNT:
            problems.append(f"influences must have exactly {_INFLUENCE_COUNT} entries")
        for inf in self.influences:
            if not isinstance(inf.genre, str) or not inf.genre.strip():
                problems.append("influence genre must be a non-empty string")
            if not _is_number(inf.weight) or not 0 <= inf.weight <= 1:
                problems.append(f"influence weight {inf.weight!r} must be in 0..1")
        if self.influences and all(_is_number(i.weight) for i in self.influences):
            total = sum(i.weight for i in self.influences)
            if abs(total - 1) >= _WEIGHT_SUM_TOLERANCE:
                problems.append(f"influence weights must sum to 1 (got {total})")

        for axis in SONIC_AXES:
            value = getattr(self.sonicPalette, axis)
            if not _is_number(value) or not -1 <= value <= 1:
                problems.append(f"sonicPalette.{axis} must be in -1..1")
        for axis in VOCAL_AXES:
            value = getattr(self.vocalCharacter, axis)
            if not _is_number(value) or not -1 <= value <= 1:
                problems.append(f"vocalCharacter.{axis} must be in -1..1")

        for name, tags in (("lyricalObsessions", self.lyricalObsessions), ("visualStyle", self.visualStyle)):
            if any(not isinstance(t, str) or not t.strip() for t in tags):
                problems.append(f"{name} entries must be non-empty strings")
            elif len({t.lower() for t in tags}) != len(tags):
                problems.append(f"{name} tags must be unique (case-insensitive)")

        if self.player_id not in PLAYER_IDS:
            problems.append(f"player_id must be one of {PLAYER_IDS}")
        if not isinstance(self.line, str) or not self.line.strip():
            problems.append("line must be a non-empty sentence")
        if not isinstance(self.lyrics, str) or not self.lyrics.strip():
            problems.append("lyrics must be non-empty")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            problems.append("rationale must be non-empty")

        if problems:
            raise ValueError("invalid intent: " + "; ".join(problems))
        return self

    # -- serialization --------------------------------------------------------

    def to_dna_dict(self) -> dict[str, Any]:
        """The exact schema.ts CreativeDNA JSON shape — nothing AFAR-specific.

        This is what crosses the boundary to anything that speaks afar_music's
        dialect (the web mirror, the mapping oracles). line/lyrics/rationale/
        player_id deliberately stay out: generated framing (and the sung words)
        is not part of the DNA.
        """
        return {
            "seedPrompt": self.seedPrompt,
            "era": self.era,
            "influences": [{"genre": i.genre, "weight": i.weight} for i in self.influences],
            "sonicPalette": {axis: getattr(self.sonicPalette, axis) for axis in SONIC_AXES},
            "vocalCharacter": {axis: getattr(self.vocalCharacter, axis) for axis in VOCAL_AXES},
            "lyricalObsessions": list(self.lyricalObsessions),
            "visualStyle": list(self.visualStyle),
        }

    def content_hash(self) -> str:
        """sha256 of the canonical JSON of the WHOLE intent (DNA + frame).

        The line, lyrics, and rationale are part of the creative act, so two
        intents that render identically but were meant differently hash
        differently. Canonical = sorted keys, no whitespace — stable across
        processes.
        """
        full = dict(
            self.to_dna_dict(),
            line=self.line,
            lyrics=self.lyrics,
            rationale=self.rationale,
            player_id=self.player_id,
        )
        canonical = json.dumps(full, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # -- parsing --------------------------------------------------------------

    @classmethod
    def from_json(cls, text: str) -> "Intent":
        """Parse (and validate) a model reply into an Intent.

        Models wrap JSON in ```json fences and occasionally in prose; both are
        tolerated because re-prompting over formatting wastes a round trip the
        installation runs thousands of times. Anything semantically wrong still
        raises ValueError — the caller decides whether to re-prompt.
        """
        data = _loads_lenient(text)
        if not isinstance(data, Mapping):
            raise ValueError("intent JSON must be an object")
        try:
            influences = tuple(
                Influence(genre=i["genre"], weight=i["weight"]) for i in data["influences"]
            )
            palette = SonicPalette(**{axis: data["sonicPalette"][axis] for axis in SONIC_AXES})
            vocal = VocalCharacter(**{axis: data["vocalCharacter"][axis] for axis in VOCAL_AXES})
            intent = cls(
                seedPrompt=data["seedPrompt"],
                era=data["era"],
                influences=influences,
                sonicPalette=palette,
                vocalCharacter=vocal,
                lyricalObsessions=tuple(data["lyricalObsessions"]),
                visualStyle=tuple(data["visualStyle"]),
                line=data["line"],
                lyrics=data["lyrics"],
                rationale=data["rationale"],
                player_id=data["player_id"],
            )
        except (KeyError, TypeError) as err:
            raise ValueError(f"intent JSON is missing or malformed: {err!r}") from err
        return intent.validate()


def normalize_influences(influences: Sequence[Influence]) -> tuple[Influence, ...]:
    """Rescale raw (possibly unnormalized) influence weights so they sum to 1.

    Port of schema.ts normalizeInfluences: a non-positive total degrades to
    equal weights rather than raising, so a model that answers in vibes
    ("all zeros") still yields something renderable.
    """
    total = sum(i.weight for i in influences)
    if total <= 0:
        return tuple(Influence(genre=i.genre, weight=1 / len(influences)) for i in influences)
    return tuple(Influence(genre=i.genre, weight=i.weight / total) for i in influences)


# -- internals ----------------------------------------------------------------

_FENCE_OPEN = re.compile(r"^```[a-zA-Z]*\s*\n")
_FENCE_CLOSE = re.compile(r"\n?```\s*$")


def _loads_lenient(text: str) -> Any:
    """json.loads that strips markdown fences, then falls back to the outermost
    {...} span (models love a preamble)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", stripped))
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as err:
        start, end = stripped.find("{"), stripped.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise ValueError(f"intent is not valid JSON: {err}") from err


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
