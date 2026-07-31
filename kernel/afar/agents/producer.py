"""The Producer: the one decision only it makes — THE CUT.

At a set boundary (never mid-set: the boundary rule), the Producer looks back
over EVERY round's takes and decides, per act, which single take makes the
release. Selection is a creative act, so it is not a max() over a scalar: the
Producer convenes a panel of independently-grounded judges (ensemble's taste
harness) and a take must survive ALL of them to be releasable.

The judges read the LOG, not the audio. What they see is the run's own record
— intents, spoken lines, sung lyrics, rationales, and the set's influence /
convergence features. That is a deliberate v1 stub (see DECISIONS.md): honest
audio-space judging needs an audio-capable judge, and until that exists the
judges say out loud what they are grounded in.

Groundings (one judge each, heterogeneous on purpose — same-lineage agreement
is fake agreement):

- intent-fidelity: does what this take set out to do match what the act's
  standing commitment claims to want?
- arc: does this take mark a turn in the set's influence/convergence story,
  or is it treading water?
- distinctness: does this take stand apart from what the other two acts put
  down the same round?

Cost discipline: each judge scores an act's WHOLE pool in one model call
(3 judges x 3 acts = 9 calls a set), and `Discriminator.evaluate` reads the
cached scores. `Discriminator.choose()` keeps the last word: candidates are
offered best-first, and when it returns -1 the whole pool was too safe —
the honest outcome is "no release this set", logged, never forced.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ensemble.agent import Agent, Artifact, Decision, Perception, Persona
from ensemble.providers.model import Message, ModelProvider
from ensemble.taste import Discriminator, ScoreVector, Verdict

from afar.intent import _loads_lenient
from afar.staff import STAGE_NAMES, SetView, TakeRow, take_digest

#: A judge must score at or above this for its anchor, or the take is out.
DEFAULT_THRESHOLD = 0.55

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

_PRODUCER_PROMPT = """You are the Producer at AFAR, the label around three \
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
        raw = self.model.complete(
            [
                Message(role="system", content=f"You are the {self.grounding} judge. {self.brief}"),
                Message(role="user", content=prompt),
            ]
        )
        data = _loads_lenient(raw)
        scores = data["scores"] if isinstance(data, Mapping) and "scores" in data else data
        if not isinstance(scores, Mapping):
            raise ValueError(f"{self.grounding} judge reply is not a scores object")
        for take in takes:
            entry = scores.get(str(take.round))
            if entry is None:
                raise ValueError(f"{self.grounding} judge skipped round {take.round}")
            self._scored[take.take_id] = (
                max(0.0, min(1.0, float(entry["score"]))),
                str(entry.get("why", "")),
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
    """The staff agent that makes the cut. An ensemble Agent: PERCEIVE the
    finished set's log, DECIDE the cut through the panel, EXECUTE the public
    note. `select()` runs the full loop and returns the `Selection`."""

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
            personality="the cut — which takes make the release; decides at set boundaries only",
            metadata={"agent_id": "producer"},
        )
        super().__init__(persona, model, **kw)
        self.judges = list(judges) if judges is not None else default_judges(model)

    # -- the direction half: where the Muse's brief is consumed ----------------

    def direct(self, brief: Any) -> dict[str, Any]:
        """Consume the Muse's brief at SET START — the only door the outside
        world enters through (architecture rule 2: through the brief, never
        the ear). Returns the session direction the conductor will hand to
        `run_set` when it exists; nothing here reaches `build_context`, so
        nothing from the Muse can enter a player's mid-set perceive context.

        Minimal seam, deliberately: v1 passes the brief through as direction.
        A later Producer may translate it (tempo targets, a dare per act);
        the contract that matters is WHERE this runs — set start, frame side.

        `brief` is an afar.agents.muse.Brief.
        """
        return {
            "stance": brief.stance,
            "theme": brief.theme,
            "text": brief.body,
            "palette_notes": list(brief.palette_notes),
            "forbidden_moves": list(brief.forbidden_moves),
        }

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
        note = self.model.complete(
            [
                Message(role="system", content=self.persona.base_prompt),
                Message(
                    role="user",
                    content=(
                        "Write the public selection note for this cut.\n"
                        + json.dumps(summary, indent=1, ensure_ascii=False)
                    ),
                ),
            ]
        ).strip()
        note = re.sub(r"^[\"“]|[\"”]$", "", note).strip()
        return Artifact(kind="selection", body=note, metadata={"released": True})
