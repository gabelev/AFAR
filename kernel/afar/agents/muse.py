"""The Muse: the one decision only it makes — THE BRIEF.

At an era's cadence the Muse decides how this world faces the outside one
(the stance — porous, hostile, oblivious — authored by the schedule, worn by
the Muse) and what the acts should reach for next (the theme). Both land in
the BRIEF: a short public note plus its working parts (palette notes,
forbidden moves, sources).

PERCEIVE is two ears and a memory:
  (a) the discourse — a broad scan over search adapters (ensemble.perceive),
      dated evidence only, dropped into a stigmergic ledger as fragments;
  (b) the world's own recent output — what AFAR itself just shipped, read
      from the release record, as fragments in the same ledger;
  (c) the Listener's logged reactions — the fan's word on previous releases,
      fed forward as fragments (the loop closing at set boundaries).

DECIDE is precipitation, not choice: `ensemble.ledger.precipitate_theme`
finds the densest cluster across everything the ledger accreted, and that
cluster IS the theme — the Muse names what precipitated, it does not invent.
Under a hostile stance the field's observed moves become forbidden moves
(afar.state.field_taboo).

EXECUTE writes the public brief (plain-language rule: readable with no music
or AI background).

THE BOUNDARY RULE IS LAW: the brief is consumed at SET START by the
Producer's direction half (`ProducerAgent.direct`), and NOTHING from the
Muse ever enters a player's mid-set perceive context — `build_context` is
the chokepoint and it knows nothing of briefs. The world enters through the
brief, never the ear.

External failure NEVER stops anything: a failed scan just means a thinner
brief, precipitated from the world's own output alone (`Brief.thin`).

Deliberate v1 stub: briefs are DISCOURSE-only. The field-audio ear — MERT-
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

from afar.intent import _loads_lenient
from afar.perception.field import (
    BEAT_FIELD,
    BEAT_OWN,
    BEAT_RECEPTION,
    BROAD_QUERIES,
    evidence_to_fragment,
)
from afar.state.field_taboo import FieldTabooMemory, field_move

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
    "music musical song songs track tracks album albums artist artists band "
    "bands release releases record records audio listen listening listeners "
    "january february march april may june july august september october "
    "november december week month year midyear".split()
)


class FieldClusterer(KeywordClusterer):
    """ensemble's keyword clusterer minus AFAR's domain-trivial labels.
    Falls back to the unfiltered ranking when nothing else precipitated."""

    def precipitate(self, fragments):  # type: ignore[override]
        ranked = super().precipitate(fragments)
        informative = [c for c in ranked if c.label not in DOMAIN_STOPWORDS]
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


_MUSE_PROMPT = """You are the Muse at AFAR, the universe around three acts — \
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
    """The staff agent that faces outward. An ensemble Agent: PERCEIVE the
    field + the world's own output, DECIDE by precipitation, EXECUTE the
    public brief. `compose()` runs the full loop and returns the `Brief`."""

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
            personality="the brief — the era's stance toward the outside world, and what to reach for next",
            metadata={"agent_id": "muse"},
        )
        super().__init__(persona, model, **kw)
        self.perceiver = perceiver
        self.taboo = taboo or FieldTabooMemory()
        self.field_audio = field_audio  # v1: always None — the documented seam
        self.clock = clock

    # -- the one decision ------------------------------------------------------

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
        messages = [
            Message(role="system", content=self.persona.base_prompt),
            Message(role="user", content=prompt),
        ]
        # One retry on a broken reply: live models occasionally return
        # truncated JSON, and a whole boundary should not die on one bad turn.
        last_error: Exception | None = None
        for _attempt in range(2):
            raw = self.model.complete(messages)
            try:
                data = _loads_lenient(raw)
                if not isinstance(data, Mapping) or "brief" not in data or "palette_notes" not in data:
                    raise ValueError("muse brief reply is not the expected JSON object")
                break
            except ValueError as err:
                last_error = err
        else:
            raise ValueError(f"muse brief reply failed twice: {last_error}")
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
