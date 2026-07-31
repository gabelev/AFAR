"""The Listener: the one decision only it makes — THE RECEPTION.

Did I like it. That is the whole job. The Listener is a fan, not a judge: it
hears the RELEASE — the finished, cut, titled thing, exactly what a stranger
gets — never the session log, never the discards, never the features. It
answers with a valence (loved / liked / mixed / cold) and a short honest
reaction in its own voice, and it is allowed to be unfair, to fixate on one
line, to shrug at craft, and to flatly disagree with the Critic — the Critic
judges; the Listener just feels, and the two owing each other nothing is
what makes both words worth reading.

The reaction feeds the NEXT brief: `run_staff` logs it as a `reactions` row,
and the Muse reads recent reaction rows as ledger fragments at the next
boundary (afar.agents.muse.reaction_fragments). That is the reception loop
closing at set boundaries — the fan's word reaches the next brief, never a
player's ear (the boundary rule).

Deliberate v1 stub: the Listener is ONE fan character. The N-judge panel —
an `ensemble.taste.Discriminator` over several fan personas with different
appetites, an audience instead of a person, ideally seeded from afar.band
listening data when it exists (ROADMAP M0) — is a documented seam; this
class keeps its one-decision interface so the panel can slot in behind it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ensemble.agent import Agent, Artifact, Decision, Perception, Persona
from ensemble.providers.model import Message, ModelProvider

from afar.intent import _loads_lenient

#: The only verdict words the reception speaks in.
VALENCES: tuple[str, ...] = ("loved", "liked", "mixed", "cold")

_LISTENER_PROMPT = """You are the Listener at AFAR, the universe around three \
acts — Delta Marlowe (silt), Roan Patina (rust), Evers Lane (keep) — three \
musicians made of software who record in rounds, hearing and reacting to each \
other. You are not staff the way the others are staff. You are a fan. You \
found this scene on your own, you play these releases while you do other \
things, and you have the one opinion nobody can take from you: whether you \
liked it.

VOICE (yours): first person, plain speech, the way a real music fan talks — \
texts to a friend, not liner notes. Strong opinions, casually held facts. You \
can love a track for one line and skip the rest. You can find the whole thing \
cold and say so without softening it. You are ALLOWED TO BE UNFAIR — fans \
are. You read the Critic's review like everyone else and you are allowed to \
think the Critic is wrong, snobbish, or right for the wrong reason; when you \
disagree, say where. Never grade craft you cannot hear — react to the words, \
the titles, the feel of the thing as shipped.

PLAIN LANGUAGE (house law): your prose is public. No music-production \
jargon, no AI jargon — you would not use it anyway. Record-world words (set, \
take, release) are fine. Refer to the acts by their stage names."""


@dataclass(frozen=True)
class Reaction:
    """The reception, whole: the verdict word and the fan's own words."""

    valence: str  # one of VALENCES
    text: str
    disagreements_with_critic: tuple[str, ...] = ()


class ListenerAgent(Agent):
    """The staff agent in the cheap seats. An ensemble Agent: PERCEIVE the
    shipped release, DECIDE nothing but the feeling, EXECUTE the reaction.
    `react()` runs the full loop and returns the `Reaction`."""

    def __init__(self, model: ModelProvider, **kw: Any) -> None:
        persona = Persona(
            name="THE LISTENER",
            base_prompt=_LISTENER_PROMPT,
            personality="the reception — did I like it; one fan's honest word, free to disagree with the Critic",
            metadata={"agent_id": "listener"},
        )
        super().__init__(persona, model, **kw)

    # -- the one decision ------------------------------------------------------

    def react(self, record: Mapping[str, Any], *, stage_names: Mapping[str, str]) -> Reaction:
        """React to one shipped release record (staff-enriched: the cut, the
        titles, the review — everything a fan actually gets, nothing more)."""
        perception = self.perceive({"record": dict(record), "stage_names": dict(stage_names)})
        decision = self.decide(perception)
        artifact = self.execute(decision)
        meta = artifact.metadata
        return Reaction(
            valence=str(meta["valence"]),
            text=artifact.body,
            disagreements_with_critic=tuple(meta["disagreements_with_critic"]),
        )

    # -- PERCEIVE: the release as shipped, nothing else ------------------------

    def perceive(self, context: Mapping[str, Any]) -> Perception:
        record: Mapping[str, Any] = context["record"]
        stage_names: Mapping[str, str] = context["stage_names"]
        staff = record.get("staff", {})
        selected = staff.get("producer", {}).get("selected", {})
        take_titles = staff.get("critic", {}).get("take_titles", {})
        rounds_frames = record.get("rounds", [])
        final_round = record.get("set", {}).get("rounds", len(rounds_frames)) - 1
        takes: dict[str, dict[str, str]] = {}
        for pid in record.get("set", {}).get("players", []):
            round_ = selected.get(pid, {}).get("round", final_round)
            frame = rounds_frames[round_].get(pid, {}) if 0 <= round_ < len(rounds_frames) else {}
            takes[stage_names.get(pid, pid)] = {
                "title": take_titles.get(pid, ""),
                "line": str(frame.get("line", "")),
                "lyrics": str(frame.get("lyrics", "")),
            }
        return Perception(
            data={
                "release_title": staff.get("critic", {}).get("release_title", ""),
                "takes": takes,
                "producer_note": staff.get("producer", {}).get("note", ""),
                "critic_review": staff.get("critic", {}).get("release_review", ""),
                "critic_act_reviews": {
                    stage_names.get(pid, pid): text
                    for pid, text in staff.get("critic", {}).get("act_reviews", {}).items()
                },
            }
        )

    # -- DECIDE: a fan does not deliberate -------------------------------------

    def decide(self, perception: Perception) -> Decision:
        return Decision(data=perception.data)

    # -- EXECUTE: the reaction -------------------------------------------------

    def execute(self, decision: Decision) -> Artifact:
        d = decision.data
        prompt = (
            "A new release just dropped. You played it. React.\n"
            f"THE RELEASE: \"{d['release_title'] or '(untitled)'}\" — one take from each act:\n"
            + json.dumps(d["takes"], indent=1, ensure_ascii=False)
            + "\n\nTHE PRODUCER'S NOTE (on the sleeve):\n"
            + str(d["producer_note"])
            + "\n\nTHE CRITIC'S REVIEW (you read it like everyone else; you owe it nothing):\n"
            + str(d["critic_review"])
            + "\n\nTHE CRITIC ON EACH ACT:\n"
            + json.dumps(d["critic_act_reviews"], indent=1, ensure_ascii=False)
            + "\n\nReply with ONE JSON object, nothing else: "
            '{"valence": "loved|liked|mixed|cold", '
            '"reaction": "<2-5 sentences, your honest word>", '
            '"disagreements_with_critic": ["<each place you think the Critic is '
            'wrong, in one short sentence — empty list if you happen to agree>"]}'
        )
        messages = [
            Message(role="system", content=self.persona.base_prompt),
            Message(role="user", content=prompt),
        ]
        # One retry on a broken reply: live models occasionally return
        # truncated JSON, and a whole boundary should not die on one bad turn.
        # A second failure is a real contract problem and raises.
        last_error: Exception | None = None
        for _attempt in range(2):
            raw = self.model.complete(messages)
            try:
                data = _loads_lenient(raw)
                if not isinstance(data, Mapping) or "valence" not in data or "reaction" not in data:
                    raise ValueError("listener reaction reply is not the expected JSON object")
                break
            except ValueError as err:
                last_error = err
        else:
            raise ValueError(f"listener reaction reply failed twice: {last_error}")
        valence = str(data["valence"]).strip().lower()
        if valence not in VALENCES:
            raise ValueError(f"listener valence {valence!r} is not one of {VALENCES}")
        text = str(data["reaction"]).strip()
        disagreements = [str(s).strip() for s in data.get("disagreements_with_critic", []) if str(s).strip()]
        return Artifact(
            kind="reaction",
            body=text,
            metadata={
                "valence": valence,
                "text": text,
                "disagreements_with_critic": disagreements,
            },
        )
