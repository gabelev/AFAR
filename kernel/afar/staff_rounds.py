"""EXPERIMENT-ONLY: the round-based staff instrument (the pre-album machinery).

Nothing in this module runs on an album. It is the ROUND-BASED set machinery
— the Producer's panel and cut, the 'no release' veto, the Critic's naming
call, the Muse's brief — kept whole behind `AFAR_EXPERIMENT_MODE` as the
offline experiment instrument, and as the code that reproduces the logged
round-based history (releases 0001-0007, TAPE-0001..0017) exactly as it was
written (docs/SPEC.md; DECISIONS 2026-08-03: "run_set, build_context's round
machinery and the condition draws stay as the offline experiment instrument
behind the flag").

The LIVE piece does not come here. An artist writes a whole album in its own
voice, the album is published, and the staff REACT to it — `afar.staff`'s
`run_reactions`, which has no cut, no veto, no naming call and no brief. The
one remaining live caller of anything in this file is the pre-album
conductor, which goes when the conductor lands on the album spine.

WHAT IT DOES (unchanged from the round-based architecture): `run_staff` takes
a COMPLETED run's append-only log, walks Producer, Critic, Muse, Listener,
Archivist over it in order, appends their decisions as new `selections` /
`reviews` / `briefs` / `reactions` / `archives` rows, and writes new
content-addressed release records that supersede the previous one — the same
append-only correction pattern as `scripts/reembed.py`. Nothing here ever
edits a logged row.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from afar.config import AfarConfig
from afar.intent import ERAS
from afar.log import JsonlLedger, RunContext
from afar.staff import (
    STAGE_NAMES,
    _load_recent_rows,
    _read_jsonl,
    _short_error,
    load_recent_reactions,
    newest_release_path,
)

__all__ = [
    "ArchiveOutcome",
    "BoundaryRecord",
    "SetView",
    "STAGE_DEGRADED_NOTES",
    "StaffRecord",
    "TakeRow",
    "load_recent_tape_titles",
    "load_recent_titles",
    "load_set_view",
    "run_archivist",
    "run_muse_listener",
    "run_staff",
    "take_digest",
]


@dataclass(frozen=True)
class TakeRow:
    """One logged take, re-read from the run's JSONL — the judges' only ears."""

    player: str
    round: int
    take_id: str  # artifact content hash
    intent_id: str
    intent: Mapping[str, Any]  # the DNA dict as logged
    line: str
    lyrics: str
    rationale: str
    path: str  # mp3 path from the artifacts row (never read by staff; publish uses it)


@dataclass(frozen=True)
class SetView:
    """A completed set as the staff see it: the log, whole, nothing else."""

    run_id: str
    condition: str
    seed: int
    rounds: int
    players: tuple[str, ...]
    takes: Mapping[str, list[TakeRow]]  # player -> takes in round order
    record: Mapping[str, Any]  # the newest content-addressed release record
    commitments: Mapping[str, str] = field(default_factory=dict)  # player -> stance

    def take_at(self, player: str, round_: int) -> TakeRow:
        return self.takes[player][round_]

    def story_digest(self) -> str:
        """The set's measured story, in judge-readable plain terms.

        Leads with INTENT space per DECISIONS.md (audio space is computed but
        flagged weak until the persona gate passes in audio).
        """
        conv = self.record.get("convergence", {}).get("intent", [])
        lines = [
            "THE MEASURED STORY (from what the acts set out to make, round by round):",
            "- drift toward each other per round (higher = closer): "
            + ", ".join(f"r{t}={v:+.3f}" for t, v in enumerate(conv)),
        ]
        influence = self.record.get("influence", {}).get("intent", {})
        for t in sorted(influence, key=int):
            edges = influence[t]
            lines.append(
                f"- round {t} pull (a<-b: how much b pulled a; higher/less negative = pulled harder): "
                + ", ".join(f"{k}={v:+.2f}" for k, v in sorted(edges.items()))
            )
        return "\n".join(lines)

    def round_context(self, *, exclude: str) -> list[dict[str, Any]]:
        """Per round, the OTHER acts' takes — for the distinctness grounding."""
        out: list[dict[str, Any]] = []
        for t in range(self.rounds):
            out.append(
                {
                    "round": t,
                    "others": {
                        pid: {"line": self.takes[pid][t].line, "lyrics": self.takes[pid][t].lyrics}
                        for pid in self.players
                        if pid != exclude
                    },
                }
            )
        return out


def take_digest(t: TakeRow) -> dict[str, Any]:
    """One take reduced to what a log-reading judge can honestly weigh."""
    influences = ", ".join(
        f"{i['genre']} {round(i['weight'] * 100)}%" for i in t.intent.get("influences", [])
    )
    era = t.intent.get("era")
    return {
        "round": t.round,
        "era": ERAS[era] if isinstance(era, int) and 0 <= era < len(ERAS) else era,
        "influences": influences,
        "palette": {k: round(v, 2) for k, v in t.intent.get("sonicPalette", {}).items()},
        "line": t.line,
        "lyrics": t.lyrics,
        "rationale": t.rationale,
    }


def load_set_view(run_dir: Path) -> SetView:
    """Rebuild one completed set from its authoritative JSONL log."""
    run_dir = Path(run_dir)
    (run_row,) = _read_jsonl(run_dir / "runs.jsonl")
    record = json.loads(newest_release_path(run_dir).read_text(encoding="utf-8"))
    intents = _read_jsonl(run_dir / "intents.jsonl")
    artifacts = _read_jsonl(run_dir / "artifacts.jsonl")
    art_by = {(row["round"], row["player"]): row for row in artifacts}

    players: tuple[str, ...] = tuple(run_row["players"])
    rounds: int = run_row["rounds"]
    takes: dict[str, list[TakeRow]] = {pid: [] for pid in players}
    for row in sorted(intents, key=lambda r: (r["round"], r["player"])):
        art = art_by[(row["round"], row["player"])]
        takes[row["player"]].append(
            TakeRow(
                player=row["player"],
                round=row["round"],
                take_id=art["hash"],
                intent_id=row["id"],
                intent=row["intent"],
                line=row["line"],
                lyrics=row.get("lyrics", ""),
                rationale=row.get("rationale", ""),
                path=art["path"],
            )
        )
    for pid in players:
        if len(takes[pid]) != rounds:
            raise ValueError(f"run {run_row['id']}: {pid} has {len(takes[pid])} takes, expected {rounds}")

    # The acts' standing commitments, for the intent-fidelity grounding.
    from afar.agents.personas import PERSONAS

    commitments = {
        pid: PERSONAS[pid].personality for pid in players if pid in PERSONAS
    }
    return SetView(
        run_id=run_row["id"],
        condition=run_row["condition"],
        seed=run_row["seed"],
        rounds=rounds,
        players=players,
        takes=takes,
        record=record,
        commitments=commitments,
    )


@dataclass(frozen=True)
class StaffRecord:
    """What one staff pass produced, and where its facts landed.

    `degraded` names the stages that failed after retries and were carried
    absent (the doctrine: a completed set is never voided by staff failure —
    the material always outranks the commentary)."""

    released: bool
    selection: Any  # afar.agents.producer.Selection
    review: Optional[Any]  # afar.agents.critic.Review
    names: Optional[Any]  # afar.agents.critic.Names
    brief: Optional[Any]  # afar.agents.muse.Brief
    reaction: Optional[Any]  # afar.agents.listener.Reaction
    release_record: Optional[dict[str, Any]]
    release_path: Optional[Path]
    superseded_release_id: str
    shelving: Optional[Any] = None  # afar.agents.archivist.Shelving (the tape's place)
    liner_notes: Optional[str] = None  # the Archivist's release liner notes
    degraded: tuple[str, ...] = ()


@dataclass(frozen=True)
class BoundaryRecord:
    """What the Muse + Listener half of the frame produced. Either piece may
    be None when its stage degraded (named in `degraded`)."""

    brief: Optional[Any]  # afar.agents.muse.Brief
    reaction: Optional[Any]  # afar.agents.listener.Reaction
    release_record: dict[str, Any]
    release_path: Path
    superseded_release_id: str
    degraded: tuple[str, ...] = ()


#: The honest public sentence each degraded stage leaves behind — what the
#: release page says instead of pretending the stage spoke (or hiding the gap).
STAGE_DEGRADED_NOTES: dict[str, str] = {
    "producer": (
        "The Producer did not file this time — the final round's takes stand, "
        "kept mechanically."
    ),
    "critic": "The Critic did not file this time.",
    "muse": "The Muse did not file this time — no brief carries forward from this release.",
    "listener": "The Listener did not file this time.",
    "archivist": (
        "The Archivist did not file this time — the session tape stands unshelved; "
        "the takes speak for themselves."
    ),
}


def _degraded_entry(stage: str, err: BaseException) -> dict[str, str]:
    return {"note": STAGE_DEGRADED_NOTES[stage], "error": _short_error(err)}


def _mechanical_selection(view: SetView) -> Any:
    """The Producer's degradation: the final round's takes, kept mechanically —
    release 0002's v1 behavior, now with an honest note instead of a panel."""
    from afar.agents.producer import Selection, TakeChoice

    final = view.rounds - 1
    takes = {}
    for pid in view.players:
        row = view.take_at(pid, final)
        takes[pid] = TakeChoice(
            player=pid,
            round=final,
            take_id=row.take_id,
            intent_id=row.intent_id,
            scores={},
            reasoning="mechanical: the Producer did not file; the final round's take stands",
            line=row.line,
            lyrics=row.lyrics,
            dissents=[],
        )
    return Selection(
        released=True,
        takes=takes,
        note=STAGE_DEGRADED_NOTES["producer"],
        failed_players=(),
    )


def _append_release_record(
    run_dir: Path,
    ledger: JsonlLedger,
    set_stamps: Mapping[str, Any],
    record_body: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    """Write one content-addressed release record (row + file) and return it.
    The single supersede path: everything staff-enriched goes through here."""
    canonical = json.dumps(record_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    release_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    release_record = {"release_id": release_id, **record_body}
    ledger.write("releases", {**set_stamps, "id": release_id, "record": release_record})
    release_path = run_dir / f"release-{release_id[:12]}.json"
    release_path.write_text(
        json.dumps(release_record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return release_record, release_path


def load_recent_titles(
    runs_root: Path, *, exclude_run: str | None = None, limit: int = 24
) -> list[str]:
    """Every title the Critic already put on the record (release and take,
    oldest first, deduped, last `limit`) — the naming call's diversity
    pressure. A namer that cannot see the shelf re-invents the same title
    shape until the whole catalog scans alike; this is how it sees the shelf."""
    titles: list[str] = []
    for row in _load_recent_rows(runs_root, "reviews", "titles", exclude_run=exclude_run):
        take_titles = row.get("take_titles") or {}
        for value in (row.get("release_title"), *dict(take_titles).values()):
            title = str(value or "").strip()
            if title and title not in titles:
                titles.append(title)
    return titles[-limit:]


def load_recent_tape_titles(
    runs_root: Path, *, exclude_run: str | None = None, limit: int = 12
) -> list[str]:
    """The recent tape titles already on the vault shelf (oldest first,
    deduped, last `limit`) — the Archivist's diversity pressure, same reason
    as the Critic's."""
    titles: list[str] = []
    for row in _load_recent_rows(runs_root, "archives", "shelving", exclude_run=exclude_run):
        title = str(row.get("tape_title") or "").strip()
        if title and title not in titles:
            titles.append(title)
    return titles[-limit:]


def run_muse_listener(
    run_dir: Path,
    config: AfarConfig,
    *,
    stance: str | None = None,
    taboo: Any = None,
    perceiver: Any = None,
) -> BoundaryRecord:
    """The outward-facing half of the frame: the Muse, then the Listener,
    AFTER the release exists.

    Requires the newest release record to carry the Producer's cut (a release
    must exist before anyone can hear it or carry it forward). Appends one
    `briefs` row and one `reactions` row, then writes a NEW content-addressed
    record whose staff block gains `muse` and `listener` — the same supersede
    pattern as the Producer/Critic pass, run second.

    The brief written here is by construction a CARRY-FORWARD: composed after
    the release it reads, consumed at the NEXT set's start by
    `ProducerAgent.direct`. `stance` comes from the schedule (the conductor's
    job); until the conductor exists it defaults to the first era's stance.
    """
    from afar.agents.listener import ListenerAgent
    from afar.agents.muse import MuseAgent
    from afar.perception.field import ProvenanceLog, build_perceiver
    from afar.schedule import ScheduleConfig
    from afar.state.field_taboo import FieldTabooMemory

    if stance is None:
        stance = ScheduleConfig().eras_stance_cycle[0]
    run_dir = Path(run_dir)
    record = json.loads(newest_release_path(run_dir).read_text(encoding="utf-8"))
    if (
        "producer" not in record.get("staff", {})
        and "producer" not in record.get("staff_degraded", {})
    ):
        raise ValueError(
            f"run {run_dir.name}: newest release record carries no Producer cut — "
            "the Muse and the Listener act only after a release exists"
        )
    (run_row,) = _read_jsonl(run_dir / "runs.jsonl")
    ledger = JsonlLedger(run_dir.parent, run_dir.name, context=RunContext(code_sha=config.code_sha))
    set_stamps = {"condition": run_row["condition"], "seed": run_row["seed"]}
    degraded: dict[str, dict[str, str]] = {}

    # --- the Muse: the brief, carried forward ---------------------------------
    # Each outward stage is wrapped INDIVIDUALLY (the degradation doctrine):
    # a Muse that fails after the retry ladder means no brief this boundary —
    # logged, absent, honest — never a voided set or a silenced Listener.
    brief: Any = None
    try:
        sink = ProvenanceLog()
        muse = MuseAgent(
            config.model,
            perceiver=perceiver if perceiver is not None else build_perceiver(config.live, config.model, sink),
            taboo=taboo if taboo is not None else FieldTabooMemory(stance=stance),
        )
        prior_reactions = load_recent_reactions(run_dir.parent, exclude_run=run_dir.name)
        brief = muse.compose(
            stance=stance,
            release_records=[record],
            reaction_rows=prior_reactions,
            stage_names=STAGE_NAMES,
            carried_forward=True,
        )
    except Exception as err:  # noqa: BLE001 — the material outranks the commentary
        degraded["muse"] = _degraded_entry("muse", err)
        ledger.write(
            "briefs",
            {
                **set_stamps,
                "kind": "staff_stage_failed",
                "agent": "muse",
                "stage": "muse",
                "error": _short_error(err),
                "note": STAGE_DEGRADED_NOTES["muse"],
                "basis_release_id": record["release_id"],
            },
        )
    else:
        ledger.write(
            "briefs",
            {
                **set_stamps,
                "kind": "brief",
                "agent": "muse",
                "stance": brief.stance,
                "theme": brief.theme,
                "text": brief.body,
                "palette_notes": list(brief.palette_notes),
                "forbidden_moves": list(brief.forbidden_moves),
                "sources": list(brief.sources),
                "thin": brief.thin,
                "carried_forward": brief.carried_forward,
                "basis_release_id": record["release_id"],
            },
        )

    # --- the Listener: the reception ------------------------------------------
    reaction: Any = None
    try:
        listener = ListenerAgent(config.model)
        reaction = listener.react(record, stage_names=STAGE_NAMES)
    except Exception as err:  # noqa: BLE001 — same doctrine, independent stage
        degraded["listener"] = _degraded_entry("listener", err)
        ledger.write(
            "reactions",
            {
                **set_stamps,
                "kind": "staff_stage_failed",
                "agent": "listener",
                "stage": "listener",
                "error": _short_error(err),
                "note": STAGE_DEGRADED_NOTES["listener"],
                "basis_release_id": record["release_id"],
            },
        )
    else:
        ledger.write(
            "reactions",
            {
                **set_stamps,
                "kind": "reaction",
                "agent": "listener",
                "valence": reaction.valence,
                "text": reaction.text,
                "disagreements_with_critic": list(reaction.disagreements_with_critic),
                "basis_release_id": record["release_id"],
            },
        )

    # --- the boundary-enriched, content-addressed release record --------------
    record_body = {key: value for key, value in record.items() if key != "release_id"}
    staff_block = dict(record_body.get("staff", {}))
    if brief is not None:
        staff_block["muse"] = {
            "stance": brief.stance,
            "theme": brief.theme,
            "text": brief.body,
            "palette_notes": list(brief.palette_notes),
            "forbidden_moves": list(brief.forbidden_moves),
            "sources": list(brief.sources),
            "thin": brief.thin,
            "carried_forward": brief.carried_forward,
        }
    if reaction is not None:
        staff_block["listener"] = {
            "valence": reaction.valence,
            "text": reaction.text,
            "disagreements_with_critic": list(reaction.disagreements_with_critic),
        }
    record_body["staff"] = staff_block
    merged_degraded = {**record.get("staff_degraded", {}), **degraded}
    if merged_degraded:
        record_body["staff_degraded"] = merged_degraded
    prior_staff = list(record.get("provenance", {}).get("staff", []))
    provenance: dict[str, Any] = {
        "staff": [
            *prior_staff,
            *(["muse"] if brief is not None else []),
            *(["listener"] if reaction is not None else []),
        ],
        "supersedes_release_id": record["release_id"],
    }
    if merged_degraded:
        provenance["staff_degraded"] = sorted(merged_degraded)
    record_body["provenance"] = provenance
    release_record, release_path = _append_release_record(run_dir, ledger, set_stamps, record_body)
    return BoundaryRecord(
        brief=brief,
        reaction=reaction,
        release_record=release_record,
        release_path=release_path,
        superseded_release_id=record["release_id"],
        degraded=tuple(degraded),
    )


@dataclass(frozen=True)
class ArchiveOutcome:
    """What the Archivist's pass over one session produced. Either piece may
    be None when the stage degraded (named in `degraded`)."""

    shelving: Optional[Any]  # afar.agents.archivist.Shelving
    liner_notes: Optional[str]  # release liner notes (released sessions only)
    release_record: Optional[dict[str, Any]]  # the archivist-enriched record, when written
    release_path: Optional[Path] = None
    degraded: tuple[str, ...] = ()


def run_archivist(run_dir: Path, config: AfarConfig) -> ArchiveOutcome:
    """The vault half of the frame: the Archivist shelves the session's FULL
    tape — release or no release — and, when a release exists, writes its
    liner notes.

    Appends one `archives` row (kind "shelving": placement, tape title, arc,
    callouts, liner notes — the tape's authoritative home; the published tape
    row mirrors it). For a released session the newest release record gains
    `staff.archivist` (liner notes + the tape block) via the same supersede
    pattern as every other staff stage. THE DEGRADATION DOCTRINE: a failed
    Archivist logs a `staff_stage_failed` row in `archives` and everything
    publishes without notes — the material always outranks the commentary.
    """
    from afar.agents.archivist import ArchivistAgent
    from afar.archive import load_tape_view

    run_dir = Path(run_dir)
    view = load_tape_view(run_dir)
    ledger = JsonlLedger(run_dir.parent, run_dir.name, context=RunContext(code_sha=config.code_sha))
    set_stamps: dict[str, Any] = {"condition": view.condition}
    record = dict(view.record) if view.record is not None else None
    basis = {"basis_release_id": record["release_id"]} if record else {}

    try:
        archivist = ArchivistAgent(config.model)
        liner_notes: Optional[str] = None
        if view.released and record is not None:
            liner_notes = archivist.release_liner_notes(record, stage_names=STAGE_NAMES)
        shelving = archivist.shelve(
            view,
            stage_names=STAGE_NAMES,
            recent_tape_titles=load_recent_tape_titles(
                run_dir.parent, exclude_run=run_dir.name
            ),
        )
    except Exception as err:  # noqa: BLE001 — the material outranks the commentary
        ledger.write(
            "archives",
            {
                **set_stamps,
                "kind": "staff_stage_failed",
                "agent": "archivist",
                "stage": "archivist",
                "error": _short_error(err),
                "note": STAGE_DEGRADED_NOTES["archivist"],
                **basis,
            },
        )
        return ArchiveOutcome(
            shelving=None, liner_notes=None, release_record=record, degraded=("archivist",)
        )

    ledger.write(
        "archives",
        {
            **set_stamps,
            "kind": "shelving",
            "agent": "archivist",
            "status": view.status,
            "placement": shelving.placement,
            "tape_title": shelving.tape_title,
            "arc": shelving.arc,
            "callouts": list(shelving.callouts),
            "liner_notes": shelving.notes,
            "release_liner_notes": liner_notes,
            **basis,
        },
    )

    if not (view.released and record is not None):
        # No release to enrich (a veto, an abandoned set, a solo run): the
        # archives row IS the shelving; the tape publishes from it directly.
        return ArchiveOutcome(shelving=shelving, liner_notes=None, release_record=record)

    record_body = {key: value for key, value in record.items() if key != "release_id"}
    staff_block = dict(record_body.get("staff", {}))
    staff_block["archivist"] = {
        "liner_notes": liner_notes,
        "tape": {
            "placement": shelving.placement,
            "tape_title": shelving.tape_title,
            "arc": shelving.arc,
            "callouts": list(shelving.callouts),
            "notes": shelving.notes,
        },
    }
    record_body["staff"] = staff_block
    prior_staff = list(record.get("provenance", {}).get("staff", []))
    provenance: dict[str, Any] = {
        "staff": [*prior_staff, "archivist"],
        "supersedes_release_id": record["release_id"],
    }
    if record.get("staff_degraded"):
        provenance["staff_degraded"] = sorted(record["staff_degraded"])
    record_body["provenance"] = provenance
    release_record, release_path = _append_release_record(
        run_dir, ledger, {**set_stamps, "seed": record.get("set", {}).get("seed")}, record_body
    )
    return ArchiveOutcome(
        shelving=shelving,
        liner_notes=liner_notes,
        release_record=release_record,
        release_path=release_path,
    )


def run_staff(
    run_dir: Path, config: AfarConfig, *, stance: str | None = None, taboo: Any = None
) -> StaffRecord:
    """Run the full staff retrospectively on one completed set — Producer,
    Critic, Muse, Listener, Archivist, in that order. See module docstring.

    Appends `selections` / `reviews` / `briefs` / `reactions` rows to the
    run's log and, when the Producer releases, writes NEW content-addressed
    release records whose `provenance.supersedes_release_id` chains name the
    records they build on — exactly the reembed correction pattern. On a 'no
    release' verdict the verdict is logged and NO new record is written: not
    releasing is a decision, not a correction — and with nothing shipped, the
    Muse and the Listener have nothing to hear (no brief, no reaction).

    THE DEGRADATION DOCTRINE (DECISIONS.md: the material always outranks the
    commentary): a completed set is never voided by staff failure. Each stage
    is wrapped individually; a stage that still fails after the retry ladder
    (afar.agents.robust) logs a `staff_stage_failed` row in its home table
    and the chain CONTINUES with that piece absent — Producer down means the
    final round's takes stand mechanically (release 0002's v1 behavior, with
    an honest note); Critic down means no titles and no review (the publish
    path placeholders honestly); Muse/Listener down means no brief/reaction
    this boundary. The set still yields a release record and PUBLISHES.
    Only `run_set` itself failing is a failed set.
    """
    from afar.agents.critic import CriticAgent
    from afar.agents.producer import ProducerAgent

    run_dir = Path(run_dir)
    view = load_set_view(run_dir)
    old_record = dict(view.record)
    ledger = JsonlLedger(run_dir.parent, run_dir.name, context=RunContext(code_sha=config.code_sha))
    set_stamps = {"condition": view.condition, "seed": view.seed}
    degraded: dict[str, dict[str, str]] = {}

    # --- the Producer's cut ---------------------------------------------------
    producer_filed = True
    try:
        producer = ProducerAgent(config.model)
        selection = producer.select(view)
    except Exception as err:  # noqa: BLE001 — the material outranks the commentary
        producer_filed = False
        degraded["producer"] = _degraded_entry("producer", err)
        ledger.write(
            "selections",
            {
                **set_stamps,
                "kind": "staff_stage_failed",
                "agent": "producer",
                "stage": "producer",
                "error": _short_error(err),
                "note": STAGE_DEGRADED_NOTES["producer"],
                "basis_release_id": old_record["release_id"],
            },
        )
        selection = _mechanical_selection(view)
    else:
        for pid in view.players:
            choice = selection.takes.get(pid)
            if choice is None:
                continue
            ledger.write(
                "selections",
                {
                    **set_stamps,
                    "kind": "take",
                    "agent": "producer",
                    "player": pid,
                    "round": choice.round,
                    "take_id": choice.take_id,
                    "intent_id": choice.intent_id,
                    "scores": choice.scores,
                    "reasoning": choice.reasoning,
                    "dissents": choice.dissents,
                    "basis_release_id": old_record["release_id"],
                },
            )
        ledger.write(
            "selections",
            {
                **set_stamps,
                "kind": "selection",
                "agent": "producer",
                "released": selection.released,
                "note": selection.note,
                "failed_players": list(selection.failed_players),
                "basis_release_id": old_record["release_id"],
            },
        )
        if not selection.released:
            # 'No release this set' is the Producer's DECISION — only a panel
            # that actually convened may refuse a release. A failed Producer
            # never voids the material (the degraded path above). The vault
            # doctrine holds even here — ESPECIALLY here: the Archivist still
            # shelves the session's tape; the veto stands, the tape survives.
            archive = run_archivist(run_dir, config)
            return StaffRecord(
                released=False,
                selection=selection,
                review=None,
                names=None,
                brief=None,
                reaction=None,
                release_record=None,
                release_path=None,
                superseded_release_id=old_record["release_id"],
                shelving=archive.shelving,
                degraded=archive.degraded,
            )

    # --- the Critic's word, then the name (last) ------------------------------
    review = None
    names = None
    try:
        critic = CriticAgent(config.model)
        review = critic.review(view, selection)
        # The Critic's shelf carries the WHOLE catalog's spines — release and
        # take titles AND the vault's tape titles — so a release can never be
        # named into a collision with an existing tape (the "Proof of a Hand"
        # / TAPE-0016 class, spotted in the round-three samples).
        shelf = load_recent_titles(run_dir.parent, exclude_run=run_dir.name)
        for tape_title in load_recent_tape_titles(run_dir.parent, exclude_run=run_dir.name):
            if tape_title not in shelf:
                shelf.append(tape_title)
        names = critic.name(view, selection, review, recent_titles=shelf)
    except Exception as err:  # noqa: BLE001 — same doctrine
        review = None
        names = None
        degraded["critic"] = _degraded_entry("critic", err)
        ledger.write(
            "reviews",
            {
                **set_stamps,
                "kind": "staff_stage_failed",
                "agent": "critic",
                "stage": "critic",
                "error": _short_error(err),
                "note": STAGE_DEGRADED_NOTES["critic"],
                "basis_release_id": old_record["release_id"],
            },
        )
    else:
        for pid in view.players:
            ledger.write(
                "reviews",
                {
                    **set_stamps,
                    "kind": "act-review",
                    "agent": "critic",
                    "player": pid,
                    "text": review.per_act[pid],
                },
            )
        ledger.write(
            "reviews",
            {**set_stamps, "kind": "release-review", "agent": "critic", "text": review.release},
        )
        ledger.write(
            "reviews",
            {
                **set_stamps,
                "kind": "titles",
                "agent": "critic",
                "release_title": names.release_title,
                "release_description": names.release_description,
                "take_titles": dict(names.take_titles),
                "take_notes": dict(names.take_notes),
            },
        )

    # --- the staff-enriched, content-addressed release record -----------------
    record_body = {key: value for key, value in old_record.items() if key != "release_id"}
    staff_block: dict[str, Any] = {}
    if producer_filed:
        staff_block["producer"] = {
            "selected": {
                pid: {
                    "round": choice.round,
                    "take_id": choice.take_id,
                    "intent_id": choice.intent_id,
                    "scores": choice.scores,
                    "reasoning": choice.reasoning,
                    "dissents": choice.dissents,
                }
                for pid, choice in selection.takes.items()
            },
            "note": selection.note,
        }
    if review is not None and names is not None:
        staff_block["critic"] = {
            "release_title": names.release_title,
            # The tunz bundle's extra sleeve text rides the record alongside
            # the fields the publish path already reads (title, take_titles):
            # the body-of-work description and each take title's one-line why.
            "release_description": names.release_description,
            "take_titles": dict(names.take_titles),
            "take_notes": dict(names.take_notes),
            "release_review": review.release,
            "act_reviews": dict(review.per_act),
        }
    record_body["staff"] = staff_block
    if degraded:
        record_body["staff_degraded"] = dict(degraded)
    provenance: dict[str, Any] = {
        "staff": [stage for stage in ("producer", "critic") if stage in staff_block],
        "supersedes_release_id": old_record["release_id"],
    }
    if degraded:
        provenance["staff_degraded"] = sorted(degraded)
    record_body["provenance"] = provenance
    _append_release_record(run_dir, ledger, set_stamps, record_body)

    # --- the Muse and the Listener, after the release exists ------------------
    # `taboo` (the conductor's era-scoped FieldTabooMemory) rides through so a
    # hostile era's observed field moves accumulate across its boundaries.
    boundary = run_muse_listener(run_dir, config, stance=stance, taboo=taboo)

    # --- the Archivist, last: the vault opens (release AND tape) --------------
    archive = run_archivist(run_dir, config)
    return StaffRecord(
        released=True,
        selection=selection,
        review=review,
        names=names,
        brief=boundary.brief,
        reaction=boundary.reaction,
        release_record=archive.release_record or boundary.release_record,
        release_path=archive.release_path or boundary.release_path,
        superseded_release_id=old_record["release_id"],
        shelving=archive.shelving,
        liner_notes=archive.liner_notes,
        degraded=tuple(
            stage
            for stage in ("producer", "critic", "muse", "listener", "archivist")
            if stage in degraded or stage in boundary.degraded or stage in archive.degraded
        ),
    )
