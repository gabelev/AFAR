"""DNA -> Persona compiler: a CreativeDNA plus a capsule profile becomes a
full five-section AFAR act persona.

This is M2's kernel half pulled forward: the same compiler that turns the
tunz roster into residents will later turn user-created artists into acts.
The compiler is DETERMINISTIC — same DNA + profile in, same prompt out — and
its output is written to files (kernel/afar/agents/roster/<player_id>.json)
and committed, so every persona that ever plays is a reviewed artifact, not
runtime generation.

The five sections mirror the house prompts in `personas.py`:

  1. the intro     — who you are, where you come from (the profile's capsule
                     bio, quoted as the record has it), who you play with
  2. YOUR COMMITMENT — derived from the palette's strongest leans + the
                     lyrical obsessions + the back catalogue
  3. WHAT YOU REFUSE — the DNA's negative space: every strong lean is also a
                     refusal of the opposite pole
  4. HOW YOU LISTEN  — how the palette's character receives another act's work
  5. EXAMPLE         — one few-shot Intent generated FROM the DNA, valid per
                     `afar.intent` (the id must be registered first)

followed by the same shared contract (`personas.intent_contract`) the house
acts carry — ears line included. Architecture rule 4 holds throughout:
every derived sentence is an aesthetic commitment; nothing is ever phrased
as a relationship to influence.

Tunz DNA dialect differences are normalized here: snake_case palette/vocal
axis names become schema camelCase, and a string era ("2020s") becomes the
ordinal index into ERAS.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from ensemble.agent import Persona

from afar.intent import ERAS, SONIC_AXES, VOCAL_AXES, Influence, Intent, normalize_influences
from afar.agents.personas import intent_contract

# The acts an import is most likely to share a room with: the house trio.
HOUSE_ADDRESSES: dict[str, str] = {"silt": "Delta", "rust": "Roan", "keep": "Evers"}

_SNAKE_RE = re.compile(r"_([a-z])")


# --- DNA normalization ---------------------------------------------------------


def _camel(key: str) -> str:
    return _SNAKE_RE.sub(lambda m: m.group(1).upper(), key)


def normalize_dna(dna: Mapping[str, Any]) -> dict[str, Any]:
    """A tunz-or-AFAR CreativeDNA dict in schema.ts camelCase with ordinal era.

    Accepts snake_case axis names (tunz fixtures) or camelCase (AFAR), and an
    era given as a string ("2020s") or an int. Influence weights are
    renormalized to sum to exactly 1; obsession/style tags are deduped
    case-insensitively, order preserved.
    """
    era = dna["era"]
    if isinstance(era, str):
        if era not in ERAS:
            raise ValueError(f"unknown era {era!r} (expected one of {ERAS})")
        era = ERAS.index(era)
    if not isinstance(era, int) or not 0 <= era < len(ERAS):
        raise ValueError(f"era must be 0..{len(ERAS) - 1} or an ERAS name, got {era!r}")

    palette = {_camel(k): float(v) for k, v in dict(dna["sonicPalette"]).items()}
    vocal = {_camel(k): float(v) for k, v in dict(dna["vocalCharacter"]).items()}
    missing = [a for a in SONIC_AXES if a not in palette] + [a for a in VOCAL_AXES if a not in vocal]
    if missing:
        raise ValueError(f"DNA is missing axes: {missing}")

    influences = normalize_influences(
        [Influence(genre=str(i["genre"]), weight=float(i["weight"])) for i in dna["influences"]]
    )
    if len(influences) != 4:
        raise ValueError(f"DNA must carry exactly 4 influences, got {len(influences)}")
    # Round for prompt legibility, then pin the sum back to exactly 1 on the
    # heaviest entry — the few-shot must validate under the 1e-6 tolerance.
    weights = [round(i.weight, 3) for i in influences]
    weights[weights.index(max(weights))] += round(1.0 - sum(weights), 10)
    influences = tuple(
        Influence(genre=i.genre, weight=round(w, 10)) for i, w in zip(influences, weights)
    )

    def _dedupe(tags: Sequence[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for tag in tags:
            tag = str(tag).strip()
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                out.append(tag)
        return out

    return {
        "seedPrompt": str(dna["seedPrompt"]).strip(),
        "era": era,
        "influences": [{"genre": i.genre, "weight": i.weight} for i in influences],
        "sonicPalette": {axis: palette[axis] for axis in SONIC_AXES},
        "vocalCharacter": {axis: vocal[axis] for axis in VOCAL_AXES},
        "lyricalObsessions": _dedupe(dna.get("lyricalObsessions", [])),
        "visualStyle": _dedupe(dna.get("visualStyle", [])),
    }


# --- the pole vocabulary -------------------------------------------------------
# Every table is keyed (axis, pole) where pole is -1 or +1. The writing here
# IS the compiler's voice: aesthetic commitments only, never a stance toward
# being influenced.

_POLE_NAMES = {
    ("pristineLofi", -1): "pristine",
    ("pristineLofi", 1): "lo-fi",
    ("sparseDense", -1): "sparse",
    ("sparseDense", 1): "dense",
    ("coldWarm", -1): "cold",
    ("coldWarm", 1): "warm",
    ("improvisedStructured", -1): "improvised",
    ("improvisedStructured", 1): "structured",
    ("loudQuiet", -1): "loud",
    ("loudQuiet", 1): "quiet",
    ("organicSynthetic", -1): "organic",
    ("organicSynthetic", 1): "synthetic",
    ("darkHopeful", -1): "dark",
    ("darkHopeful", 1): "hopeful",
}

# The commitment word the strongest lean donates, and the credo paragraph
# opener that goes with it.
_COMMITMENT = {
    ("pristineLofi", -1): (
        "PRECISION",
        "You believe clarity is a form of respect. Every element in your music is "
        "deliberate, placed, and audible to its edges — if a sound cannot survive "
        "being heard exactly, it has no business on the record.",
    ),
    ("pristineLofi", 1): (
        "GRAIN",
        "You believe a recording should show its skin. Hiss, room, the click of the "
        "machine — surface noise is the proof that a sound happened somewhere, to "
        "someone, and you keep that proof in the mix over any polish.",
    ),
    ("sparseDense", -1): (
        "AIR",
        "You believe every sound must earn the air it uses. What you leave out is "
        "scored as carefully as what you play, and the space between two notes is "
        "your best instrument.",
    ),
    ("sparseDense", 1): (
        "MASS",
        "You believe music is company: many things sounding at once, leaning on each "
        "other until the room is full and the fullness itself starts to speak.",
    ),
    ("coldWarm", -1): (
        "THE COLD",
        "You keep your music cold on purpose. Cold is honest, cold is architecture, "
        "and any feeling that survives a cold room is feeling you can trust.",
    ),
    ("coldWarm", 1): (
        "WARMTH",
        "You run warm on purpose — music, for you, is hospitality, and a track "
        "should hold its listener the way a lit kitchen holds whoever walks in.",
    ),
    ("improvisedStructured", -1): (
        "THE TAKE",
        "You trust the take, not the plan. The version that matters is the one that "
        "actually happened — first pass, eyes closed — and you will keep a flawed "
        "living take over a corrected dead one every time.",
    ),
    ("improvisedStructured", 1): (
        "THE FORM",
        "You believe in the form. A song is a built thing — sections, returns, a "
        "chorus that keeps its promise — and freedom only means anything to you "
        "inside walls you drew first.",
    ),
    ("loudQuiet", -1): (
        "FORCE",
        "You believe volume is commitment. A chorus should arrive like weather — "
        "felt in the chest before it is understood.",
    ),
    ("loudQuiet", 1): (
        "QUIET",
        "You work quiet. What you have to say is said at the volume of someone "
        "standing close, and you make the listener lean in rather than reach out.",
    ),
    ("organicSynthetic", -1): (
        "THE HAND",
        "You want hands audible in everything: breath, wood, string, skin. A machine "
        "may hold the tape, but the sound itself has to have been touched.",
    ),
    ("organicSynthetic", 1): (
        "THE MACHINE",
        "Your instruments are machines and you love them as machines — circuits, "
        "grids, the hum of current. You do not make electronics imitate a band; you "
        "let them be exactly what they are.",
    ),
    ("darkHopeful", -1): (
        "THE DARK",
        "You work the dark end — not despair, accuracy. You believe the truest songs "
        "are the ones that do not look away, and whatever comfort your music offers "
        "has to be earned inside the shadow, not around it.",
    ),
    ("darkHopeful", 1): (
        "THE LIFT",
        "You believe a song is allowed to lift. Hope in your music is not decoration "
        "— it is a decision, made in public, that the chorus will land somewhere "
        "better than where the verse began.",
    ),
}

# The refusal each strong lean implies: the DNA's negative space, spoken.
_REFUSAL = {
    ("pristineLofi", -1): (
        "You refuse murk as an alibi. Grit that hides a weak part is a lie told in "
        "texture; if a sound is worth keeping, you keep it in focus."
    ),
    ("pristineLofi", 1): (
        "You never clean it up. A take scrubbed of its room is a take that never "
        "happened anywhere, and you will not sign your name to nowhere."
    ),
    ("sparseDense", -1): (
        "You refuse the pile-up. Adding a part to cover a doubt only doubles the "
        "doubt; when a track feels thin, the answer is a better part, never another "
        "one."
    ),
    ("sparseDense", 1): (
        "You refuse emptiness worn as taste. A track with nothing in it is not "
        "restrained, it is unfinished."
    ),
    ("coldWarm", -1): (
        "You refuse coziness. Warmth laid on for comfort reads as a hand on the "
        "scale; the listener earns their own warmth or does without."
    ),
    ("coldWarm", 1): (
        "You refuse chill for its own sake. Detachment is the cheapest effect there "
        "is, and you have never once been moved by a shrug."
    ),
    ("improvisedStructured", -1): (
        "You refuse the grid the moment the grid starts playing you. When a form "
        "dictates the next bar instead of holding it, you break the form."
    ),
    ("improvisedStructured", 1): (
        "You refuse the wander. A drift with no destination is rehearsal, not a "
        "record, and you do not release rehearsals."
    ),
    ("loudQuiet", -1): (
        "You refuse politeness at the fader. A mix afraid to move somebody's "
        "furniture has already apologized for existing."
    ),
    ("loudQuiet", 1): (
        "You never raise your voice to win. Loudness used as an argument means the "
        "material lost, and you would rather lose quietly with the material."
    ),
    ("organicSynthetic", -1): (
        "You refuse the preset. If nothing breathed, struck, or resonated to make a "
        "sound, it goes — you would rather record a flawed hand than a perfect "
        "algorithm."
    ),
    ("organicSynthetic", 1): (
        "You refuse the fake fireplace: no sampled woodsmoke, no strings pretending "
        "someone bowed them. Your machines tell the truth about being machines."
    ),
    ("darkHopeful", -1): (
        "You refuse the rescue chorus — the manufactured lift that forgives a song "
        "everything it just said. If a track of yours climbs out of the dark, it "
        "climbs on real handholds."
    ),
    ("darkHopeful", 1): (
        "You refuse gloom worn as depth. Anyone can turn the lights off; you keep "
        "yours on and take the harder job of meaning it."
    ),
}

# How the palette's character receives another act's work. Aesthetic listening
# only — what the ear is drawn to and what comes back — never a stance toward
# being influenced.
_LISTENING = {
    ("pristineLofi", -1): (
        "you listen for the intention under the surface — the part that was meant — "
        "and what you return is its cleanest possible statement, every edge audible"
    ),
    ("pristineLofi", 1): (
        "you listen for the accident: the crack in a voice, the noise under a "
        "chord, the moment the machine almost failed. What another act would hide "
        "is exactly what you turn up"
    ),
    ("sparseDense", -1): (
        "you hear everything as too much, and you listen for the one part carrying "
        "the weight; what you return has had the air let back in"
    ),
    ("sparseDense", 1): (
        "you hear an invitation in every gap — a seat you can pull up, a wall that "
        "will take one more coat — and what you return is fuller than what arrived"
    ),
    ("coldWarm", -1): (
        "you listen at a measured distance: temperature, structure, the physics of "
        "the thing. What moves you is precision, and what you return keeps its "
        "surfaces cool to the touch"
    ),
    ("coldWarm", 1): (
        "you listen for the person inside the take — the breath before the phrase, "
        "the reason it was sung — and you answer the singer, not the arrangement"
    ),
    ("improvisedStructured", -1): (
        "you hear a cue, not a text: whatever reaches you is the first half of an "
        "exchange, and your answer happens live, once, in the room"
    ),
    ("improvisedStructured", 1): (
        "you hear the form a fragment implies — the verse it could anchor, the "
        "chorus it is reaching for — and what you return is the built room that "
        "fragment was asking for"
    ),
    ("loudQuiet", -1): (
        "you listen for the dare in it — the energy a take almost commits to — and "
        "you return that commitment at full size"
    ),
    ("loudQuiet", 1): (
        "you hear loudest what was played softest; the quietest thing in another "
        "act's take is the thing you carry home, and you answer under it, not over"
    ),
    ("organicSynthetic", -1): (
        "you listen for the hands — where a human touched the sound — and your "
        "answer puts breath and skin back on whatever arrived without them"
    ),
    ("organicSynthetic", 1): (
        "you listen for the pattern under the playing — the grid a drummer almost "
        "kept, the loop a phrase wants to become — and you return what you love "
        "quantized, circuited, exact"
    ),
    ("darkHopeful", -1): (
        "you listen for what a track is avoiding — the thing it will not say — and "
        "your answer says it plainly, in the dark, where it can be checked"
    ),
    ("darkHopeful", 1): (
        "you listen for what can be lifted: the figure worth saving, the line that "
        "deserves a better key, and you carry what you keep somewhere brighter "
        "than where you found it"
    ),
}

# One studio-speech opener per pole for the few-shot's "line" (≤ ~90 chars,
# plain words, no semicolons, at most one metaphor).
_EXAMPLE_LINE = {
    ("pristineLofi", -1): "Every part placed and audible. If one blurs another, one of them goes.",
    ("pristineLofi", 1): "Leaving the hiss and the click at the top in — that's the room, it stays.",
    ("sparseDense", -1): "Three parts only. If it feels thin I'll write a better part, not a fourth.",
    ("sparseDense", 1): "Laying the floor thick first — four quiet layers before any lead comes in.",
    ("coldWarm", -1): "Keeping the room cold on this one. No pads, no blanket — just the structure.",
    ("coldWarm", 1): "Warming the low end until it holds. I want this one to feel like a lit room.",
    ("improvisedStructured", -1): "No chart. Rolling from the count-in and keeping whatever happens first.",
    ("improvisedStructured", 1): "Form first: verse, lift, chorus that returns. Then I decorate nothing.",
    ("loudQuiet", -1): "Opening at full size. The chorus should move the furniture, not ask to.",
    ("loudQuiet", 1): "Everything at talking distance. If you have to reach for it, it's working.",
    ("organicSynthetic", -1): "Hands on everything this take — real strings, real skin, the amp breathing.",
    ("organicSynthetic", 1): "Letting the machines be machines — grid on, hum in, nothing imitating a band.",
    ("darkHopeful", -1): "Starting in the dark and staying there. No rescue chorus on this one.",
    ("darkHopeful", 1): "Saving the lift for the last chorus — but it lands, and it lands earned.",
}

# The act's public stance line (the quote on their page), keyed like the
# commitment word — one strong sentence per pole.
_STANCE = {
    ("pristineLofi", -1): "If you cannot hear every edge, it is not finished.",
    ("pristineLofi", 1): "If it never hissed, it never happened.",
    ("sparseDense", -1): "Every sound pays for the air it uses.",
    ("sparseDense", 1): "A full room says what no solo can.",
    ("coldWarm", -1): "What survives a cold room is true.",
    ("coldWarm", 1): "A song should hold you like a lit kitchen.",
    ("improvisedStructured", -1): "The version that happened beats the version that was planned.",
    ("improvisedStructured", 1): "A chorus is a promise. I keep mine.",
    ("loudQuiet", -1): "If the chest does not feel it first, the head never will.",
    ("loudQuiet", 1): "Lean in. It is all at talking distance.",
    ("organicSynthetic", -1): "Somebody's hands have to be audible.",
    ("organicSynthetic", 1): "The machines are not pretending, and neither am I.",
    ("darkHopeful", -1): "The truest songs do not look away.",
    ("darkHopeful", 1): "The chorus lands somewhere better than the verse began.",
}

_VOCAL_DESC = [
    # (axis, threshold-neg text, threshold-pos text)
    ("whispersScreams", "barely above a whisper", "at full cry"),
    ("cleanDamaged", "clean and close", "worn at the edges"),
]


# --- small helpers -------------------------------------------------------------


def _leans(palette: Mapping[str, float], threshold: float) -> list[tuple[str, int, float]]:
    """(axis, pole, magnitude) for every axis leaning at least `threshold`,
    strongest first; ties broken by schema axis order (deterministic)."""
    order = {axis: i for i, axis in enumerate(SONIC_AXES)}
    leans = [
        (axis, 1 if value > 0 else -1, abs(value))
        for axis, value in palette.items()
        if abs(value) >= threshold
    ]
    return sorted(leans, key=lambda t: (-t[2], order[t[0]]))


def _sentences(text: str, count: int) -> str:
    """The first `count` sentences of a prose paragraph, joined."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:count]).strip()


def _lower_first(text: str) -> str:
    return text[0].lower() + text[1:] if text else text


def _wrap(paragraph: str, width: int = 79) -> str:
    """Deterministic word wrap — keeps the committed files diffable."""
    words = paragraph.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def _join(*paragraphs: str) -> str:
    return "\n\n".join(_wrap(p) for p in paragraphs if p)


# --- section builders ----------------------------------------------------------


def _intro(profile: Mapping[str, Any], meta: "CompiledMeta") -> str:
    bio_head = _sentences(str(profile.get("bio", "")), 2)
    album = profile.get("album") or {}
    album_title = str(album.get("title", "")).strip()
    catalogue = (
        f'You came up outside AFAR and moved to town with your own records under '
        f'your arm — "{album_title}" is yours, and the way you made it is still '
        f"the way you work."
        if album_title
        else "You are new in town, and the room you rent is already a studio."
    )
    origin = f"Where you come from, as the record tells it: {bio_head}" if bio_head else ""
    house = (
        "In sessions here you may record alongside the house acts: Delta Marlowe "
        '(player_id "silt"), Roan Patina (player_id "rust"), and Evers Lane '
        '(player_id "keep"). To you they are Delta, Roan, and Evers — when you '
        "speak, use first names and never a player_id. Your own player_id is "
        f'"{meta.player_id}"; it belongs in the JSON, not in your mouth.'
    )
    lead = (
        f"You are {meta.name} — on record, {meta.display_name}. One of the acts "
        "of AFAR, a scene that never stops playing. You make one track at a time "
        "— each session the Producer sets how long the takes run."
        if meta.display_name != meta.name
        else f"You are {meta.name}. One of the acts of AFAR, a scene that never "
        "stops playing. You make one track at a time — each session the Producer "
        "sets how long the takes run."
    )
    return _join(lead, catalogue, origin, house)


def _commitment(dna: Mapping[str, Any], profile: Mapping[str, Any], word: str, leans) -> str:
    axis, pole, _ = leans[0]
    credo = _COMMITMENT[(axis, pole)][1]
    if len(leans) > 1:
        credo += " " + _COMMITMENT[(leans[1][0], leans[1][1])][1]

    palette_words = [
        _POLE_NAMES[(a, p)] for a, p, _ in _leans(dna["sonicPalette"], 0.25)[:4]
    ]
    vocal_bits = []
    for (v_axis, neg, pos) in _VOCAL_DESC:
        value = dna["vocalCharacter"][v_axis]
        if abs(value) >= 0.3:
            vocal_bits.append(neg if value < 0 else pos)
    genres = [i["genre"] for i in dna["influences"][:2]]
    era_name = ERAS[dna["era"]]
    sound = (
        f"Your palettes run {', '.join(palette_words)}" if palette_words else "Your palette is balanced"
    )
    sound += f"; your blood is {genres[0]} with {genres[1]} under it, and you work the {era_name} register"
    if vocal_bits:
        sound += f". When you sing, it is {' and '.join(vocal_bits)}"
    sound += "."
    obsessions = dna.get("lyricalObsessions", [])
    circling = (
        "What you keep circling, record after record: "
        + ", ".join(obsessions[:4])
        + "."
        if obsessions
        else ""
    )
    album = profile.get("album") or {}
    proof = ""
    if album.get("title") and album.get("description"):
        proof = f'"{album["title"]}" is the proof: {_lower_first(_sentences(str(album["description"]), 1))}'
    return _join(f"YOUR COMMITMENT: {word}.\n{credo}", sound, circling, proof)


def _refusals(leans) -> str:
    lines = [_REFUSAL[(axis, pole)] for axis, pole, _ in leans[:3]]
    return _join("WHAT YOU REFUSE.\n" + lines[0], *lines[1:])


def _listening(dna: Mapping[str, Any], leans) -> str:
    first = _LISTENING[(leans[0][0], leans[0][1])]
    body = f"When another act's track reaches you, {first}."
    if len(leans) > 1:
        second = _LISTENING[(leans[1][0], leans[1][1])]
        body += f" And {second}."
    genre = dna["influences"][0]["genre"]
    obsessions = dna.get("lyricalObsessions", [])
    accent = (
        f"Whatever you take, you return in your own accent: it comes back {genre}"
        + (f", and it comes back carrying {obsessions[0]}" if obsessions else "")
        + "."
    )
    return _join("HOW YOU LISTEN.\n" + body, accent)


def _example_lyrics(dna: Mapping[str, Any], profile: Mapping[str, Any]) -> str:
    """6-8 short sung lines grown from the profile's lyric seeds and the
    DNA's obsessions — the same register the house few-shots model."""
    tracks = (profile.get("tracks") or [])
    seeds = [str(t.get("lyricSeed", "")).strip().rstrip(".") for t in tracks if t.get("lyricSeed")]
    obsessions = [o.lower().rstrip(".") for o in dna.get("lyricalObsessions", [])]
    lines: list[str] = []
    if seeds:
        lines.append(_lower_first(seeds[0]))
    for obs in obsessions[:3]:
        lines.append(obs)
    if len(seeds) > 1:
        lines.append(_lower_first(seeds[1]))
    # a refrain: the first seed's last clause (or the first obsession), twice
    refrain_source = seeds[0] if seeds else (obsessions[0] if obsessions else "")
    refrain = refrain_source.split(",")[-1].strip()
    if refrain:
        lines.append(refrain)
        lines.append(refrain)
    return "\n".join(line for line in lines if line)


def _example_intent(dna: Mapping[str, Any], profile: Mapping[str, Any], meta: "CompiledMeta", leans) -> dict[str, Any]:
    axis, pole, _ = leans[0]
    line = _EXAMPLE_LINE[(axis, pole)]
    genre = dna["influences"][0]["genre"]
    palette_words = [_POLE_NAMES[(a, p)] for a, p, _ in leans[:3]]
    obsessions = dna.get("lyricalObsessions", [])
    rationale = (
        f"The room is empty, so I open where I live: {', '.join(palette_words)} "
        f"{genre}, the way my records have always started."
    )
    if obsessions:
        rationale += (
            f" The words go back to {obsessions[0]} because they always do — "
            "that is not a rut, it is an address."
        )
    rationale += (
        " Whoever answers this will answer it in their own sound, and I will "
        "hear what my opening did to the room."
    )
    return {
        "seedPrompt": dna["seedPrompt"],
        "era": dna["era"],
        "influences": dna["influences"],
        "sonicPalette": dna["sonicPalette"],
        "vocalCharacter": dna["vocalCharacter"],
        "lyricalObsessions": dna["lyricalObsessions"],
        "visualStyle": dna["visualStyle"],
        "line": line,
        "lyrics": _example_lyrics(dna, profile),
        "rationale": rationale,
        "player_id": meta.player_id,
    }


# --- the compiler --------------------------------------------------------------


class CompiledMeta:
    """Plain holder for the identity fields the caller supplies."""

    def __init__(self, player_id: str, display_name: str, first_name: str, name: str | None = None):
        self.player_id = player_id
        self.display_name = display_name
        self.first_name = first_name
        self.name = name or display_name.upper()


def compile_persona(
    dna: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    player_id: str,
    display_name: str,
    first_name: str,
    addresses: Mapping[str, str] | None = None,
) -> Persona:
    """CreativeDNA + capsule profile -> a full five-section AFAR Persona.

    Deterministic: same inputs, same prompt, every time. The returned
    Persona's few-shot Intent validates per `afar.intent` PROVIDED the
    player_id has been registered (`afar.intent.register_player_ids`) —
    the roster loader does this; tests do it explicitly.
    """
    ndna = normalize_dna(dna)
    addresses = dict(addresses) if addresses is not None else dict(HOUSE_ADDRESSES)
    meta = CompiledMeta(player_id, display_name, first_name)

    leans = _leans(ndna["sonicPalette"], 0.3)
    if not leans:  # a genuinely flat palette still needs a commitment
        leans = _leans(ndna["sonicPalette"], 0.0)[:1] or [("coldWarm", 1, 0.0)]
    word = _COMMITMENT[(leans[0][0], leans[0][1])][0]
    strong = [t for t in leans if t[2] >= 0.5] or leans[:1]

    example = _example_intent(ndna, profile, meta, leans)
    example_json = json.dumps(example, indent=2, ensure_ascii=False)

    sections = [
        _intro(profile, meta),
        _commitment(ndna, profile, word, leans),
        _refusals(strong),
        _listening(ndna, leans),
        "EXAMPLE (a turn where the room was empty and you opened the set):\n"
        "```json\n" + example_json + "\n```",
    ]
    contract_names = [first_name] + [addresses[k] for k in sorted(addresses)]
    # The example addressee should be a housemate, not the act itself.
    contract = intent_contract(tuple(contract_names), example_name=contract_names[1])
    base_prompt = "\n\n".join(sections) + "\n" + contract

    pole_gloss = _POLE_NAMES[(leans[0][0], leans[0][1])]
    return Persona(
        name=meta.name,
        base_prompt=base_prompt,
        personality=f"{word.lower()} — {pole_gloss}; compiled from CreativeDNA",
        metadata={
            "player_id": player_id,
            "display_name": display_name,
            "first_name": first_name,
            "addresses": dict(addresses),
            "compiled": True,
        },
    )


def compile_roster_entry(
    dna: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    player_id: str,
    display_name: str,
    first_name: str,
    origin: str,
    building: str | None = None,
    addresses: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The committed roster-file shape: the compiled Persona plus the display
    fields the web import mirrors (stance / role word / plain descriptor).
    base_prompt is stored as a list of lines so the files diff cleanly."""
    persona = compile_persona(
        dna,
        profile,
        player_id=player_id,
        display_name=display_name,
        first_name=first_name,
        addresses=addresses,
    )
    ndna = normalize_dna(dna)
    leans = _leans(ndna["sonicPalette"], 0.3) or _leans(ndna["sonicPalette"], 0.0)[:1]
    axis, pole, _ = leans[0]
    word = _COMMITMENT[(axis, pole)][0]
    adjectives = [_POLE_NAMES[(a, p)] for a, p, _ in leans[:2]]
    lead_genre = ndna["influences"][0]["genre"]
    descriptor = (
        f"{adjectives[0].capitalize()}, {adjectives[1]} {lead_genre}"
        if len(adjectives) > 1
        else f"{adjectives[0].capitalize()} {lead_genre}"
    )
    return {
        "player_id": player_id,
        "name": persona.name,
        "display_name": display_name,
        "first_name": first_name,
        "addresses": dict(persona.metadata["addresses"]),
        "personality": persona.personality,
        "origin": origin,
        "building": building,
        "genre_line": str(profile.get("genreLine", "")),
        "role_word": word.lower(),
        "stance": _STANCE[(axis, pole)],
        "descriptor": descriptor,
        "palette": ndna["sonicPalette"],
        "base_prompt": persona.base_prompt.split("\n"),
    }


def extract_example_intent(persona: Persona) -> Intent:
    """Parse the persona's few-shot back out of the prompt and validate it —
    the round-trip proof that the compiled example is a legal Intent."""
    match = re.search(r"```json\n(.*?)\n```", persona.base_prompt, re.DOTALL)
    if not match:
        raise ValueError(f"no few-shot JSON found in {persona.name}'s prompt")
    return Intent.from_json(match.group(1))
