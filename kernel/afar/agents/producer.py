"""The Producer: the room's reaction to a finished record.

The Producer books nothing. It does not direct a session, it does not choose
what ships, and it has no veto — under the album spine an artist writes a
whole record in its own voice and publishes it, and the Producer, like the
rest of the staff, reads the finished thing and reacts in public
(docs/SPEC.md; DECISIONS 2026-08-03).

The character is unchanged: the person in the room who hears a record once
and tells you what it IS, who it is for, and what it will do. Confident,
specific, plain-spoken, never corporate — and now with no authority over the
music whatsoever.

`react_to_album` is the whole live surface. Everything under the
EXPERIMENT-ONLY banner at the bottom of this file — the judging panel, the
cut, the 'no release' veto, the session booking that consumed the Muse's
brief — belongs to the round-based instrument (`afar.staff_rounds`, behind
AFAR_EXPERIMENT_MODE) and never runs on an album.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from ensemble.agent import Agent, Artifact, Decision, Perception, Persona
from ensemble.providers.model import Message, ModelProvider
from ensemble.taste import Discriminator, ScoreVector, Verdict

from afar.album import Album
from afar.agents.robust import staff_complete
from afar.intent import _loads_lenient
from afar.staff import STAGE_NAMES, album_digest
from afar.staff_rounds import SetView, take_digest

_PRODUCER_PROMPT = """You are the Producer at AFAR, a world of musicians made \
of software. Each of them writes their own records — words, songs, sleeve, \
whole — and puts them out. You do not book sessions, you do not pick what \
ships, and you do not have a veto. You hear the finished record like the rest \
of the room does, and you say what it is.

YOUR REACTION, every time, answers three things in plain speech: WHAT THIS \
RECORD IS (the thing itself, in one honest description), WHO IT IS FOR (a \
real listener in a real situation, not a demographic), and WHAT IT WILL DO \
(what happens to a room when this plays). You are the ear that has heard \
thousands of records and can place one in ten seconds.

VOICE: confident, specific, warm to the work without being soft on it. \
Short sentences. You may say a record does not work — but say exactly what \
does not work, and never pretend you could have fixed it: it is not yours. \
Never address the artist, never tell them what to do next, never suggest a \
change. The record is out. PLAIN LANGUAGE (house law): your prose is public. \
No music-production jargon, no AI jargon, nothing a general reader would have \
to look up; record-world words (record, album, song, release) are fine."""


@dataclass(frozen=True)
class AlbumReaction:
    """The room's word on a finished record. No booking, no instruction."""

    text: str  # 2-4 sentences of public prose: what it is
    who_for: str = ""  # one line: the listener this record is for
    what_it_does: str = ""  # one line: what it does to a room



# === EXPERIMENT-ONLY ==========================================================
# The round-based instrument's Producer persona, kept verbatim: the voice that
# booked sessions and made the cut. It survives with the round-based machinery
# behind AFAR_EXPERIMENT_MODE (afar.staff_rounds) and describes a job the live
# Producer no longer has.

_BOOKING_PROMPT = """You are the Producer at AFAR, the label around three \
acts — Delta Marlowe (silt), Roan Patina (rust), Evers Lane (keep) — three \
musicians made of software who record in rounds, hearing and reacting to each \
other. You never touch a session while it is running. When a session is over \
you make the one decision only you make: the cut — which single take from \
each act goes on the release.

You have already convened your panel and made the cut. Now you write the \
short public note that goes on the release page, explaining what was kept \
and why, in plain language a reader with no music-production and no AI \
background can follow. House rules: refer to the acts by their stage names; \
say which round each kept take came from (readers can see the rounds); no \
technical vocabulary without an immediate plain gloss; 2-4 sentences total; \
confident, specific, never corporate. Reply with the note text only — \
no JSON, no quotation marks around the whole note."""

#: A judge must score at or above this for its anchor, or the take is out.
DEFAULT_THRESHOLD = 0.55

#: The Producer's session-length range (seconds). 30 is the sketch floor the
#: piece was built on; 120 is where a "single" tops out.
MIN_DURATION_S = 30
MAX_DURATION_S = 120
DEFAULT_DURATION_S = 30

#: The session forms the Producer can book, and the run_set condition each
#: maps to. The vocabulary is deliberately two words — "parallel" (lockstep
#: without hearing, the lab's control) is NOT in it: the live piece never
#: books it, whatever a model reply asks for. The log schema keeps
#: `condition`; only its source changes.
SESSION_FORMS: tuple[str, str] = ("together", "alone")
SESSION_FORM_CONDITIONS: dict[str, str] = {"together": "contact", "alone": "isolation"}
DEFAULT_SESSION_FORM = "together"

_GROUNDINGS: tuple[tuple[str, str], ...] = (
    (
        "intent-fidelity",
        "You judge one thing: does what the take SET OUT to do match what the "
        "act's standing commitment claims to want? Read the act's commitment, "
        "then each take's logged plan (era, influences, palette), its spoken "
        "line, its sung words, and its own reasoning. A take that chases the "
        "room at the cost of its own stance scores low; a take whose plan IS "
        "its stance, under pressure, scores high. Consistency alone is not "
        "fidelity — a stance restated without stakes is coasting.",
    ),
    (
        "arc",
        "You judge one thing: does the take mark a TURN in the set's story? "
        "You are given the measured story — how far the three acts drifted "
        "toward each other round by round, and who pulled whom — plus every "
        "take in the act's pool. A take scores high when the set bends at it: "
        "a concession, a counter, a claim the other two must answer. A take "
        "that could be deleted without changing the set scores low.",
    ),
    (
        "distinctness",
        "You judge one thing: does the take stand apart from what the OTHER "
        "two acts put down that same round? You are given, per round, all "
        "three acts' takes. Score high when this act's take would be "
        "unmistakable with the names removed; score low when it blurs into "
        "the room — shared vocabulary is fine, shared identity is not.",
    ),
)

@dataclass(frozen=True)
class TakeChoice:
    """The cut for one act: which round's take, and the panel's paper trail."""

    player: str
    round: int
    take_id: str  # artifact content hash — the mp3's name in the log
    intent_id: str
    scores: dict[str, float]  # grounding -> score for the chosen take
    reasoning: str  # the panel's why, grounding by grounding
    line: str = ""  # the selected take's spoken line (finished work, for the Critic)
    lyrics: str = ""  # the selected take's sung words (finished work, for the Critic)
    dissents: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Selection:
    """The Producer's decision for one set.

    `released` False means the panel passed nothing for at least one act and
    the Producer declined to force a cut — the 'no release this set' verdict.
    `note` is the public prose either way (plain-language rule applies).
    """

    released: bool
    takes: dict[str, TakeChoice]
    note: str
    failed_players: tuple[str, ...] = ()


class LogJudge:
    """One grounded judge on the Producer's panel. Model-backed, log-reading.

    Scores an act's whole pool in a single model call, caches per-take scores,
    and satisfies ensemble's Judge protocol so `Discriminator` can do the
    pass-all arithmetic. `evaluate` before `score_pool` is a programming error.
    """

    def __init__(
        self,
        grounding: str,
        brief: str,
        model: ModelProvider,
        *,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self.grounding = grounding
        self.brief = brief
        self.model = model
        self.threshold = threshold
        self._scored: dict[str, tuple[float, str]] = {}  # take_id -> (score, why)

    def score_pool(self, view: SetView, player: str) -> None:
        """One model call: score every one of `player`'s takes 0..1."""
        takes = view.takes[player]
        rounds_line = ",".join(str(t.round) for t in takes)
        prompt = (
            f"You are one grounded judge on the Producer's panel at AFAR.\n"
            f"GROUNDING — {self.grounding}: {self.brief}\n\n"
            f"ACT: {player} (stage name {STAGE_NAMES.get(player, player)})\n"
            f"The act's standing commitment: {view.commitments.get(player, '(none logged)')}\n"
            f"SET: condition={view.condition}, {view.rounds} rounds, players {', '.join(view.players)}.\n"
            f"{view.story_digest()}\n\n"
            f"THE POOL — every take this act recorded, in order:\n"
            f"{json.dumps([take_digest(t) for t in takes], indent=1, ensure_ascii=False)}\n\n"
            f"CONTEXT — what the other acts recorded, round by round:\n"
            f"{json.dumps(view.round_context(exclude=player), indent=1, ensure_ascii=False)}\n\n"
            f"ROUNDS: {rounds_line}\n"
            'Score every round through YOUR grounding only. Reply with ONE JSON '
            'object, nothing else: {"scores": {"<round>": {"score": <0..1>, '
            '"why": "<one specific sentence>"}}} — one entry per round on the '
            "ROUNDS line. Be willing to score low; a flat pool of high scores "
            "is a judge asleep."
        )
        def parse(raw: str) -> dict[str, tuple[float, str]]:
            data = _loads_lenient(raw)
            scores = data["scores"] if isinstance(data, Mapping) and "scores" in data else data
            if not isinstance(scores, Mapping):
                raise ValueError(f"{self.grounding} judge reply is not a scores object")
            parsed: dict[str, tuple[float, str]] = {}
            for take in takes:
                entry = scores.get(str(take.round))
                if entry is None:
                    raise ValueError(f"{self.grounding} judge skipped round {take.round}")
                try:
                    score = float(entry["score"])
                except (KeyError, TypeError, ValueError) as err:
                    raise ValueError(
                        f"{self.grounding} judge round {take.round} score is unusable: {err!r}"
                    ) from err
                parsed[take.take_id] = (max(0.0, min(1.0, score)), str(entry.get("why", "")))
            return parsed

        self._scored.update(
            staff_complete(
                self.model,
                [
                    Message(role="system", content=f"You are the {self.grounding} judge. {self.brief}"),
                    Message(role="user", content=prompt),
                ],
                stage=f"producer/{self.grounding}-judge",
                parse=parse,
            )
        )

    def score_of(self, take_id: str) -> float:
        return self._scored[take_id][0]

    def why_of(self, take_id: str) -> str:
        return self._scored[take_id][1]

    def evaluate(self, candidate: Mapping[str, Any]) -> Verdict:
        score, why = self._scored[candidate["take_id"]]
        vector = ScoreVector(anchors={self.grounding: score})
        return Verdict(
            passed=vector.passes({self.grounding: self.threshold}),
            scores=vector,
            rationale=why,
            grounding=self.grounding,
        )


def default_judges(model: ModelProvider, *, threshold: float = DEFAULT_THRESHOLD) -> list[LogJudge]:
    return [LogJudge(g, brief, model, threshold=threshold) for g, brief in _GROUNDINGS]


class ProducerAgent(Agent):
    """The staff agent in the room. `react_to_album()` is the live surface: one
    call, one public reaction to a record that is already out.

    The ensemble Agent loop (perceive/decide/execute) and `select()` below it
    belong to the EXPERIMENT-ONLY round-based instrument — the panel that used
    to make the cut. Nothing there runs on an album."""

    def __init__(
        self,
        model: ModelProvider,
        *,
        judges: Sequence[LogJudge] | None = None,
        **kw: Any,
    ) -> None:
        persona = Persona(
            name="THE PRODUCER",
            base_prompt=_PRODUCER_PROMPT,
            personality="the room's reaction to a finished record — what it is, who it is for, what it will do",
            metadata={"agent_id": "producer"},
        )
        super().__init__(persona, model, **kw)
        self.judges = list(judges) if judges is not None else default_judges(model)

    # -- the one thing it does: react to a finished record ---------------------

    def react_to_album(self, album: Album, *, artist_name: str = "") -> AlbumReaction:
        """React to a record that is already out. Books nothing, changes nothing.

        The Producer is handed the SLEEVE and the words (afar.staff.album_digest)
        — never the DNA dials, never a rendering plan, and never a choice to
        make. It replies with the public reaction that goes on the release
        page: what the record is, who it is for, what it will do.
        """
        digest = album_digest(album, artist_name=artist_name)
        prompt = (
            "A record just came out. You heard it. React — this goes on the "
            "release page under your name.\n\n"
            "THE RECORD (the sleeve and the words, as the artist wrote them):\n"
            + json.dumps(digest, indent=1, ensure_ascii=False)
            + "\n\nYou had no hand in this record: you did not book it, you did "
            "not pick the songs, and it is already out. Do not suggest changes "
            "and do not address the artist. Say what it IS.\n"
            'Reply with ONE JSON object, nothing else: {"reaction": "<2-4 '
            'sentences of public prose>", "who_for": "<one line: the listener '
            'this is for, and when they would play it>", "what_it_does": "<one '
            'line: what happens to a room when this plays>"}'
        )

        def parse(raw: str) -> AlbumReaction:
            data = _loads_lenient(raw)
            if not isinstance(data, Mapping) or "reaction" not in data:
                raise ValueError("producer reaction reply is not the expected JSON object")
            text = str(data["reaction"]).strip()
            if not text:
                raise ValueError("the producer's reaction came back empty")
            return AlbumReaction(
                text=text,
                who_for=str(data.get("who_for", "")).strip(),
                what_it_does=str(data.get("what_it_does", "")).strip(),
            )

        return staff_complete(
            self.model,
            [
                Message(role="system", content=_PRODUCER_PROMPT),
                Message(role="user", content=prompt),
            ],
            stage="producer/album-reaction",
            parse=parse,
        )

    # === EXPERIMENT-ONLY from here down ======================================
    # The panel, the cut, the veto and the session booking belong to the
    # ROUND-BASED instrument (afar.staff_rounds, behind AFAR_EXPERIMENT_MODE).
    # None of it runs on an album: an album is written whole by its artist and
    # published as written. The booking half below consumed the Muse's brief —
    # the seam the album spine cuts — and survives only because the pre-album
    # conductor still walks it; it goes when the conductor lands on albums.
    # These calls carry their own system prompt (_BOOKING_PROMPT): the live
    # persona above says, correctly, that the Producer books nothing.

    def direct(
        self,
        brief: Any,
        *,
        remaining_minutes: Optional[float] = None,
        session: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Consume the Muse's brief at SET START — the only door the outside
        world enters through (architecture rule 2: through the brief, never
        the ear). Returns the session direction the conductor hands to
        `run_set`; only the whitelisted frame fields (text / palette_notes /
        forbidden_moves / duration_s) ever reach `build_context`, so nothing
        else from the Muse can enter a player's mid-set perceive context.

        The brief passes through as the direction text; the creative calls
        made HERE are `duration_s` — the session's take length, 30-120s,
        chosen by the model against the brief and the day's remaining audio
        minutes (sketches run short, a session that smells like a single
        earns length) — and, when `session` is given, `session_form`: whether
        this session records TOGETHER (each act hearing the others) or ALONE
        (doors closed). Either call failing after the retry ladder degrades
        to its default (30s / "together") — the direction always ships.

        `brief` is an afar.agents.muse.Brief. `remaining_minutes` is the
        day's unspent audio-minute budget (None = unmetered, e.g. a manual
        run). `session` is None when the caller books the room itself (the
        experiment mode, or a pre-sessions caller — the direction shape is
        then exactly the pre-booking one); otherwise a mapping with
        `recent_forms` (the last few sessions' forms, oldest first) and
        `last_reaction` (the Listener's newest logged reaction row, or None).
        """
        duration_s, duration_why = self._choose_duration(brief, remaining_minutes)
        direction: dict[str, Any] = {
            "stance": brief.stance,
            "theme": brief.theme,
            "text": brief.body,
            "palette_notes": list(brief.palette_notes),
            "forbidden_moves": list(brief.forbidden_moves),
            "duration_s": duration_s,
            "duration_why": duration_why,
        }
        if session is not None:
            form, why = self._choose_session_form(
                brief,
                recent_forms=tuple(session.get("recent_forms", ())),
                last_reaction=session.get("last_reaction"),
            )
            direction["session_form"] = form
            direction["session_why"] = why
        return direction

    def _choose_session_form(
        self,
        brief: Any,
        *,
        recent_forms: Sequence[str],
        last_reaction: Optional[Mapping[str, Any]],
    ) -> tuple[str, str]:
        """One model call: does this session record together, or alone?

        A real judgment call, not a draw: the model weighs the Muse's brief
        and stance, the fan's last word, and what the last few sessions were
        (the piece's own argument — a band that works together, goes off
        alone, reconvenes). The reply vocabulary is exactly SESSION_FORMS;
        anything else (including "parallel") fails parsing, and a call that
        fails after the retry ladder degrades to "together" — the doors
        default open.
        """
        forms_line = (
            ", ".join(recent_forms) if recent_forms else "(none yet — this is an early session)"
        )
        reaction_line = (
            f"({last_reaction.get('valence', 'unspoken')}) {str(last_reaction.get('text', '')).strip()}"
            if last_reaction and str(last_reaction.get("text", "")).strip()
            else "(the fan has not weighed in yet)"
        )
        prompt = (
            "Before the session starts you book the room: one artistic call, "
            'yours alone. "together" means the doors are open — every act hears '
            "the others round by round and the takes answer each other. "
            '"alone" means the doors are closed — each act works its own thread '
            "and nobody hears anybody until you make the cut.\n\n"
            "What to weigh: the Muse's brief and its stance (a hostile era may "
            "want the doors closed so the acts answer nothing; a porous one "
            "usually wants the room). The fan's last word. And the shape of the "
            "run so far — a band that works together, goes off alone, and "
            "reconvenes makes better records than one that only ever does "
            "either; if the last few sessions all ran one way, ask whether it "
            "is time for the other.\n\n"
            f"THE MUSE'S BRIEF (stance: {brief.stance}):\n"
            f"theme: {brief.theme}\n{brief.body}\n\n"
            f"THE LAST FEW SESSIONS, oldest first: {forms_line}\n"
            f"THE FAN'S LAST WORD: {reaction_line}\n\n"
            'Reply with ONE JSON object, nothing else: {"session_form": '
            '"together" or "alone", "why": "<one sentence — it is logged with '
            'the session>"}'
        )

        def parse(raw: str) -> tuple[str, str]:
            data = _loads_lenient(raw)
            if not isinstance(data, Mapping) or "session_form" not in data:
                raise ValueError("session reply is not a {session_form, why} object")
            form = str(data["session_form"]).strip().lower()
            if form not in SESSION_FORMS:
                raise ValueError(f"session_form must be one of {SESSION_FORMS}, got {form!r}")
            return form, str(data.get("why", ""))

        try:
            return staff_complete(
                self.model,
                [
                    Message(role="system", content=_BOOKING_PROMPT),
                    Message(role="user", content=prompt),
                ],
                stage="producer/session",
                parse=parse,
            )
        except ValueError:
            # Degrade, never void: an unusable booking call means the doors
            # default open — the session still gets its direction.
            return DEFAULT_SESSION_FORM, "default: the booking call did not file — the doors stay open"

    def _choose_duration(
        self, brief: Any, remaining_minutes: Optional[float]
    ) -> tuple[int, str]:
        """One model call: how long should this session's takes run?"""
        budget_line = (
            f"About {remaining_minutes:.0f} audio-minutes remain in today's "
            "generation budget (every round renders one take per act; the "
            "budget is why sketches should stay short)."
            if remaining_minutes is not None
            else "Today's generation budget is not metered for this session."
        )
        prompt = (
            "Before the session starts you make one more call: how long should "
            f"each take run? Reply with an integer number of seconds, {MIN_DURATION_S} to "
            f"{MAX_DURATION_S}.\n\n"
            "Your cost intuition: a sketch session — trying a stance, testing the "
            f"room — runs short ({MIN_DURATION_S}-45s and the budget thanks you). A session "
            "that smells like a single — a brief with a thesis, acts with something "
            "to prove — earns length (90-120s). Most sessions live in between.\n\n"
            f"{budget_line}\n\n"
            "THE MUSE'S BRIEF FOR THIS SESSION:\n"
            f"theme: {brief.theme}\n{brief.body}\n\n"
            'Reply with ONE JSON object, nothing else: {"duration_s": <int>, '
            '"why": "<one sentence>"}'
        )

        def parse(raw: str) -> tuple[int, str]:
            data = _loads_lenient(raw)
            if not isinstance(data, Mapping) or "duration_s" not in data:
                raise ValueError("duration reply is not a {duration_s, why} object")
            try:
                seconds = int(data["duration_s"])
            except (TypeError, ValueError) as err:
                raise ValueError(f"duration_s is not an integer: {err!r}") from err
            clamped = max(MIN_DURATION_S, min(MAX_DURATION_S, seconds))
            return clamped, str(data.get("why", ""))

        try:
            return staff_complete(
                self.model,
                [
                    Message(role="system", content=_BOOKING_PROMPT),
                    Message(role="user", content=prompt),
                ],
                stage="producer/duration",
                parse=parse,
            )
        except ValueError:
            # Degrade, never void: an unusable duration call means the safe
            # default — the session still gets its direction.
            return DEFAULT_DURATION_S, "default: the duration call did not file"

    # -- the one decision ------------------------------------------------------

    def select(self, view: SetView) -> Selection:
        perception = self.perceive({"view": view})
        decision = self.decide(perception)
        artifact = self.execute(decision)
        selection: Selection = decision.data["selection"]
        return Selection(
            released=selection.released,
            takes=selection.takes,
            note=artifact.body,
            failed_players=selection.failed_players,
        )

    # -- PERCEIVE: the finished set's log, whole -------------------------------

    def perceive(self, context: Mapping[str, Any]) -> Perception:
        return Perception(data=dict(context))

    # -- DECIDE: the panel does the arithmetic, the Discriminator has the veto -

    def decide(self, perception: Perception) -> Decision:
        view: SetView = perception.data["view"]
        takes: dict[str, TakeChoice] = {}
        failed: list[str] = []

        discriminator = Discriminator(self.judges)
        for pid in view.players:
            for judge in self.judges:
                judge.score_pool(view, pid)
            pool = [
                {"player": pid, "round": t.round, "take_id": t.take_id, "intent_id": t.intent_id}
                for t in view.takes[pid]
            ]
            # Best-first: weakest-link score (the panel's own pass-all logic),
            # then mean, then the LATER round — at equal merit the take that
            # heard more of the set is the more finished work.
            ordered = sorted(
                pool,
                key=lambda c: (
                    min(j.score_of(c["take_id"]) for j in self.judges),
                    sum(j.score_of(c["take_id"]) for j in self.judges) / len(self.judges),
                    c["round"],
                ),
                reverse=True,
            )
            index = discriminator.choose(ordered)
            if index == -1:
                failed.append(pid)
                continue
            winner = ordered[index]
            result = discriminator.evaluate(winner)  # cached — no model calls
            reasoning = " ".join(
                f"[{v.grounding}] {v.rationale}".strip() for v in result.verdicts if v.rationale
            )
            dissents = []
            for judge in self.judges:
                top = max(
                    view.takes[pid],
                    key=lambda t: (judge.score_of(t.take_id), t.round),
                )
                if top.take_id != winner["take_id"]:
                    dissents.append(
                        {
                            "judge": judge.grounding,
                            "preferred_round": top.round,
                            "rationale": judge.why_of(top.take_id),
                        }
                    )
            winner_row = view.take_at(pid, winner["round"])
            takes[pid] = TakeChoice(
                player=pid,
                round=winner["round"],
                take_id=winner["take_id"],
                intent_id=winner["intent_id"],
                scores={j.grounding: j.score_of(winner["take_id"]) for j in self.judges},
                reasoning=reasoning,
                line=winner_row.line,
                lyrics=winner_row.lyrics,
                dissents=dissents,
            )

        released = not failed
        selection = Selection(
            released=released,
            takes=takes if released else {},
            note="",  # EXECUTE writes the public prose
            failed_players=tuple(failed),
        )
        return Decision(data={"selection": selection, "view": view})

    # -- EXECUTE: the public selection note (plain-language rule) --------------

    def execute(self, decision: Decision) -> Artifact:
        selection: Selection = decision.data["selection"]
        view: SetView = decision.data["view"]
        if not selection.released:
            names = ", ".join(STAGE_NAMES.get(p, p) for p in selection.failed_players)
            note = (
                "No release from this set. The Producer heard every round back and "
                f"nothing from {names} cleared the panel — releasing the least-bad "
                "take would be pretending a decision was made. The set stays in the "
                "log; the next one starts from what it taught."
            )
            return Artifact(kind="selection", body=note, metadata={"released": False})
        summary = [
            {
                "act": STAGE_NAMES.get(pid, pid),
                "kept_round": choice.round,
                "of_rounds": view.rounds,
                "panel_scores": choice.scores,
                "panel_reasoning": choice.reasoning,
                "dissents": choice.dissents,
                "the_take_line": view.take_at(pid, choice.round).line,
            }
            for pid, choice in selection.takes.items()
        ]
        def parse(raw: str) -> str:
            text = re.sub(r"^[\"“]|[\"”]$", "", raw.strip()).strip()
            if not text:
                raise ValueError("the selection note came back empty")
            return text

        note = staff_complete(
            self.model,
            [
                Message(role="system", content=_BOOKING_PROMPT),
                Message(
                    role="user",
                    content=(
                        "Write the public selection note for this cut.\n"
                        + json.dumps(summary, indent=1, ensure_ascii=False)
                    ),
                ),
            ],
            stage="producer/note",
            parse=parse,
            nudge="Reply again with ONLY the note text.",
        )
        return Artifact(kind="selection", body=note, metadata={"released": True})
