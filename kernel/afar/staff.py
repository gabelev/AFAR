"""The set boundary: where the staff are allowed to act.

Architecture rule 1 (the boundary rule): staff act on the FRAME between sets,
never inside one. This module is that frame. `run_staff` takes a COMPLETED
run's append-only log, walks the full staff over it in order — Producer,
Critic, Muse, Listener — appends their decisions as new `selections` /
`reviews` / `briefs` / `reactions` rows, and writes new content-addressed
release records that supersede the previous one — the same append-only
correction pattern as `scripts/reembed.py`. Nothing here ever edits a logged
row, and nothing here ever feeds forward into a player's context: the loop
closes at set boundaries through the log, not the ear.

Order is load-bearing: Producer first (the cut), Critic second (the word on
the finished cut, then the name — the naming call sees ONLY finished work, so
a title can never become a brief), then the Muse and the Listener AFTER the
release exists — the Muse reads what actually shipped (plus the Listener's
logged reactions from earlier boundaries) into the next brief, and the
Listener reacts to the finished, titled release like any fan would. The
Listener's reaction row is what the NEXT boundary's Muse reads: the reception
loop closes here, at the frame, never inside a set.
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

#: Display-only stage names (DECISIONS.md): staff prose uses these; ids never change.
STAGE_NAMES: dict[str, str] = {"silt": "Delta Marlowe", "rust": "Roan Patina", "keep": "Evers Lane"}

#: Staff surnames — the register the Critic writes in (DECISIONS.md naming rule).
SURNAMES: dict[str, str] = {"silt": "Marlowe", "rust": "Patina", "keep": "Lane"}


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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def newest_release_path(run_dir: Path) -> Path:
    """The run's most recent release-*.json by mtime — the record to build on."""
    candidates = sorted(
        run_dir.glob("release-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        raise FileNotFoundError(f"no release-*.json under {run_dir}")
    return candidates[0]


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
    """What one staff pass produced, and where its facts landed."""

    released: bool
    selection: Any  # afar.agents.producer.Selection
    review: Optional[Any]  # afar.agents.critic.Review
    names: Optional[Any]  # afar.agents.critic.Names
    brief: Optional[Any]  # afar.agents.muse.Brief
    reaction: Optional[Any]  # afar.agents.listener.Reaction
    release_record: Optional[dict[str, Any]]
    release_path: Optional[Path]
    superseded_release_id: str


@dataclass(frozen=True)
class BoundaryRecord:
    """What the Muse + Listener half of the frame produced."""

    brief: Any  # afar.agents.muse.Brief
    reaction: Any  # afar.agents.listener.Reaction
    release_record: dict[str, Any]
    release_path: Path
    superseded_release_id: str


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


def load_recent_reactions(
    runs_root: Path, *, exclude_run: str | None = None, limit: int = 6
) -> list[dict[str, Any]]:
    """The Listener's most recent logged reactions across ALL runs — what the
    Muse reads at a boundary. Reading the log, not remembering, is the point:
    the loop closes through logged rows (rule 3), and a fresh process on a
    fresh machine hears the same fan."""
    runs_root = Path(runs_root)
    rows: list[dict[str, Any]] = []
    if runs_root.exists():
        for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
            if run_dir.name == exclude_run:
                continue
            path = run_dir / "reactions.jsonl"
            if path.exists():
                rows.extend(r for r in _read_jsonl(path) if r.get("kind") == "reaction")
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows[-limit:]


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
    if "producer" not in record.get("staff", {}):
        raise ValueError(
            f"run {run_dir.name}: newest release record carries no Producer cut — "
            "the Muse and the Listener act only after a release exists"
        )
    (run_row,) = _read_jsonl(run_dir / "runs.jsonl")
    ledger = JsonlLedger(run_dir.parent, run_dir.name, context=RunContext(code_sha=config.code_sha))
    set_stamps = {"condition": run_row["condition"], "seed": run_row["seed"]}

    # --- the Muse: the brief, carried forward ---------------------------------
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
    listener = ListenerAgent(config.model)
    reaction = listener.react(record, stage_names=STAGE_NAMES)
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
    staff_block["listener"] = {
        "valence": reaction.valence,
        "text": reaction.text,
        "disagreements_with_critic": list(reaction.disagreements_with_critic),
    }
    record_body["staff"] = staff_block
    prior_staff = list(record.get("provenance", {}).get("staff", []))
    record_body["provenance"] = {
        "staff": [*prior_staff, "muse", "listener"],
        "supersedes_release_id": record["release_id"],
    }
    release_record, release_path = _append_release_record(run_dir, ledger, set_stamps, record_body)
    return BoundaryRecord(
        brief=brief,
        reaction=reaction,
        release_record=release_record,
        release_path=release_path,
        superseded_release_id=record["release_id"],
    )


def run_staff(
    run_dir: Path, config: AfarConfig, *, stance: str | None = None, taboo: Any = None
) -> StaffRecord:
    """Run the full staff retrospectively on one completed set — Producer,
    Critic, Muse, Listener, in that order. See module docstring.

    Appends `selections` / `reviews` / `briefs` / `reactions` rows to the
    run's log and, when the Producer releases, writes NEW content-addressed
    release records whose `provenance.supersedes_release_id` chains name the
    records they build on — exactly the reembed correction pattern. On a 'no
    release' verdict the verdict is logged and NO new record is written: not
    releasing is a decision, not a correction — and with nothing shipped, the
    Muse and the Listener have nothing to hear (no brief, no reaction).
    """
    from afar.agents.critic import CriticAgent
    from afar.agents.producer import ProducerAgent

    run_dir = Path(run_dir)
    view = load_set_view(run_dir)
    old_record = dict(view.record)
    ledger = JsonlLedger(run_dir.parent, run_dir.name, context=RunContext(code_sha=config.code_sha))
    set_stamps = {"condition": view.condition, "seed": view.seed}

    # --- the Producer's cut ---------------------------------------------------
    producer = ProducerAgent(config.model)
    selection = producer.select(view)
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
        )

    # --- the Critic's word, then the name (last) ------------------------------
    critic = CriticAgent(config.model)
    review = critic.review(view, selection)
    names = critic.name(selection, review)
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
            "take_titles": dict(names.take_titles),
        },
    )

    # --- the staff-enriched, content-addressed release record -----------------
    record_body = {key: value for key, value in old_record.items() if key != "release_id"}
    record_body["staff"] = {
        "producer": {
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
        },
        "critic": {
            "release_title": names.release_title,
            "take_titles": dict(names.take_titles),
            "release_review": review.release,
            "act_reviews": dict(review.per_act),
        },
    }
    record_body["provenance"] = {
        "staff": ["producer", "critic"],
        "supersedes_release_id": old_record["release_id"],
    }
    _append_release_record(run_dir, ledger, set_stamps, record_body)

    # --- the Muse and the Listener, after the release exists ------------------
    # `taboo` (the conductor's era-scoped FieldTabooMemory) rides through so a
    # hostile era's observed field moves accumulate across its boundaries.
    boundary = run_muse_listener(run_dir, config, stance=stance, taboo=taboo)
    return StaffRecord(
        released=True,
        selection=selection,
        review=review,
        names=names,
        brief=boundary.brief,
        reaction=boundary.reaction,
        release_record=boundary.release_record,
        release_path=boundary.release_path,
        superseded_release_id=old_record["release_id"],
    )
