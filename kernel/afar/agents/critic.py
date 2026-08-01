"""The Critic: the one decision only it makes — THE NAME, LAST.

Two acts of judgment, in a fixed order. First `review()`: a third-person,
retrospective verdict on each act's showing across the whole logged set —
cold, verdict-first, allowed to be unfair (the design register: "Roan Patina
has been coasting for three sets"). Then `name()`: ONE structured call that
titles the release, describes it as a body of work, and titles each selected
take — together, so the sleeve coheres. The naming process is ported from
tunz (`tunz/lib/generation/profile.ts`), whose titles stayed good for three
process reasons this call mirrors: nothing is named in isolation (one bundle
call, all sleeve text in the same breath); every title arrives WITH its
justification (the release gets a 1-2 sentence body-of-work description, each
take title a one-line why); and instead of ban lists, one traceability law —
every artifact must be traceable to the record's own material. The call
reads a rich session brief (who the acts are, everything sung and said across
the rounds, the Critic's own review) plus the catalog shelf as differ-from
pressure. Nothing the Critic writes ever feeds forward into any brief; the
name is the last word said about a set, not the first.

The voice is ported from mold's Critic (verdict-first, zero warmth, pan when
panning is earned) and adapted to AFAR's register: third person, surnames,
retrospective, and — because reviews are public prose — the plain-language
rule: readable by someone with no music-production and no AI background.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ensemble.agent import Agent, Artifact, Decision, Perception, Persona
from ensemble.providers.model import Message, ModelProvider

from afar.agents.robust import staff_complete
from afar.intent import ERAS, _loads_lenient
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


#: The naming law, appended to every naming call. This is the tunz process
#: (profile.ts), not a rule list: one traceability law in place of ban
#: inventories — the two earlier rule-list cures (2026-08-01, twice) each
#: just grew a new rut. What remains of them is three lines of residue at
#: the end, the catalog's certified dead molds.
_NAMING_LAW = """\
THE TRACEABILITY LAW. Every artifact on this sleeve must be traceable to \
the record: each title names something actually sung or said on the tape — \
a thing, an image, a phrase an act put on the record — and the description \
reads the takes as one body of work, built from the record's own images. \
Nothing on the sleeve is invented from outside the record, and nothing is \
named in isolation: the release title, its description, and the take titles \
leave your desk in the same breath and must cohere — and differ; four titles \
sharing one construction is one title written four times.

REGISTER. The description is 1-2 sentences on the record as a body of work, \
in the register of a music journalist's capsule note: concrete detail from \
the record, no generic praise. Each take title carries its why — one line \
pointing at the sung or spoken words the title came from.

HOUSE RESIDUE (this catalog's certified dead molds — never again):
- two fragments joined by a comma ("Three Rooms, No Doors")
- any title beginning with "Same"
- colons and subtitles\
"""


@dataclass(frozen=True)
class Review:
    """The Critic's verdicts: one per act, plus the word on the release."""

    per_act: dict[str, str]
    release: str


@dataclass(frozen=True)
class Names:
    """The last decision of a set: what the finished work is called — and,
    per the tunz process, why. The description and the whys arrive in the
    same call as the titles so the sleeve coheres."""

    release_title: str
    take_titles: dict[str, str]
    release_description: str = ""  # 1-2 sentences, the record as a body of work
    take_notes: dict[str, str] = field(default_factory=dict)  # pid -> one-line why


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

    # -- the name, last (the tunz bundle: one call, whole sleeve) --------------

    def name(
        self,
        view: SetView,
        selection: Any,
        review: Review,
        recent_titles: Sequence[str] = (),
    ) -> Names:
        """Name the whole sleeve in one structured call — the tunz process.

        The call reads a rich session brief: who each act is (their stance and
        the DNA of their selected take), everything sung and everything said
        across the rounds (the discards included — titles grow from the
        session's whole material, the way tunz grows titles from the whole
        DNA), and the Critic's own review. It returns the release title, the
        1-2 sentence body-of-work description, and each take's title WITH its
        one-line why — bundled, so nothing is named in isolation. The measured
        story (drift numbers) and the acts' private rationales stay out: the
        sleeve is traceable to what a listener can hear, not to the meters.
        `recent_titles` is the catalog shelf, kept as differ-from pressure.
        It runs last and feeds nothing forward.
        """
        acts_brief: dict[str, Any] = {}
        sung: dict[str, list[dict[str, Any]]] = {}
        for pid, choice in selection.takes.items():
            stage = STAGE_NAMES.get(pid, pid)
            takes = view.takes.get(pid, [])
            selected = next((t for t in takes if t.round == choice.round), None)
            intent = dict(selected.intent) if selected is not None else {}
            era = intent.get("era")
            acts_brief[stage] = {
                "player_id": pid,
                "stance": view.commitments.get(pid, ""),
                "the_artist_they_set_out_to_be": intent.get("seedPrompt", ""),
                "era": ERAS[era] if isinstance(era, int) and 0 <= era < len(ERAS) else era,
                "lyrical_obsessions": intent.get("lyricalObsessions", []),
            }
            sung[stage] = [
                {
                    "round": t.round,
                    "said": t.line,
                    "sung": t.lyrics,
                    **({"on_the_release": True} if t.round == choice.round else {}),
                }
                for t in takes
            ]
        acts_line = ",".join(selection.takes)
        shelf = ""
        if recent_titles:
            shelf = (
                "\n\nALREADY ON THE SHELF (recent titles across the catalog): "
                "this sleeve must fit the record it is on but differ from "
                "everything here — no shared first word, construction, or "
                "cadence.\n"
                + json.dumps(list(recent_titles), indent=1, ensure_ascii=False)
            )
        prompt = (
            "The release is cut and reviewed. Write its sleeve — the whole "
            "sleeve, in one breath: the release title, the description of the "
            "record as a body of work, and each act's take title with its why.\n\n"
            "WHO WAS IN THE ROOM:\n"
            + json.dumps(acts_brief, indent=1, ensure_ascii=False)
            + "\n\nEVERYTHING SUNG AND SAID, round by round ('on_the_release' "
            "marks the takes that shipped; the rest is the session the titles "
            "grew out of):\n"
            + json.dumps(sung, indent=1, ensure_ascii=False)
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
            + _NAMING_LAW
            + "\nRelease title 1-5 words; take titles 1-6 words; plain "
            "language, no quotation marks inside titles. Reply with ONE JSON "
            'object, nothing else: {"release_title": "<title>", '
            '"release_description": "<1-2 sentences>", '
            '"take_titles": {"<player_id>": {"title": "<title>", '
            '"why": "<one line: the sung or spoken words it came from>"}}} — '
            "one take_titles entry per player id on the ACTS line."
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
        titles: dict[str, str] = {}
        notes: dict[str, str] = {}
        for pid in selection.takes:
            entry = data["take_titles"][pid]
            if isinstance(entry, Mapping):  # the bundle shape
                titles[pid] = str(entry.get("title", "")).strip()
                notes[pid] = str(entry.get("why", "")).strip()
            else:  # a bare string still names the take (degrade, don't die)
                titles[pid] = str(entry).strip()
        return Names(
            release_title=str(data["release_title"]).strip(),
            take_titles=titles,
            release_description=str(data.get("release_description", "")).strip(),
            take_notes=notes,
        )
