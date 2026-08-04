"""Player: one AFAR musician — writing whole records, and (offline) one take.

A Player is an ensemble Agent whose creative act is an `Album`: title,
description and every song's words and DNA, written in ONE call in the
artist's own voice before any audio exists (`write_album`, docs/SPEC.md). The
model never touches the renderer and the renderer never touches the model: the
per-track `Intent` is the only thing that crosses between them, which is what
makes every track reproducible from its logged intent.

The per-round PERCEIVE -> DECIDE -> EXECUTE path (`decide`, `render_one`)
stays as the offline experiment instrument behind `AFAR_EXPERIMENT_MODE` — the
round-based history is logged and published, and the experiment still needs a
per-round decision. It is not how the live piece makes records.

`ensemble.agent.Agent.run()` deliberately does NOT publish or log — so the
logging lives in the orchestrators (`afar.run.run_album` for records,
`render_one` for the Step A single take), which run the stages and write the
perceptions/intents/artifacts rows explicitly.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from ensemble.agent import Agent, Artifact, Decision, Perception, Persona, SelfState
from ensemble.memory import EpisodicMemory
from ensemble.providers.model import Message, ModelProvider

from afar.agents.robust import staff_complete
from afar.album import MAX_TRACKS, MIN_TRACKS, Album
from afar.intent import Intent
from afar.log import JsonlLedger
from afar.mapping import lyric_line_budget
from afar.render.base import DEFAULT_DURATION_S, Renderer

#: Sung words per second of take. The established figure behind the persona
#: contract's "4-8 lines (30-60 words) for a standard 30-second take" and
#: `mapping.lyric_line_budget`'s 8-lines-per-30s density: ~45 words / 30s.
WORDS_PER_SECOND = 1.5


class Player(Agent):
    """A persona + model + renderer, closing the loop from hearing to track."""

    def __init__(
        self,
        persona: Persona,
        model: ModelProvider,
        renderer: Renderer,
        *,
        self_state: Optional[SelfState] = None,
        memory: Optional[EpisodicMemory] = None,
    ) -> None:
        super().__init__(persona, model, self_state=self_state, memory=memory)
        self.renderer = renderer
        # The seed for the NEXT render. Set by the orchestrator per round;
        # execute() only receives a Decision, so the seed rides on the player.
        self.seed: int = 0
        # The take length for the NEXT render (the Producer's session length).
        # Set by the orchestrator per set — same pattern as `seed`.
        self.duration_s: int = DEFAULT_DURATION_S

    # -- PERCEIVE --------------------------------------------------------------

    def perceive(self, context: Mapping[str, Any]) -> Perception:
        """Wrap the given context untouched.

        The boundary rule (what a player may hear mid-set: ONLY other players'
        material) is enforced where the context is BUILT, not here — a player
        never second-guesses its own ears.
        """
        return Perception(data=dict(context))

    # -- WRITE (the album: the live piece's only creative call) -----------------

    def write_album(
        self, context: Mapping[str, Any], *, n_tracks: int, duration_s: int
    ) -> Album:
        """Write a whole record in ONE call, and return it parsed and validated.

        System message = the persona's `base_prompt`, verbatim. That prompt IS
        the artist inventing itself (compiled once from Creative DNA and never
        rewritten), so nothing here re-describes who the artist is; the user
        message only says what is being made, what the artist has heard, and
        what shape the answer takes.

        `context` comes from `afar.perception.album_context.build_album_context`
        and from nowhere else — that is where the no-staff law is enforced.

        The retry ladder is `robust.staff_complete` rather than `decide`'s
        single re-prompt, for one reason: an album is the most expensive call
        the piece makes (up to six tracks of lyrics and DNA), and the failure
        that once voided a paid set was an EMPTY reply — which `decide`'s
        ladder answers by re-prompting about a parse error that never
        happened, and which `staff_complete` answers by simply asking again.
        Three model calls at most, then ValueError; the caller decides what a
        record that could not be written means.
        """
        if not MIN_TRACKS <= n_tracks <= MAX_TRACKS:
            raise ValueError(
                f"an album carries {MIN_TRACKS}-{MAX_TRACKS} tracks, asked for {n_tracks}"
            )
        artist_id = str(context.get("artist_id") or self.persona.metadata["player_id"])
        messages = [
            Message(role="system", content=self.persona.base_prompt),
            Message(
                role="user",
                content=self._album_prompt(context, n_tracks=n_tracks, duration_s=duration_s),
            ),
        ]

        def _parse(raw: str) -> Album:
            album = Album.from_json(raw, artist_id=artist_id)
            if len(album.tracks) != n_tracks:
                # The count is the budget: the conductor sized this record to
                # the audio-minutes it can afford, so a generous extra song is
                # real money and a short one is a short record.
                raise ValueError(
                    f"this record is {n_tracks} songs, not {len(album.tracks)}"
                )
            return album

        return staff_complete(
            self.model,
            messages,
            stage=f"album:{artist_id}",
            parse=_parse,
            nudge=(
                "Reply again with ONLY the album JSON object — title, "
                "description, rationale and the tracks array, nothing else."
            ),
        )

    # -- DECIDE (the offline experiment's per-round path) ----------------------

    def decide(self, perception: Perception) -> Decision:
        """Ask the model for an Intent; one re-prompt on a malformed reply.

        One retry, not more: a model that cannot produce a valid intent twice
        in a row is a bug to surface, not noise to smooth over — silently
        looping would hide broken personas from the log.
        """
        messages = [
            Message(role="system", content=self.persona.base_prompt),
            Message(role="user", content=self._decision_prompt(perception)),
        ]
        raw = self.model.complete(messages)
        try:
            intent = Intent.from_json(raw)
        except ValueError as err:
            retry = messages + [
                Message(role="assistant", content=raw),
                Message(
                    role="user",
                    content=(
                        f"That reply was not a valid Intent ({err}). "
                        "Reply again with ONLY the corrected JSON object."
                    ),
                ),
            ]
            intent = Intent.from_json(self.model.complete(retry))  # raises if still bad
        return Decision(data={"intent": intent})

    # -- EXECUTE ---------------------------------------------------------------

    def execute(self, decision: Decision) -> Artifact:
        intent: Intent = decision.data["intent"]
        result = self.renderer.render(intent, seed=self.seed, duration_s=self.duration_s)
        return Artifact(
            kind="track",
            body=str(result.path),
            metadata={
                "intent": intent.to_dna_dict(),
                "line": intent.line,
                "lyrics": intent.lyrics,
                "rationale": intent.rationale,
                "content_hash": result.content_hash,
                "prompt_sha": result.prompt_sha,
                "renderer_version": result.renderer_version,
                "render": dict(result.metadata),
            },
        )

    # -- internals -------------------------------------------------------------

    def _album_prompt(
        self, context: Mapping[str, Any], *, n_tracks: int, duration_s: int
    ) -> str:
        """The one user message that produces a whole record.

        Order matters: what is being made, the laws it is made under, where
        this artist is now, what it has heard, then the shape of the answer.
        The machine-readable TRACKS:/SECONDS PER TRACK: lines follow the staff
        prompts' idiom (ROUNDS:/ACTS:) so the offline mock can answer honestly.
        """
        lines = lyric_line_budget(duration_s * 1000)
        words = int(round(duration_s * WORDS_PER_SECOND))
        parts: list[str] = [
            f"""YOU ARE MAKING A RECORD. Not a take — a record: {n_tracks} songs that \
belong together, about {duration_s} seconds each. You write all of it now, in \
one breath, before a note of it exists: the album's title, what the record is, \
and every song's title, words and DNA.
TRACKS: {n_tracks}
SECONDS PER TRACK: {duration_s}""",
            _ALBUM_LAWS.format(n=n_tracks),
        ]
        state_line = self._self_state_line()
        if state_line:
            parts.append(state_line)
        parts.append(self._heard_block(context))
        own = context.get("own_last")
        if own:
            parts.append("YOUR LAST RECORD:\n" + _render_sleeve(own, indent="  "))
        parts.append(_answer_contract(n_tracks, duration_s, lines, words))
        return "\n\n".join(parts)

    def _heard_block(self, context: Mapping[str, Any]) -> str:
        """What other artists' records reached this one, as sleeves.

        Rendered as prose rather than a JSON dump because it is what the
        artist HEARD, and an artist reads a sleeve. The measured ear facts
        ride under the track they belong to — the sound is the fact, so it
        sits next to the words that claim it."""
        heard = context.get("heard") or []
        if not heard:
            if context.get("isolated"):
                return (
                    "WHAT YOU HAVE HEARD SINCE YOUR LAST RECORD:\n"
                    "Nothing. Nobody else's music has reached you. This record "
                    "comes out of you alone."
                )
            return (
                "WHAT YOU HAVE HEARD SINCE YOUR LAST RECORD:\n"
                "Nothing yet — no one else has put a record out. You are first."
            )
        blocks = [_render_sleeve(album, indent="  ") for album in heard]
        return (
            "WHAT YOU HAVE HEARD SINCE YOUR LAST RECORD (other artists' finished "
            "records; where a song was actually played to you, the measured facts "
            "of how it sounded are under it — trust those over what the sleeve "
            "claims). This is here to CHANGE WHAT YOU MAKE, not to give you a "
            "subject: none of these names, titles or moves may appear anywhere on "
            "your sleeve.\n\n" + "\n\n".join(blocks)
        )

    def _decision_prompt(self, perception: Perception) -> str:
        """The decide-turn user message: the Producer's direction (frame, when
        the set has one), the player's own drifted self-state, what the other
        takes measurably SOUNDED like, then the room.

        The direction is rendered apart from the peer material on purpose —
        it is the frame the session happens inside, not something another act
        played. The self-state line comes from the player itself (SelfState is
        the player's own residue, never part of the built context). The heard
        facts are rendered as their own plain-language block and stripped from
        the room's JSON dump — one fact, said once; the LOGGED context still
        carries the full heard dict, because the log records what was built,
        not how the prompt phrased it."""
        data = dict(perception.data)
        direction = data.pop("direction", None)
        heard_block = self._extract_heard(data)
        parts: list[str] = []
        if direction:
            parts.append(_render_direction(direction))
        state_line = self._self_state_line()
        if state_line:
            parts.append(state_line)
        if heard_block:
            parts.append(heard_block)
        if not data:
            parts.append(
                "The room is empty — no one has played yet. You open the set. "
                "Reply with your Intent JSON."
            )
        else:
            parts.append(
                "What you can hear right now (the other players' material):\n"
                + json.dumps(data, indent=2, default=str)
                + "\n\nMake your track. Reply with your Intent JSON."
            )
        return "\n\n".join(parts)

    def _extract_heard(self, data: dict[str, Any]) -> Optional[str]:
        """Pop each other-act entry's `heard` dict out of `data` (in place)
        and render the WHAT YOU HEARD block, or None when nothing was heard.

        First names come from the persona's addresses map — the block speaks
        the way the room does. Own take carries no heard facts by design (the
        act made it), so this only ever describes the others."""
        others = data.get("others")
        if not others:
            return None
        addresses: Mapping[str, str] = self.persona.metadata.get("addresses", {})
        lines: list[str] = []
        stripped: list[dict[str, Any]] = []
        for entry in others:
            entry = dict(entry)
            heard = entry.pop("heard", None)
            stripped.append(entry)
            if heard:
                pid = str(entry.get("player_id", ""))
                sentence = _heard_sentence(addresses.get(pid, pid), heard)
                if sentence:
                    lines.append(sentence)
        data["others"] = stripped
        if not lines:
            return None
        return (
            "WHAT YOU HEARD (measured from the audio of their last takes):\n"
            + "\n".join(lines)
        )

    def _self_state_line(self) -> Optional[str]:
        """One line of who-you-have-become, present only once drift exists:
        'Era N, stance S. You keep returning to: ...' — the logged
        persona_state rows made behavioral, still fully auditable."""
        state = self.self_state
        residue = dict(state.residue or {})
        obsessions = [str(o).strip() for o in (state.obsessions or []) if str(o).strip()]
        bits: list[str] = []
        era, stance = residue.get("era"), residue.get("stance")
        if era is not None and stance:
            bits.append(f"Era {era}, stance {stance}.")
        elif stance:
            bits.append(f"Stance {stance}.")
        if obsessions:
            bits.append("You keep returning to: " + ", ".join(obsessions) + ".")
        if not bits:
            return None
        return "WHERE YOU ARE NOW: " + " ".join(bits)


#: The tunz process, stated as law (docs/SPEC.md; tunz profile.ts, whose
#: titles are good because the title is an INPUT). One traceability law in
#: place of ban lists — the two rule-list cures each just grew a new rut — the
#: ordering rule the whole architecture exists to enforce (the title is written
#: WITH the songs, by the artist that will make the record), and the absorption
#: law: the first live sleeves annotated the listening instead of being changed
#: by it ("Evers plays four chords back to the top. I pulled the fourth"), which
#: is a reply, not a record. Nobody writes a sleeve about the record next door.
_ALBUM_LAWS = """\
HOW A RECORD GETS WRITTEN HERE.

Everything on this record is traceable to two things and nothing else: who you \
are, and what you have heard. The era you work in, what you refuse, the images \
you keep returning to, and the specific records that reached you since the last \
time — that is the entire source. Nothing arrives from outside it.

What you heard CHANGES WHAT YOU MAKE. It never becomes what you make it ABOUT. \
Being moved by a record does not mean discussing it. It means you reach for \
something you would not have reached for, or refuse something you used to \
allow, or put the weight in a different place, or build the songs out of \
different material. An artist who was changed by what they heard makes \
different work. They do not narrate the transaction.

So: on everything anyone will ever read — the album title, the description, \
every song title, and the line you say out loud about each song — you never \
name another artist, never quote or describe their songs or their titles, \
never mention what they did or kept or left out, and never frame this record \
as answering, replying to, rebutting, correcting, continuing or improving on \
anyone. No commentary on the scene. No "they went quiet so I went loud". \
Nobody writes a sleeve about the record next door. This record is about its \
own world: your places, your materials, your obsessions, the things that are \
yours alone.

Nor do you repeat another record's words back. If a sleeve you heard has a \
phrase that is plainly its own — its count, its move, the way it names its own \
trick — that phrasing is theirs and it stays out of your public text even \
unattributed. Take what it did to you, not the words it did it in.

The hearing goes in the RATIONALES — the album's and each song's. Those are \
private: they are logged and never printed on anything, and they are the right \
and only place to say plainly what reached you and what it moved you to do.

The title is written WITH the songs, not after them. You are not captioning \
finished music. You decide what this record IS, and the songs are written to \
it: each one earns its place on THIS album rather than on any other.

Nothing is named in isolation. The album title, the description and all {n} \
song titles leave your hand in the same breath — they have to cohere, and they \
have to differ. {n} titles built the same way is one title printed {n} times, \
and no song may wear the album's title.

Every title names a specific thing: keep the noun AND its particular — the \
material, the count, the place, the state it is in. Two tests: could a stranger \
draw it, and would it sit at home on somebody else's sleeve? You want yes, then \
no. Not a mood, not a verb fragment, not a bare abstract noun, no colons, no \
subtitles.

You name your own work. Nobody else in this world titles anything of yours — \
not a producer, not a critic, not an archivist. If a name is wrong it is \
yours to have got wrong.\
"""


def _render_sleeve(album: Mapping[str, Any], *, indent: str = "") -> str:
    """One album context entry as the sleeve an artist would read.

    Sleeve text only, by construction — `album_context` already whitelisted
    what may be here, and this renderer names the fields it prints, so a field
    that somehow arrived has to be printed on purpose to reach a prompt."""
    name = str(album.get("artist_name") or album.get("artist_id") or "").strip()
    title = str(album.get("title", "")).strip()
    head = f'{name} — "{title}"' if name else f'"{title}"'
    lines = [head]
    description = str(album.get("description", "")).strip()
    if description:
        lines.append(f"{indent}{description}")
    for i, track in enumerate(album.get("tracks") or [], start=1):
        song = str(track.get("title", "")).strip()
        note = str(track.get("note", "")).strip()
        lines.append(f'{indent}{i}. "{song}"' + (f" — {note}" if note else ""))
        facts = _heard_facts(track.get("heard") or {})
        if facts:
            lines.append(f"{indent}   how it sounded to you: {facts}")
    return "\n".join(lines)


def _heard_facts(heard: Mapping[str, Any]) -> str:
    """One track's measured facts as one terse clause, or "" when nothing was
    measured. Facts only, in the buckets the ear reports them in; whatever was
    not measured is simply not said."""
    facts: list[str] = []
    if heard.get("tempo_bpm") is not None:
        facts.append(f"about {round(float(heard['tempo_bpm']))} BPM")
    for key in ("loudness", "brightness"):
        label = heard.get(key)
        if label:
            facts.append(str(label) if label != "mid" else f"mid {key}")
    if heard.get("duration_s") is not None:
        facts.append(f"{round(float(heard['duration_s']))} seconds")
    moved = heard.get("moved")
    if moved == "toward_you":
        facts.append("it moved toward your last record")
    elif moved == "away_from_you":
        facts.append("it moved away from yours, closer to their own last one")
    return ", ".join(facts)


def _answer_contract(n_tracks: int, duration_s: int, lines: int, words: int) -> str:
    """The album JSON shape, stated in terms of the Intent contract the
    persona prompt already carries — the schema stays in one place, and this
    only says how {n} of them are wrapped into a record."""
    return f"""\
HOW YOU ANSWER.
Reply with exactly ONE JSON object and nothing else (a ```json fence is fine). \
It is the whole record. Each field is marked PUBLIC (it goes on the sleeve, \
where the absorption law applies in full) or PRIVATE (logged, never printed):

{{
  "title": PUBLIC — the album's title.
  "description": PUBLIC — 1-2 sentences on this record as a body of work, in \
your own voice: concrete detail from the record itself, the way a good capsule \
note reads. No praise, no pitch, and nothing about anybody else's record.
  "rationale": PRIVATE — why this record, now. A few sentences, first person, \
plain words. This is where what you heard belongs: name it, say what it moved \
you to do, say what you did instead of what you would have done. Nobody but \
the archive ever reads this, so be direct about it here.
  "tracks": exactly {n_tracks} objects, in running order:
    {{
      "title": PUBLIC — the song's title.
      "note": PUBLIC — the one line you say out loud about this song. Studio \
speech, about 90 characters, plain words, the same register as the "line" in \
your instructions. It is about the song and the room it was made in — never \
about another artist, their record, or what you are answering. This is the \
only thing anyone will read you saying about it.
      "intent": the complete Intent object your instructions describe — \
seedPrompt, era, influences, sonicPalette, vocalCharacter, lyricalObsessions, \
visualStyle, lyrics, rationale, player_id. Its "rationale" is PRIVATE, like the \
album's: what this song is doing and what in your hearing put it there. Its \
"lyrics" are PUBLIC — they are sung. The "line" field is optional here: the \
note above is what you said.
    }}
}}

Every song gets its OWN intent. The DNA is the only thing the audio is made \
from, so {n_tracks} songs sharing one palette is one song pressed {n_tracks} \
times: the record's songs should sit in the same world and still be told \
apart — a different tempo, a different weight, a different room.

LYRICS. Each "lyrics" field is the words you SING on that song, not a \
description of them: short lines separated by newlines. These takes run \
{duration_s} seconds, so aim at about {lines} lines (~{words} words) per song. \
A long take with thin words sounds thin.\
"""


def _heard_sentence(name: str, heard: Mapping[str, Any]) -> Optional[str]:
    """One act's heard dict as one terse studio sentence, e.g.
    "Roan's last take: about 98 BPM, quiet, dark, 60 seconds. It moved away
    from yours — closer to their own last one."

    Facts only, no adjectives beyond the measured buckets; whatever was not
    measured is simply not said. Returns None when there is nothing to say
    (fully degraded DSP and no movement to report)."""
    facts: list[str] = []
    if heard.get("tempo_bpm") is not None:
        facts.append(f"about {round(float(heard['tempo_bpm']))} BPM")
    if heard.get("loudness"):
        label = str(heard["loudness"])
        facts.append(label if label != "mid" else "mid loudness")
    if heard.get("brightness"):
        label = str(heard["brightness"])
        facts.append(label if label != "mid" else "mid brightness")
    if heard.get("duration_s") is not None:
        facts.append(f"{round(float(heard['duration_s']))} seconds")
    moved = heard.get("moved")
    tail: Optional[str] = None
    if moved == "toward_you":
        tail = "It moved toward yours — away from their own last one."
    elif moved == "away_from_you":
        tail = "It moved away from yours — closer to their own last one."
    if not facts and not tail:
        return None
    sentence = f"{name}'s last take:"
    if facts:
        sentence += " " + ", ".join(facts) + "."
    if tail:
        sentence += f" {tail}"
    return sentence


def _render_direction(direction: Mapping[str, Any]) -> str:
    """The Producer's session frame, rendered as prose the act reads before
    the room. Only the whitelisted frame fields ever reach this (see
    afar.perception.context.direction_frame)."""
    lines = ["THE PRODUCER'S DIRECTION FOR THIS SESSION:"]
    text = str(direction.get("text", "")).strip()
    if text:
        lines.append(text)
    notes = [str(n).strip() for n in direction.get("palette_notes", ()) if str(n).strip()]
    if notes:
        lines.append("Palette notes: " + "; ".join(notes))
    forbidden = [str(m).strip() for m in direction.get("forbidden_moves", ()) if str(m).strip()]
    if forbidden:
        lines.append("Off the table this session: " + "; ".join(forbidden))
    duration = direction.get("duration_s")
    if duration:
        lines.append(
            f"Take length this session: {int(duration)} seconds — "
            "size your lyrics to fill it."
        )
    return "\n".join(lines)


def render_one(
    player: Player,
    context: Mapping[str, Any],
    ledger: JsonlLedger,
    *,
    seed: int,
    condition: str,
) -> Artifact:
    """One player, one round: run the PDE loop and log every stage.

    This exists because Agent.run() returns only the final artifact and never
    publishes — but the log needs the intermediate facts (what was heard, what
    was intended) as first-class rows. Rows are written after EXECUTE so all
    three carry the full provenance stamp (renderer_version and prompt_sha are
    only known once the render request exists).
    """
    perception = player.perceive(context)
    decision = player.decide(perception)
    intent: Intent = decision.data["intent"]

    player.seed = seed
    artifact = player.execute(decision)

    stamps = {
        "condition": condition,
        "seed": seed,
        "renderer_version": artifact.metadata["renderer_version"],
        "prompt_sha": artifact.metadata["prompt_sha"],
    }
    intent_id = intent.content_hash()
    ledger.write(
        "perceptions",
        {**stamps, "player": intent.player_id, "context": dict(perception.data)},
    )
    ledger.write(
        "intents",
        {
            **stamps,
            "id": intent_id,
            "player": intent.player_id,
            "intent": intent.to_dna_dict(),
            "line": intent.line,
            "lyrics": intent.lyrics,
            "rationale": intent.rationale,
        },
    )
    # Content-addressed: the row's id IS the file's sha256. Path + hash only —
    # bytes live on disk, never in the log.
    ledger.write(
        "artifacts",
        {
            **stamps,
            "id": artifact.metadata["content_hash"],
            "kind": artifact.kind,
            "player": intent.player_id,
            "path": artifact.body,
            "hash": artifact.metadata["content_hash"],
            "intent_id": intent_id,
        },
    )
    player.memory.remember({"persona": player.persona.name, "artifact_kind": artifact.kind})
    return artifact
