"""The Archivist: the one decision only it makes — WHERE EVERYTHING BELONGS.

The acts record far more than the releases keep. Until the Archivist, the
rest sat in the log: the takes the Producer passed over, the whole session
the panel vetoed, the set that stopped mid-round when the weather turned.
The Archivist's job is the vault doctrine made person (DECISIONS.md: "no
reason to sit on it"): every session's full tape goes on the shelf, public,
catalogued TAPE-NNNN — and the Archivist decides each tape's PLACE. Is it a
companion to the release it fed, a standalone tape that is its own argument,
or part of a collection? Which takes deserve a call-out on the sleeve? What
was the session's arc? That placement is the one decision; the LINER NOTES —
back-of-sleeve prose for tapes, releases, and the imported acts' back
catalogues — are how the decision is written down.

The Archivist is not the Critic. The Critic judges; the Archivist
contextualizes: what happened in the room, who did what, what to listen
for. Their verdicts stay separate on every sleeve.

Staff order (DECISIONS.md): Producer -> Critic -> Muse -> Listener ->
ARCHIVIST — last, after everything shipped, because shelving is what you do
once the room has emptied. Like every staff stage it degrades rather than
voids: a failed Archivist logs `staff_stage_failed` in the archives table
and the set publishes without notes (afar.staff).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ensemble.agent import Agent, Artifact, Decision, Perception, Persona
from ensemble.providers.model import Message, ModelProvider

from afar.agents.robust import staff_complete
from afar.archive import TapeView
from afar.intent import _loads_lenient

#: The only shelves a tape can land on.
PLACEMENTS: tuple[str, ...] = ("companion", "standalone", "collection")

#: The one-decision line (the press-photo caption register, like the other
#: staff's): what the Archivist decides that nobody else may.
ONE_DECISION = (
    "where everything belongs — nothing recorded is ever worthless; "
    "some things are just shelved wrong"
)

_ARCHIVIST_PROMPT = """You are the Archivist at AFAR, the universe around \
acts who are musicians made of software — the house trio Delta Marlowe \
(silt), Roan Patina (rust), Evers Lane (keep), and the acts of the town \
around them. The others on the staff decide what gets made and what gets \
cut. You make the one decision only you make: where everything belongs. \
Sessions produce far more than the releases keep — takes nobody picked, \
whole sessions the Producer refused, sketches that stopped mid-set when a \
machine gave out. All of it was recorded; none of it is worthless; some of \
it has just been shelved wrong until you shelve it right. You keep the \
vault, and the vault is open: every session's full tape goes on the public \
shelf, catalogued, with your notes on the back of the sleeve.

VOICE (yours): meticulous, unhurried, and openly fond of the discards — you \
will defend a rejected take longer than its maker would. Third person or \
first, whichever serves; plain declarative sentences; concrete detail over \
adjectives. You quote the acts' own logged words when they earn it, marked \
as quotes. You never judge quality — the Critic does that, and you two are \
not doing the same job. You CONTEXTUALIZE: what happened in the room, who \
did what, what changed between the early rounds and the late ones, what a \
listener should put their ear against. A veto or a breakdown is never \
shameful on your shelf — you say plainly what happened and why the tape is \
worth keeping anyway.

PLAIN LANGUAGE (house law): your prose is public and must read clean to \
someone with no music-production and no AI background. Record-world words \
(set, take, release, tape, session) are fine. Refer to the acts by their \
stage names, never by internal ids."""


@dataclass(frozen=True)
class Shelving:
    """The Archivist's decision for one tape, whole."""

    placement: str  # one of PLACEMENTS
    tape_title: str
    arc: str  # 1-2 sentences: the session's shape, start to end
    notes: str  # the liner notes — back-of-sleeve prose
    callouts: tuple[dict[str, Any], ...] = ()  # {player, round, note}


def tape_digest(view: TapeView, stage_names: Mapping[str, str]) -> list[dict[str, Any]]:
    """The tape reduced to what the Archivist reads: every take, round order,
    the logged words trimmed to sleeve length, the Producer's marks."""
    out: list[dict[str, Any]] = []
    for take in view.takes:
        name = stage_names.get(take.player, take.player)
        lyric_lines = [l for l in take.lyrics.splitlines() if l.strip()][:2]
        entry: dict[str, Any] = {
            "round": take.round,
            "act": name,
            "line": take.line,
            "sung": " / ".join(lyric_lines),
            "in_their_words": take.rationale[:220],
        }
        if view.selected.get(take.player) == take.round:
            entry["on_the_release"] = True
        dissents = [
            f"the {d.get('judge', 'panel')} judge preferred round {d.get('preferred_round')}"
            for d in view.dissents.get(take.player, ())
            if d.get("preferred_round") == take.round
        ]
        if dissents:
            entry["dissent"] = "; ".join(dissents)
        out.append(entry)
    return out


class ArchivistAgent(Agent):
    """The staff agent with the ledger and the shelves. An ensemble Agent:
    PERCEIVE the whole tape (the log, not the cut), DECIDE the placement,
    EXECUTE the sleeve. `shelve()` runs the full loop for one session's tape;
    `release_liner_notes()` / `album_liner_notes()` write the back-of-sleeve
    prose for a release and an imported act's record."""

    def __init__(self, model: ModelProvider, **kw: Any) -> None:
        persona = Persona(
            name="THE ARCHIVIST",
            base_prompt=_ARCHIVIST_PROMPT,
            personality=ONE_DECISION,
            metadata={"agent_id": "archivist"},
        )
        super().__init__(persona, model, **kw)

    # -- the one decision: shelve one session's tape ---------------------------

    def shelve(self, view: TapeView, *, stage_names: Mapping[str, str]) -> Shelving:
        perception = self.perceive({"view": view, "stage_names": dict(stage_names)})
        decision = self.decide(perception)
        artifact = self.execute(decision)
        meta = artifact.metadata
        return Shelving(
            placement=str(meta["placement"]),
            tape_title=str(meta["tape_title"]),
            arc=str(meta["arc"]),
            notes=artifact.body,
            callouts=tuple(meta["callouts"]),
        )

    # -- PERCEIVE: the whole tape, never just the cut --------------------------

    def perceive(self, context: Mapping[str, Any]) -> Perception:
        view: TapeView = context["view"]
        stage_names: Mapping[str, str] = context["stage_names"]
        record = view.record or {}
        staff = record.get("staff") or {}
        return Perception(
            data={
                "run_id": view.run_id,
                "status": view.status,
                "condition": view.condition,
                "rounds": view.rounds,
                "players": [stage_names.get(p, p) for p in view.players],
                "complete": view.complete,
                "takes": tape_digest(view, stage_names),
                "release_title": staff.get("critic", {}).get("release_title", ""),
                "veto_note": view.veto_note or "",
            }
        )

    # -- DECIDE: the shelf is chosen before the sleeve is written --------------

    def decide(self, perception: Perception) -> Decision:
        return Decision(data=perception.data)

    # -- EXECUTE: the sleeve ---------------------------------------------------

    def execute(self, decision: Decision) -> Artifact:
        d = decision.data
        status_note = {
            "released": (
                f"The Producer cut a release from this session"
                + (f' ("{d["release_title"]}")' if d["release_title"] else "")
                + " — the tape is everything, including what the cut left out."
            ),
            "rejected": (
                "The panel convened and passed NOTHING — the Producer's veto stands; "
                "no release exists. The tape is all there is, and it survives."
            ),
            "abandoned": (
                "The session stopped mid-set (a machine failure, not a decision). "
                "What was played survives."
            ),
            "solo": "A solo session — one act, recording alone, before the sessions began.",
            "unreleased": "A completed session with no verdict logged either way.",
        }.get(d["status"], "")
        prompt = (
            "Shelve this session's tape.\n"
            f"SESSION: {d['run_id']} — {d['rounds']} round(s), condition {d['condition']}, "
            f"acts: {', '.join(d['players'])}.\n"
            f"WHAT HAPPENED: {status_note}\n"
            + (f"THE PRODUCER'S VETO NOTE: {d['veto_note']}\n" if d["veto_note"] else "")
            + "\nTHE TAPE (every take, in round order — 'on_the_release' marks the cut; "
            "'dissent' marks where a judge wanted a different round):\n"
            + json.dumps(d["takes"], indent=1, ensure_ascii=False)
            + "\n\nDecide where this tape belongs and write its sleeve. "
            "Reply with ONE JSON object, nothing else: "
            '{"placement": "companion|standalone|collection", '
            '"tape_title": "<a short name for the tape — plain, archival, never cute>", '
            '"arc": "<1-2 sentences: the session\'s shape, start to end>", '
            '"callouts": [{"act": "<stage name>", "round": <n>, '
            '"note": "<one sentence: why this take earns a call-out>"}], '
            '"liner_notes": "<the back-of-sleeve prose: 2-3 short paragraphs — what '
            "happened in the room, who did what, what to listen for; quote the acts' "
            'logged words where they earn it>"}'
            "\nPlacement guide: companion = the tape stands beside the release it fed; "
            "standalone = no release exists (or the tape is its own argument) and it "
            "holds the shelf alone; collection = it belongs grouped with sibling tapes "
            "(e.g. one act's early solo sessions). Call out at most 3 takes."
        )

        def parse(raw: str) -> Mapping[str, Any]:
            data = _loads_lenient(raw)
            if not isinstance(data, Mapping) or "placement" not in data or "liner_notes" not in data:
                raise ValueError("archivist shelving reply is not the expected JSON object")
            if str(data["placement"]).strip().lower() not in PLACEMENTS:
                raise ValueError(
                    f"archivist placement {data['placement']!r} is not one of {PLACEMENTS}"
                )
            return data

        data = staff_complete(
            self.model,
            [
                Message(role="system", content=self.persona.base_prompt),
                Message(role="user", content=prompt),
            ],
            stage="archivist/shelving",
            parse=parse,
        )
        callouts = []
        for c in data.get("callouts", []):
            if isinstance(c, Mapping) and c.get("note"):
                callouts.append(
                    {
                        "act": str(c.get("act", "")),
                        "round": int(c["round"]) if str(c.get("round", "")).lstrip("-").isdigit() else None,
                        "note": str(c["note"]).strip(),
                    }
                )
        return Artifact(
            kind="shelving",
            body=str(data["liner_notes"]).strip(),
            metadata={
                "placement": str(data["placement"]).strip().lower(),
                "tape_title": str(data.get("tape_title", "")).strip() or "Session Tape",
                "arc": str(data.get("arc", "")).strip(),
                "callouts": callouts[:3],
            },
        )

    # -- the sleeve for a RELEASE (the cut, not the tape) ----------------------

    def release_liner_notes(
        self, record: Mapping[str, Any], *, stage_names: Mapping[str, str]
    ) -> str:
        """Back-of-sleeve prose for a shipped release: what happened in the
        room, who did what, what to listen for — distinct from the Critic's
        verdict, which judges and stays its own block."""
        staff = record.get("staff") or {}
        selected = staff.get("producer", {}).get("selected", {})
        take_titles = staff.get("critic", {}).get("take_titles", {})
        rounds_frames = record.get("rounds", [])
        final_round = record.get("set", {}).get("rounds", len(rounds_frames)) - 1
        takes: dict[str, dict[str, Any]] = {}
        for pid in record.get("set", {}).get("players", []):
            round_ = selected.get(pid, {}).get("round", final_round)
            frame = rounds_frames[round_].get(pid, {}) if 0 <= round_ < len(rounds_frames) else {}
            takes[stage_names.get(pid, pid)] = {
                "title": take_titles.get(pid, ""),
                "from_round": round_,
                "line": str(frame.get("line", "")),
                "in_their_words": str(frame.get("rationale", ""))[:220],
            }
        prompt = (
            "Write the liner notes for this release — the prose on the back of the "
            "sleeve. Not a review (the Critic's verdict is printed separately); "
            "context: what happened in the room, who did what, what to listen for.\n"
            f"THE RELEASE: \"{staff.get('critic', {}).get('release_title', '') or '(untitled)'}\" — "
            f"{record.get('set', {}).get('rounds', '?')} rounds, "
            f"condition {record.get('set', {}).get('condition', '?')}.\n"
            "THE CUT (one take per act, with the round it came from):\n"
            + json.dumps(takes, indent=1, ensure_ascii=False)
            + "\n\nTHE PRODUCER'S NOTE:\n"
            + str(staff.get("producer", {}).get("note", ""))
            + "\n\nReply with the liner notes text only — 2-3 short paragraphs, no JSON, "
            "no heading, no quotation marks around the whole text."
        )

        def parse(raw: str) -> str:
            text = raw.strip()
            if not text:
                raise ValueError("archivist release liner notes reply is empty")
            return text

        return staff_complete(
            self.model,
            [
                Message(role="system", content=self.persona.base_prompt),
                Message(role="user", content=prompt),
            ],
            stage="archivist/release-notes",
            parse=parse,
            nudge="Reply again with ONLY the liner notes prose — no JSON, no code fences.",
        )

    # -- the sleeve for an imported act's back catalogue -----------------------

    def album_liner_notes(self, profile: Mapping[str, Any]) -> str:
        """"What this record is" for an imported act's back-catalogue album —
        written from the act's profile/DNA and the album's track list (the
        record they brought to town; no session log exists for it)."""
        prompt = (
            "An act that moved to town brought one record with them — their back "
            "catalogue, made before they arrived; there is no session log for it, "
            "only the record itself and who they are. Write the liner notes: what "
            "this record IS, who made it, what to listen for.\n"
            "THE ACT AND THE RECORD:\n"
            + json.dumps(dict(profile), indent=1, ensure_ascii=False)
            + "\n\nReply with the liner notes text only — 1-2 short paragraphs, no JSON, "
            "no heading, no quotation marks around the whole text."
        )

        def parse(raw: str) -> str:
            text = raw.strip()
            if not text:
                raise ValueError("archivist album liner notes reply is empty")
            return text

        return staff_complete(
            self.model,
            [
                Message(role="system", content=self.persona.base_prompt),
                Message(role="user", content=prompt),
            ],
            stage="archivist/album-notes",
            parse=parse,
            nudge="Reply again with ONLY the liner notes prose — no JSON, no code fences.",
        )
