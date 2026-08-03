"""The Archivist: where everything belongs — and the prose on the back.

Every record that comes out of this world goes on the public shelf, and the
Archivist decides each one's PLACE: is it a companion to something else, a
standalone that is its own argument, or part of a collection? What should a
listener put their ear against? That placement is the one decision; the LINER
NOTES — back-of-sleeve prose for records, tapes, and the imported acts' back
catalogues — are how the decision is written down.

THE ARCHIVIST NEVER RE-TITLES ANYTHING. On an album the artist wrote the
title and the description before a note existed (docs/SPEC.md: the title
comes first), and the liner notes are a reaction to a record that is already
named. `shelve_album` cannot title: there is no title field on what it
returns and no title asked for in what it sends. The tape titles under the
EXPERIMENT-ONLY banner belong to the round-based instrument's SESSION TAPES —
raw session material nobody ever named — and never to a record.

The Archivist is not the Critic. The Critic judges; the Archivist
contextualizes: what is on the record, what changed, what to listen for.
Their verdicts stay separate on every sleeve.

Like every staff reaction it degrades rather than voids: a failed Archivist
logs `staff_stage_failed` and the record stands unshelved (afar.staff).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ensemble.agent import Agent, Artifact, Decision, Perception, Persona
from ensemble.providers.model import Message, ModelProvider

from afar.album import Album
from afar.agents.robust import staff_complete
from afar.archive import TapeView
from afar.intent import _loads_lenient
from afar.staff import album_digest


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
around them. Everyone else here reacts to what comes out; nobody \
here decides what gets made. You make the one decision only you make: where \
everything belongs. \
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
stage names, never by internal ids. The log hands you internal numbers and \
dial names (drift values, palette axes like "coldWarm") — those are YOUR \
evidence, never your prose, and they never survive inside a quote either: \
trim a quoted line rather than let a dial name through."""


@dataclass(frozen=True)
class AlbumShelving:
    """The Archivist's decision for one finished record — placement and prose.

    There is deliberately NO title field. The artist named this record; the
    Archivist shelves it and writes the back of the sleeve, and cannot rename
    it even by accident."""

    placement: str  # one of PLACEMENTS
    arc: str  # 1-2 sentences: the record's shape, first song to last
    notes: str  # the liner notes — back-of-sleeve prose
    callouts: tuple[dict[str, Any], ...] = ()  # {song, note}


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
    """The staff agent with the ledger and the shelves. `shelve_album()` is the
    live surface: one call, one record's place and its liner notes — and no
    title, ever.

    The ensemble Agent loop (perceive/decide/execute) and `shelve()` below it
    shelve a round-based SESSION TAPE and belong to the EXPERIMENT-ONLY
    instrument. `album_liner_notes()` stays live for the imported acts' back
    catalogues."""

    def __init__(self, model: ModelProvider, **kw: Any) -> None:
        persona = Persona(
            name="THE ARCHIVIST",
            base_prompt=_ARCHIVIST_PROMPT,
            personality=ONE_DECISION,
            metadata={"agent_id": "archivist"},
        )
        super().__init__(persona, model, **kw)

    # -- the one decision, on a record: where it belongs -----------------------

    def shelve_album(self, album: Album, *, artist_name: str = "") -> AlbumShelving:
        """Shelve a finished record and write the back of its sleeve.

        Reads the sleeve and the words as the artist wrote them
        (afar.staff.album_digest). Returns the placement, the record's arc,
        up to three songs worth an ear, and the liner notes. It is asked for
        no title and it returns no title: the record was named by the artist
        before any of this existed.
        """
        digest = album_digest(album, artist_name=artist_name)
        prompt = (
            "Shelve this record and write the back of its sleeve.\n\n"
            "THE RECORD (the artist's own title, description and words — all "
            "written before a note of it existed):\n"
            + json.dumps(digest, indent=1, ensure_ascii=False)
            + "\n\nTHE RECORD IS ALREADY NAMED. The title and the description "
            "are the artist's, and they are final: use them exactly, never "
            "suggest another, never write a title of your own for the record or "
            "for any song on it. Your job is where it belongs and what a "
            "listener should put their ear against.\n"
            "Everything you write must be traceable to the record — the arc and "
            "the notes are built from these songs, and nothing is invented from "
            "outside them.\n"
            "Reply with ONE JSON object, nothing else: "
            '{"placement": "companion|standalone|collection", '
            '"arc": "<1-2 sentences: the record\'s shape, first song to last>", '
            '"callouts": [{"song": "<the artist\'s song title, verbatim>", '
            '"note": "<one sentence: what to listen for>"}], '
            '"liner_notes": "<the back-of-sleeve prose: 2-3 short paragraphs — '
            "what is on this record, what changed across it, what to listen for; "
            'quote the artist\'s own words where they earn it>"}'
            "\nPlacement guide: companion = it stands beside another record "
            "(this artist's last, or one it was clearly answering); standalone = "
            "it is its own argument and holds the shelf alone; collection = it "
            "belongs grouped with siblings. Call out at most 3 songs."
        )

        def parse(raw: str) -> AlbumShelving:
            data = _loads_lenient(raw)
            if not isinstance(data, Mapping) or "placement" not in data or "liner_notes" not in data:
                raise ValueError("archivist album shelving reply is not the expected JSON object")
            placement = str(data["placement"]).strip().lower()
            if placement not in PLACEMENTS:
                raise ValueError(
                    f"archivist placement {data['placement']!r} is not one of {PLACEMENTS}"
                )
            notes = str(data["liner_notes"]).strip()
            if not notes:
                raise ValueError("the archivist's liner notes came back empty")
            titles = {t.title for t in album.tracks}
            callouts = tuple(
                {"song": str(c.get("song", "")).strip(), "note": str(c["note"]).strip()}
                for c in data.get("callouts", [])
                if isinstance(c, Mapping)
                and c.get("note")
                and str(c.get("song", "")).strip() in titles
            )[:3]
            return AlbumShelving(
                placement=placement,
                arc=str(data.get("arc", "")).strip(),
                notes=notes,
                callouts=callouts,
            )

        return staff_complete(
            self.model,
            [
                Message(role="system", content=_ARCHIVIST_PROMPT),
                Message(role="user", content=prompt),
            ],
            stage="archivist/album-shelving",
            parse=parse,
        )

    # === EXPERIMENT-ONLY from here down ======================================
    # Shelving a SESSION TAPE (rounds, takes, a cut, a veto) and writing a
    # round-based release's liner notes belong to the round-based instrument
    # (afar.staff_rounds, behind AFAR_EXPERIMENT_MODE). A tape is raw session
    # material nobody ever named, so the Archivist titles it — that is the one
    # place a title is the Archivist's to write, and it is not a record.
    # `album_liner_notes` (the imported acts' back catalogues) stays live: it
    # writes prose for a record the act brought with them, and titles nothing.

    def shelve(
        self,
        view: TapeView,
        *,
        stage_names: Mapping[str, str],
        recent_tape_titles: Sequence[str] = (),
    ) -> Shelving:
        perception = self.perceive(
            {
                "view": view,
                "stage_names": dict(stage_names),
                "recent_tape_titles": list(recent_tape_titles),
            }
        )
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
                "recent_tape_titles": list(context.get("recent_tape_titles", ())),
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
            + (
                "\n\nALREADY ON THE SHELF (recent tape titles — yours must not "
                "echo their words, their openings, or their cadence; a shelf "
                "where every spine scans alike is shelved wrong):\n"
                + json.dumps(d["recent_tape_titles"], indent=1, ensure_ascii=False)
                if d["recent_tape_titles"]
                else ""
            )
            + "\n\nDecide where this tape belongs and write its sleeve — the "
            "whole sleeve in one breath, title and notes together, so it "
            "coheres. THE TRACEABILITY LAW: everything on the sleeve must be "
            "traceable to the tape — the title names something actually on it "
            "(a sung image, a spoken phrase, the thing that happened), the arc "
            "and notes are built from the takes you were handed, and nothing "
            "is invented from outside the tape. House residue (dead molds, "
            "never again): two fragments joined by a comma; colons. "
            "Reply with ONE JSON object, nothing else: "
            '{"placement": "companion|standalone|collection", '
            '"tape_title": "<a short plain archival name, traceable to the tape; '
            "for a solo tape the act's name may lead>\", "
            '"arc": "<1-2 sentences: the session\'s shape, start to end — the '
            'spine note that justifies the title in the same breath>", '
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
