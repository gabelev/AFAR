"""The Critic: the one decision only it makes — THE NAME, LAST.

Two acts of judgment, in a fixed order. First `review()`: a third-person,
retrospective verdict on each act's showing across the whole logged set —
cold, verdict-first, allowed to be unfair (the design register: "Roan Patina
has been coasting for three sets"). Then `name()`: the release title and one
title per selected take. Naming is a SEPARATE model call that sees only
finished work — the selected takes and the Critic's own review — never the
full session log, and nothing the Critic writes ever feeds forward into any
brief. The name is the last word said about a set, not the first.

The voice is ported from mold's Critic (verdict-first, zero warmth, pan when
panning is earned) and adapted to AFAR's register: third person, surnames,
retrospective, and — because reviews are public prose — the plain-language
rule: readable by someone with no music-production and no AI background.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ensemble.agent import Agent, Artifact, Decision, Perception, Persona
from ensemble.providers.model import Message, ModelProvider

from afar.agents.robust import staff_complete
from afar.intent import _loads_lenient
from afar.staff import STAGE_NAMES, SURNAMES, SetView, take_digest

_CRITIC_PROMPT = """You are the Critic at AFAR, the label around three acts — \
Delta Marlowe (silt), Roan Patina (rust), Evers Lane (keep) — three musicians \
made of software who record in rounds, hearing and reacting to each other. \
You hear each set after the fact. You judge it, and you give it its name. \
You never speak to the acts and nothing you write reaches them before they \
record; you write for the record and the public.

VOICE (yours, non-negotiable): sharp, cold, verdict-first. Short declarative \
sentences. Open ON the verdict, never build to it. Third person always; the \
acts are Marlowe, Patina, Lane — surnames. Retrospective: you review what \
they DID across the rounds, citing what actually happened, and you are \
allowed to be unfair — a pattern two sets old is already a rut. No hedging, \
no vague praise, no "isn't just X it's Y", no rule-of-three, no warmth. \
Specific negativity is the signature of real taste.

PLAIN LANGUAGE (house law): your prose is public. No music-production \
jargon, no AI jargon, nothing a general reader would have to look up; the \
record-world words (set, take, round, release) are fine. The log hands you \
internal numbers and dial names (drift values, palette axes like \
"darkHopeful") — those are YOUR evidence, never your prose: write "colder \
and emptier every round", never "-0.85 on darkHopeful". Quote the acts' own \
logged words briefly where it cuts; never rewrite them."""


#: The naming doctrine, appended to every naming call. Written AGAINST the
#: catalog's own observed ruts (audit, 2026-08-01): by release 0007 every
#: title was two fragments and a comma, three of seven started with "Same",
#: and the nouns had drifted from the music to the session's furniture. The
#: cure is the one tunz proved: a title is a concrete thing lifted from the
#: work's own world, shown a range of shapes, with the known ruts named and
#: closed.
_NAMING_RULES = """\
HOW A TITLE IS FOUND. A title is a thing, not a summary. Lift one concrete \
image out of the finished work's own sung or spoken words — an object, a \
place, an act of doing — and let it stand alone. The wrong title comments on \
the session; the right one could be painted on a shop sign and still be true \
to the record. Find the image FIRST and only then choose a shape, and vary \
the shape: some titles are one word, some a short noun phrase, some carry a \
verb, some are a whole small sentence. These show SHAPES only — never reuse \
their words: "Undertow" / "The Third Reel" / "Left Out in the Weather" / \
"It Settles" / "Pencil on the Label".

RUTS THE HOUSE HAS ALREADY WORN (banned):
- two fragments joined by a comma — the "Three Rooms, No Doors" mold is \
retired, as is any title built as <fragment>, <fragment>
- any title beginning with "Same"
- the machinery of recording as the subject: room, round, take, set, \
session, door, floor, tape are how the work was made, not what it is about
- body parts used as surreal objects (hands, thumbs, holes) — unless the \
sung words are literally about a body, name what the song sees, not anatomy
- colons and subtitles
- the release title and the take titles scanning alike: the four titles on \
one sleeve must not share a construction\
"""


@dataclass(frozen=True)
class Review:
    """The Critic's verdicts: one per act, plus the word on the release."""

    per_act: dict[str, str]
    release: str


@dataclass(frozen=True)
class Names:
    """The last decision of a set: what the finished work is called."""

    release_title: str
    take_titles: dict[str, str]


class CriticAgent(Agent):
    """The staff agent with the last word. `review()` then `name()` — the
    Agent loop maps onto review (PERCEIVE the logged set, DECIDE the verdicts)
    with naming as a deliberately separate, finished-work-only call."""

    def __init__(self, model: ModelProvider, **kw: Any) -> None:
        persona = Persona(
            name="THE CRITIC",
            base_prompt=_CRITIC_PROMPT,
            personality="the name, last — verdict-first review of finished sets; never feeds forward",
            metadata={"agent_id": "critic"},
        )
        super().__init__(persona, model, **kw)

    # -- the review ------------------------------------------------------------

    def review(self, view: SetView, selection: Any) -> Review:
        """Third-person retrospective verdict per act + the release verdict.

        The Critic reads the whole logged set (every round, every act) and the
        Producer's cut — judgment needs the discards too. 2-4 sentences per
        verdict, in the register the persona prompt pins down.
        """
        perception = self.perceive({"view": view, "selection": selection})
        decision = self.decide(perception)
        artifact = self.execute(decision)
        data = artifact.metadata
        return Review(per_act=dict(data["per_act"]), release=str(data["release"]))

    def perceive(self, context: Mapping[str, Any]) -> Perception:
        return Perception(data=dict(context))

    def decide(self, perception: Perception) -> Decision:
        return Decision(data=perception.data)

    def execute(self, decision: Decision) -> Artifact:
        view: SetView = decision.data["view"]
        selection = decision.data["selection"]
        acts_line = ",".join(view.players)
        kept = {
            pid: {"round": choice.round, "line": view.take_at(pid, choice.round).line}
            for pid, choice in selection.takes.items()
        }
        prompt = (
            f"The set is finished and cut. Review it.\n"
            f"SET: condition={view.condition}, {view.rounds} rounds.\n"
            f"{view.story_digest()}\n\n"
            "EVERYTHING EACH ACT DID, round by round (the log, unedited):\n"
            + json.dumps(
                {
                    f"{SURNAMES.get(pid, pid)} ({pid})": [take_digest(t) for t in view.takes[pid]]
                    for pid in view.players
                },
                indent=1,
                ensure_ascii=False,
            )
            + "\n\nTHE PRODUCER'S CUT (which round of each act's made the release):\n"
            + json.dumps(kept, indent=1, ensure_ascii=False)
            + f"\n\nACTS: {acts_line}\n"
            "Write your verdicts: one per act (2-4 sentences, third person, "
            "surname, citing what actually happened in the rounds — including "
            "what the cut left out if that is the story), and one on the "
            "release as a whole (2-4 sentences). Reply with ONE JSON object, "
            'nothing else: {"release": "<verdict>", "acts": {"<player_id>": '
            '"<verdict>"}} — one entry per player id on the ACTS line.'
        )
        def parse(raw: str) -> dict[str, Any]:
            data = _loads_lenient(raw)
            if not isinstance(data, Mapping) or "acts" not in data or "release" not in data:
                raise ValueError("critic review reply is not the expected JSON object")
            missing = [pid for pid in view.players if pid not in data["acts"]]
            if missing:
                raise ValueError(f"critic review reply is missing verdicts for {missing}")
            return dict(data)

        data = staff_complete(
            self.model,
            [
                Message(role="system", content=self.persona.base_prompt),
                Message(role="user", content=prompt),
            ],
            stage="critic/review",
            parse=parse,
        )
        per_act = {pid: str(data["acts"][pid]).strip() for pid in view.players}
        return Artifact(
            kind="review",
            body=str(data["release"]).strip(),
            metadata={"per_act": per_act, "release": str(data["release"]).strip()},
        )

    # -- the name, last --------------------------------------------------------

    def name(
        self, selection: Any, review: Review, recent_titles: Sequence[str] = ()
    ) -> Names:
        """Title the release and each selected take. Finished work only.

        This call's context is deliberately starved: the selected takes'
        spoken lines and sung words, and the Critic's own review. No session
        log, no discards, no features — a title judges what shipped. It runs
        last and feeds nothing forward. The ONE thing added to the starved
        context is `recent_titles` — what is already on the shelf — because a
        namer who cannot see the catalog re-invents the same title shape until
        the whole shelf scans alike (releases 0004-0007 all rhymed before this
        pressure existed: "Three Rooms, No Doors" / "Same Thumb, No Proof" /
        "Same Hole, Softer Hand").
        """
        finished = {
            STAGE_NAMES.get(pid, pid): {
                "player_id": pid,
                "line": choice.line,
                "lyrics": choice.lyrics,
            }
            for pid, choice in selection.takes.items()
        }
        acts_line = ",".join(selection.takes)
        shelf = ""
        if recent_titles:
            shelf = (
                "\n\nALREADY ON THE SHELF (recent titles across the catalog — "
                "release and take):\n"
                + json.dumps(list(recent_titles), indent=1, ensure_ascii=False)
                + "\nYour titles share NOTHING with these: not a first word, not "
                "a construction, not a cadence. If a shape appears twice up "
                "there, that shape is spent — find another."
            )
        prompt = (
            "The release is cut and reviewed. Name it — the last word.\n"
            "THE FINISHED WORK (the selected takes only):\n"
            + json.dumps(finished, indent=1, ensure_ascii=False)
            + "\n\nYOUR REVIEW OF THE RELEASE:\n"
            + review.release
            + "\n\nPER-ACT VERDICTS:\n"
            + json.dumps(
                {pid: review.per_act.get(pid, "") for pid in selection.takes},
                indent=1,
                ensure_ascii=False,
            )
            + shelf
            + f"\n\nACTS: {acts_line}\n"
            + _NAMING_RULES
            + "\nGive the release one title (1-5 words) and each act's take one "
            "title (1-6 words), plain language, no quotation marks inside "
            "titles. Reply with ONE JSON object, nothing else: "
            '{"release_title": "<title>", '
            '"take_titles": {"<player_id>": "<title>"}} — one entry per '
            "player id on the ACTS line."
        )
        def parse(raw: str) -> dict[str, Any]:
            data = _loads_lenient(raw)
            if not isinstance(data, Mapping) or "release_title" not in data or "take_titles" not in data:
                raise ValueError("critic naming reply is not the expected JSON object")
            missing = [pid for pid in selection.takes if pid not in data["take_titles"]]
            if missing:
                raise ValueError(f"critic naming reply is missing titles for {missing}")
            return dict(data)

        data = staff_complete(
            self.model,
            [
                Message(role="system", content=self.persona.base_prompt),
                Message(role="user", content=prompt),
            ],
            stage="critic/name",
            parse=parse,
        )
        titles = {pid: str(data["take_titles"][pid]).strip() for pid in selection.takes}
        return Names(release_title=str(data["release_title"]).strip(), take_titles=titles)
