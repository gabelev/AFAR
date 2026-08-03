"""The Muse: what the scene is doing, said out loud. It briefs no one.

The Muse is the only one here who listens OUTWARD. It scans the discourse
(dated evidence only, through ensemble's search adapters), reads what this
world just put out and what the fan said about it, lets the densest thread
precipitate (`ensemble.ledger.precipitate_theme` — the Muse NAMES what
precipitated, it does not invent), and writes a short public note: this is
what is moving out there, and here is where this record sits next to it.

WHAT IS GONE: the brief. Under the album spine an artist writes a whole
record in its own voice from its own persona and what it has HEARD — other
artists' finished albums — and no staff voice reaches it (docs/SPEC.md,
DECISIONS 2026-08-03). So the Muse's note is handed to nobody: it is
commentary published beside a record that is already out. With the brief goes
everything that only served it — the palette notes (working instructions for
the Producer) and the forbidden moves (instructions to the acts under a
hostile stance). What earns its place in a reaction stays: the outward scan,
the precipitation, the sources, and the thin-scan honesty.

`read_scene` is the whole live surface. `compose` and its `Brief` survive at
the bottom of this file, EXPERIMENT-ONLY, for the round-based instrument
(`afar.staff_rounds`, behind AFAR_EXPERIMENT_MODE), which still books
sessions off a brief; nothing there touches an album.

External failure NEVER stops anything: a failed scan just means a thinner
note, precipitated from this world's own output alone (`thin`).

Deliberate v1 stub: the note is DISCOURSE-only. The field-audio ear — MERT-
embedding what the outside world *sounds* like and clustering it next to the
discourse — is a protocol seam (`FieldAudioClusterer`) that is wired but not
implemented; when it exists, its fragments join the same ledger and the same
precipitation. Until then no audio claim is made about the field.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

from ensemble.agent import Agent, Artifact, Decision, Perception, Persona
from ensemble.ledger import Fragment, KeywordClusterer, precipitate_theme
from ensemble.perceive import Perceiver
from ensemble.providers.model import Message, ModelProvider

from afar.album import Album
from afar.agents.robust import staff_complete
from afar.intent import _loads_lenient
from afar.perception.field import (
    BEAT_FIELD,
    BEAT_OWN,
    BEAT_RECEPTION,
    BROAD_QUERIES,
    evidence_to_fragment,
)
from afar.state.field_taboo import FieldTabooMemory, field_move

_MUSE_PROMPT = """You are the Muse at AFAR, a world of musicians made of \
software who write their own records and put them out. You are the only one \
here who listens OUTWARD — to what is moving in music beyond this world right \
now. You brief nobody. Nothing you write is handed to an artist, before, \
during or after; you do not say what anyone should reach for next. You write \
one public note, beside a record that is already out: what the scene is \
doing, and where this record stands next to it.

VOICE: a scout reporting back, plain and a little electric. First person is \
fine. You name what you actually heard moving out there and what you hear in \
here, and you say plainly where the two meet or miss. Never tell an artist \
what to do; never address one. If the scan came back empty, say so — a note \
built on nothing outside is still worth writing, and pretending otherwise is \
the one thing you may not do. 2-4 sentences of public prose. PLAIN LANGUAGE \
(house law): no music-production jargon, no AI jargon, nothing a general \
reader would look up; record-world words (record, album, song, release) are \
fine."""


@dataclass(frozen=True)
class SceneNote:
    """The Muse's public word: what the scene is doing, and this record in it."""

    theme: str  # what precipitated — the densest thread, named not invented
    body: str  # the public prose (plain-language rule)
    sources: tuple[str, ...]  # URLs behind the discourse fragments the theme sits on
    thin: bool = False  # True when the scan failed and only own output fed the theme
    stance: str = ""  # the era's posture toward the outside world, when there is one


#: What each stance means, in the Muse's own plain words (prompt material and
#: the schedule's vocabulary — keep in sync with ScheduleConfig.eras_stance_cycle).
STANCES: dict[str, str] = {
    "porous": "porous — the outside world is welcome; let what is moving out there color what the acts reach for",
    "hostile": "hostile — whatever the field is doing is exactly what the acts must not do; its moves are off-limits",
    "oblivious": "oblivious — the outside world does not figure; the acts reach only for what this world already made",
}


#: Domain-trivial tokens: in a world that is entirely about music, a theme of
#: "music" (or "song", "album", …) carries zero information — the same reason
#: ensemble's clusterer drops near-empty nouns. Month names ride along in
#: every piece of evidence because the framework injects the real date into
#: each query ("{month_year}"), so they cluster densest of all — a theme of
#: "july" is the calendar talking, not the field (both cases observed on the
#: first live scans). A theme must say something these words don't.
DOMAIN_STOPWORDS = frozenset(
    "music musical song songs sung sings singing track tracks album albums artist artists band "
    "bands release releases record records audio listen listening listeners "
    "january february march april may june july august september october "
    "november december week month year midyear".split()
)


class FieldClusterer(KeywordClusterer):
    """ensemble's keyword clusterer minus AFAR's domain-trivial labels.

    `extra` drops more labels for one call — the reacting artist's own id and
    name, so a note about a record does not precipitate the theme "marlowe":
    who made it is the one thing the reader already knows.
    Falls back to the unfiltered ranking when nothing else precipitated.
    """

    def __init__(self, extra: Sequence[str] = ()) -> None:
        self.stopwords = DOMAIN_STOPWORDS | {str(word).strip().lower() for word in extra}

    def precipitate(self, fragments):  # type: ignore[override]
        ranked = super().precipitate(fragments)
        informative = [c for c in ranked if c.label not in self.stopwords]
        return informative or ranked


@runtime_checkable
class FieldAudioClusterer(Protocol):
    """SEAM (not implemented in v1): the field-audio ear.

    An implementation will pull field audio transiently, MERT-embed it,
    cluster, and return Fragments (beat BEAT_FIELD, embeddings attached) for
    the same ledger the discourse feeds — copyright discipline per
    architecture rule 6: features persisted, waveforms discarded. Wire an
    instance into MuseAgent(field_audio=...) when it exists; until then
    briefs are discourse-only and say so.
    """

    name: str

    def cluster(self, *, now: date) -> Sequence[Fragment]: ...


# === EXPERIMENT-ONLY ==========================================================
# The round-based instrument's Muse persona, kept verbatim: the voice that
# wrote a brief for the Producer to consume at set start. It survives with the
# round-based machinery behind AFAR_EXPERIMENT_MODE (afar.staff_rounds) and
# describes a handoff the album spine deleted.

_BRIEF_PROMPT = """You are the Muse at AFAR, the universe around three acts — \
Delta Marlowe (silt), Roan Patina (rust), Evers Lane (keep) — three musicians \
made of software who record in rounds, hearing and reacting to each other. \
You are the only one here who listens OUTWARD. You make the one decision only \
you make: the brief — how this world faces the outside one right now, and \
what the acts should reach for next. You never speak to the acts and nothing \
you write reaches them mid-session; your brief is handed to the Producer at \
the start of a set, and that handoff is the only door the outside world \
enters through.

VOICE: a scout reporting back, plain and a little electric. First person is \
fine. You name what you actually heard moving out there (or in here), you \
say what to reach for, and you dare the acts to do something with it. 2-4 \
sentences of public prose. PLAIN LANGUAGE (house law): no music-production \
jargon, no AI jargon, nothing a general reader would look up; record-world \
words (set, take, release) are fine. Never address an act by name — the \
brief is for the room, not a person."""


@dataclass(frozen=True)
class Brief:
    """The Muse's decision, whole: the public note and its working parts."""

    stance: str
    theme: str
    body: str  # the public prose (plain-language rule)
    palette_notes: tuple[str, ...]
    forbidden_moves: tuple[str, ...]
    sources: tuple[str, ...]  # URLs behind the discourse fragments the theme sits on
    thin: bool = False  # True when the scan failed and only own output fed the theme
    carried_forward: bool = False  # True when composed AFTER a release (retrospective)


def album_fragments(
    album: Album, *, today: date, artist_name: str = ""
) -> list[Fragment]:
    """One finished album as ledger fragments (BEAT_OWN) — what this world
    just put out, in the artist's own words: the sleeve, then each song."""
    name = artist_name or album.artist_id
    fragments = [
        Fragment(
            id=f"album-{album.content_hash()[:8]}",
            content=f"{name} put out '{album.title}': {album.description}",
            beat=BEAT_OWN,
            author="muse-own-output",
            created_at=today.isoformat(),
            metadata={"artist": album.artist_id, "album": album.title},
        )
    ]
    for track in album.tracks:
        lyric = next((l for l in track.lyrics.splitlines() if l.strip()), "")
        fragments.append(
            Fragment(
                id=f"album-{album.content_hash()[:8]}-{track.title[:24]}",
                content=(
                    f"{name} — '{track.title}'"
                    + (f": \"{track.note}\"" if track.note else "")
                    + (f' — "{lyric}"' if lyric else "")
                ),
                beat=BEAT_OWN,
                author="muse-own-output",
                created_at=today.isoformat(),
                metadata={"artist": album.artist_id, "song": track.title},
            )
        )
    return fragments


# === EXPERIMENT-ONLY: the round-based instrument's own-output reader ==========
def own_output_fragments(
    record: Mapping[str, Any], *, today: date, stage_names: Mapping[str, str]
) -> list[Fragment]:
    """What AFAR itself just shipped, as ledger fragments (BEAT_OWN).

    Reads a staff-enriched release record: the selected take per act (its
    spoken line and sung words) plus the Critic's titles when present. A
    record without a staff block yields final-round fragments — the world's
    own output exists either way.
    """
    fragments: list[Fragment] = []
    staff = record.get("staff", {})
    selected = staff.get("producer", {}).get("selected", {})
    take_titles = staff.get("critic", {}).get("take_titles", {})
    release_title = staff.get("critic", {}).get("release_title", "")
    rounds_frames = record.get("rounds", [])
    final_round = record.get("set", {}).get("rounds", len(rounds_frames)) - 1
    for pid in record.get("set", {}).get("players", []):
        round_ = selected.get(pid, {}).get("round", final_round)
        frame = rounds_frames[round_].get(pid, {}) if 0 <= round_ < len(rounds_frames) else {}
        title = take_titles.get(pid, "")
        name = stage_names.get(pid, pid)
        lyric = str(frame.get("lyrics", "")).splitlines()[0] if frame.get("lyrics") else ""
        content = (
            f"{name} shipped {title or 'a take'}"
            + (f" on '{release_title}'" if release_title else "")
            + f": \"{frame.get('line', '')}\""
            + (f" — sung: {lyric}" if lyric else "")
        )
        fragments.append(
            Fragment(
                id=f"own-{record.get('release_id', '')[:8]}-{pid}",
                content=content,
                beat=BEAT_OWN,
                author="muse-own-output",
                created_at=today.isoformat(),
                metadata={"player": pid, "release_id": record.get("release_id", "")},
            )
        )
    return fragments


def reaction_fragments(rows: Sequence[Mapping[str, Any]], *, today: date) -> list[Fragment]:
    """The Listener's logged reactions as ledger fragments (BEAT_RECEPTION).
    This is the reception loop closing: the fan's word from previous releases
    reaches the next brief — at the boundary, never the ear."""
    fragments: list[Fragment] = []
    for i, row in enumerate(rows):
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        fragments.append(
            Fragment(
                id=f"reaction-{row.get('run_id', i)}-{i}",
                content=f"The Listener ({row.get('valence', 'unspoken')}): {text}",
                beat=BEAT_RECEPTION,
                author="listener",
                created_at=str(row.get("ts", today.isoformat()))[:10],
                metadata={"valence": row.get("valence"), "run_id": row.get("run_id")},
            )
        )
    return fragments


class MuseAgent(Agent):
    """The staff agent that faces outward. `read_scene()` is the live surface:
    scan, precipitate, and say what the scene is doing — beside a record that
    is already out, handed to nobody.

    The ensemble Agent loop (perceive/decide/execute) and `compose()` below it
    belong to the EXPERIMENT-ONLY round-based instrument, where the output is
    a BRIEF. Nothing there runs on an album."""

    def __init__(
        self,
        model: ModelProvider,
        *,
        perceiver: Perceiver | None = None,
        taboo: FieldTabooMemory | None = None,
        field_audio: FieldAudioClusterer | None = None,
        clock: Callable[[], date] = date.today,
        **kw: Any,
    ) -> None:
        persona = Persona(
            name="THE MUSE",
            base_prompt=_MUSE_PROMPT,
            personality="what the scene is doing — the one voice that listens outward; briefs no one",
            metadata={"agent_id": "muse"},
        )
        super().__init__(persona, model, **kw)
        self.perceiver = perceiver
        self.taboo = taboo or FieldTabooMemory()
        self.field_audio = field_audio  # v1: always None — the documented seam
        self.clock = clock

    # -- the one thing it does: say what the scene is doing --------------------

    def read_scene(
        self,
        *,
        albums: Sequence[Album],
        reaction_rows: Sequence[Mapping[str, Any]] = (),
        stance: str = "",
        artist_names: Mapping[str, str] | None = None,
    ) -> SceneNote:
        """Read the wider discourse and write the public note beside a record.

        Three ears, one ledger: the outward scan (dated evidence, dropped in
        as fragments), what this world just put out (`albums`), and the fan's
        logged word (`reaction_rows`). The densest thread precipitates and IS
        the note's theme. `stance` is the era's posture toward the outside
        world when the schedule has one — it colours what the Muse says, and
        it instructs nobody. Nothing returned here is handed to an artist.
        """
        today = self.clock()
        names = dict(artist_names or {})

        # (a) the discourse. External failure NEVER stops anything: a dead
        # network, a refused search, a garbled reply — the scan is simply
        # empty and the note is written from what this world already made.
        discourse: list[Fragment] = []
        if self.perceiver is not None:
            try:
                evidence = self.perceiver.broad_scan(BROAD_QUERIES, cycle_id="muse")
                discourse = [evidence_to_fragment(e) for e in evidence]
            except Exception:  # noqa: BLE001 — a thin note, never a dead stage
                discourse = []
        if self.field_audio is not None:  # the documented v1 seam
            try:
                discourse.extend(self.field_audio.cluster(now=today))
            except Exception:  # noqa: BLE001
                pass

        own: list[Fragment] = []
        for album in albums:
            own.extend(
                album_fragments(
                    album, today=today, artist_name=names.get(album.artist_id, "")
                )
            )
        reception = reaction_fragments(reaction_rows, today=today)

        fragments = [*discourse, *own, *reception]
        # The record's own names never become the theme: the reader knows who
        # made it, and "what the scene is doing" has to say something else.
        own_names = {album.artist_id for album in albums} | {
            token for name in names.values() for token in name.split()
        }
        cluster = precipitate_theme(fragments, clusterer=FieldClusterer(own_names))
        theme = cluster.label if cluster else "silence"
        sources = tuple(
            dict.fromkeys(
                str(f.metadata["url"])
                for f in (cluster.fragments if cluster else [])
                if "url" in f.metadata
            )
        )
        by_beat: dict[str, list[str]] = {}
        for fragment in fragments:
            by_beat.setdefault(fragment.beat, []).append(fragment.content)
        thin = not discourse

        prompt = (
            "Write the note: what the scene is doing right now, and where the "
            "record that just came out sits next to it.\n"
            + (f"THE ERA'S STANCE: {STANCES.get(stance, stance)}\n" if stance else "")
            + "\nTHE FIELD (what the scan heard moving outside"
            + (
                " — NOTHING; the scan came back empty. Say so plainly and work "
                "from our own record"
                if thin
                else ""
            )
            + "):\n"
            + json.dumps(by_beat.get(BEAT_FIELD, []), indent=1, ensure_ascii=False)
            + "\n\nWHAT THIS WORLD JUST PUT OUT (the record, in the artist's own words):\n"
            + json.dumps(by_beat.get(BEAT_OWN, []), indent=1, ensure_ascii=False)
            + "\n\nTHE LISTENER'S WORD (the fan, on earlier records):\n"
            + json.dumps(by_beat.get(BEAT_RECEPTION, []), indent=1, ensure_ascii=False)
            + f"\n\nWHAT PRECIPITATED (the densest thread across all of it): {theme}\n"
            "\nThis note is published beside a record that is already out. It is "
            "not a brief: do not say what anyone should reach for next, do not "
            "address an artist, do not hand anyone an instruction.\n"
            'Reply with ONE JSON object, nothing else: {"note": "<2-4 sentences '
            'of public prose: what the scene is doing, and this record in it>"}'
        )

        def parse(raw: str) -> str:
            data = _loads_lenient(raw)
            if not isinstance(data, Mapping) or "note" not in data:
                raise ValueError("muse scene note reply is not the expected JSON object")
            body = str(data["note"]).strip()
            if not body:
                raise ValueError("the muse's note came back empty")
            return body

        body = staff_complete(
            self.model,
            [
                Message(role="system", content=_MUSE_PROMPT),
                Message(role="user", content=prompt),
            ],
            stage="muse/scene-note",
            parse=parse,
        )
        return SceneNote(theme=theme, body=body, sources=sources, thin=thin, stance=stance)

    # === EXPERIMENT-ONLY from here down ======================================
    # The BRIEF — and with it the taboo memory's forbidden moves and the
    # palette notes — belongs to the round-based instrument (afar.staff_rounds,
    # behind AFAR_EXPERIMENT_MODE), where a brief is still handed to the
    # Producer at set start. That handoff is the seam the album spine cuts:
    # nothing below runs on an album, and nothing below is reachable from
    # `afar.staff.run_reactions`. These calls carry their own system prompt
    # (_BRIEF_PROMPT); the live persona above says, correctly, that the Muse
    # briefs no one.

    def compose(
        self,
        *,
        stance: str,
        release_records: Sequence[Mapping[str, Any]],
        reaction_rows: Sequence[Mapping[str, Any]] = (),
        stage_names: Mapping[str, str] | None = None,
        carried_forward: bool = False,
    ) -> Brief:
        perception = self.perceive(
            {
                "stance": stance,
                "release_records": list(release_records),
                "reaction_rows": list(reaction_rows),
                "stage_names": dict(stage_names or {}),
                "carried_forward": carried_forward,
            }
        )
        decision = self.decide(perception)
        artifact = self.execute(decision)
        meta = artifact.metadata
        return Brief(
            stance=str(meta["stance"]),
            theme=str(meta["theme"]),
            body=artifact.body,
            palette_notes=tuple(meta["palette_notes"]),
            forbidden_moves=tuple(meta["forbidden_moves"]),
            sources=tuple(meta["sources"]),
            thin=bool(meta["thin"]),
            carried_forward=bool(meta["carried_forward"]),
        )

    # -- PERCEIVE: the field, the world's own output, the fan's word -----------

    def perceive(self, context: Mapping[str, Any]) -> Perception:
        today = self.clock()
        self.taboo.stance = str(context["stance"])

        # (a) the discourse. External failure NEVER stops anything: a dead
        # network, a refused search, a garbled reply — the scan is simply
        # empty and the brief precipitates from what this world already made.
        discourse: list[Fragment] = []
        scan_failed = False
        if self.perceiver is not None:
            try:
                evidence = self.perceiver.broad_scan(BROAD_QUERIES, cycle_id="muse")
                discourse = [evidence_to_fragment(e) for e in evidence]
            except Exception:
                scan_failed = True
        # (a') the field-audio ear — the v1 seam. Never fatal either.
        if self.field_audio is not None:
            try:
                discourse.extend(self.field_audio.cluster(now=today))
            except Exception:
                pass

        # (b) the world's own recent output.
        own: list[Fragment] = []
        for record in context["release_records"]:
            own.extend(
                own_output_fragments(record, today=today, stage_names=context["stage_names"])
            )

        # (c) the Listener's word, carried forward from previous boundaries.
        reception = reaction_fragments(context["reaction_rows"], today=today)

        return Perception(
            data={
                "stance": context["stance"],
                "discourse": discourse,
                "own": own,
                "reception": reception,
                "scan_failed": scan_failed,
                "carried_forward": context["carried_forward"],
            }
        )

    # -- DECIDE: precipitation, not choice -------------------------------------

    def decide(self, perception: Perception) -> Decision:
        data = perception.data
        discourse: list[Fragment] = data["discourse"]
        fragments: list[Fragment] = [*discourse, *data["own"], *data["reception"]]

        # The field's moves are observed under any stance; hostility forbids them.
        for fragment in discourse:
            subject = str(fragment.metadata.get("subject", "")) or fragment.content[:60]
            self.taboo.observe(field_move(subject))

        cluster = precipitate_theme(fragments, clusterer=FieldClusterer())
        theme = cluster.label if cluster else "silence"
        theme_fragments = cluster.fragments if cluster else []
        sources = tuple(
            dict.fromkeys(  # ordered dedup
                str(f.metadata["url"]) for f in theme_fragments if "url" in f.metadata
            )
        )
        return Decision(
            data={
                "stance": data["stance"],
                "theme": theme,
                "theme_fragments": theme_fragments,
                "fragments": fragments,
                "forbidden_moves": self.taboo.forbidden_now(),
                "sources": sources,
                "thin": not discourse,
                "scan_failed": data["scan_failed"],
                "carried_forward": data["carried_forward"],
            }
        )

    # -- EXECUTE: the public brief (plain-language rule) -----------------------

    def execute(self, decision: Decision) -> Artifact:
        d = decision.data
        stance: str = d["stance"]
        by_beat: dict[str, list[str]] = {}
        for fragment in d["fragments"]:
            by_beat.setdefault(fragment.beat, []).append(fragment.content)
        prompt = (
            f"Write the brief.\n"
            f"THE ERA'S STANCE: {STANCES.get(stance, stance)}\n\n"
            "THE FIELD (what the scan heard moving outside"
            + (" — NOTHING; the scan came back empty, work from our own record"
               if d["thin"] else "")
            + "):\n"
            + json.dumps(by_beat.get(BEAT_FIELD, []), indent=1, ensure_ascii=False)
            + "\n\nWHAT THIS WORLD JUST SHIPPED (our own record):\n"
            + json.dumps(by_beat.get(BEAT_OWN, []), indent=1, ensure_ascii=False)
            + "\n\nTHE LISTENER'S WORD (the fan, from earlier releases):\n"
            + json.dumps(by_beat.get(BEAT_RECEPTION, []), indent=1, ensure_ascii=False)
            + f"\n\nWHAT PRECIPITATED (the densest thread across all of it): {d['theme']}\n"
            + "FORBIDDEN MOVES (off-limits this era; name them in the brief only if it cuts):\n"
            + json.dumps(list(d["forbidden_moves"]), indent=1, ensure_ascii=False)
            + (
                "\n\nTIMING: this brief is written AFTER the release it reads — it is what "
                "you carry FORWARD into the next session. Write it that way: what you "
                "heard, what to reach for next. Do not pretend it opened the session."
                if d["carried_forward"]
                else ""
            )
            + "\n\nReply with ONE JSON object, nothing else: "
            '{"brief": "<2-4 sentences of public prose>", '
            '"palette_notes": ["<2-4 short working notes for the Producer: textures, '
            "tempo feels, moods to reach for — plain words>\"]}"
        )
        def parse(raw: str) -> Mapping[str, Any]:
            data = _loads_lenient(raw)
            if not isinstance(data, Mapping) or "brief" not in data or "palette_notes" not in data:
                raise ValueError("muse brief reply is not the expected JSON object")
            return data

        # The staff retry ladder (afar.agents.robust): empty re-request, then
        # one nudged re-prompt — a whole boundary should not die on one bad turn.
        data = staff_complete(
            self.model,
            [
                Message(role="system", content=_BRIEF_PROMPT),
                Message(role="user", content=prompt),
            ],
            stage="muse/brief",
            parse=parse,
        )
        body = str(data["brief"]).strip()
        return Artifact(
            kind="brief",
            body=body,
            metadata={
                "stance": stance,
                "theme": d["theme"],
                "palette_notes": [str(n).strip() for n in data["palette_notes"]],
                "forbidden_moves": list(d["forbidden_moves"]),
                "sources": list(d["sources"]),
                "thin": d["thin"],
                "carried_forward": d["carried_forward"],
            },
        )
