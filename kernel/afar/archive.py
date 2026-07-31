"""The vault: every session's full tape, read whole from the append-only log.

Gabe's directive ("why do we generate so much audio? … no reason to sit on
it") became the vault doctrine (DECISIONS.md): EVERYTHING the acts record is
released into the archive. The cut release — when one exists — stays the
headline; the session's FULL tape (all takes, round order, the discards, the
dissents, even a vetoed or abandoned session) becomes a companion release of
kind "tape", catalogue series TAPE-NNNN.

This module is the tape's read side: `load_tape_view` rebuilds one session —
ANY session — from its run dir, tolerantly. A conductor set has runs.jsonl,
selections, a release record; a step-a solo run has only intents + artifacts;
an aborted set has fewer takes than rounds × players. All of them are tapes.
The only hard requirement is the material itself: intents.jsonl and
artifacts.jsonl. Nothing here writes anything — the Archivist (the staff
agent that shelves tapes) and the publish path both read through this.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def newest_release_record(run_dir: Path) -> Optional[dict[str, Any]]:
    """The run's newest release-*.json by mtime, or None (solo/aborted runs
    never wrote one). Same newest-by-mtime rule as afar.staff/afar.publish."""
    candidates = sorted(
        Path(run_dir).glob("release-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        return None
    return json.loads(candidates[0].read_text(encoding="utf-8"))


@dataclass(frozen=True)
class TapeTake:
    """One take on the tape — the logged fact, whole."""

    player: str
    round: int
    take_id: str  # artifact content hash (the mp3's name in the log)
    path: str
    line: str
    lyrics: str
    rationale: str
    intent: Mapping[str, Any] = field(default_factory=dict)


#: What a session's tape status is, derived from the log alone.
#:   released  — the Producer cut a release from it
#:   rejected  — the panel convened and passed nothing (the veto stands)
#:   abandoned — the session stopped mid-set (renderer failure, SIGTERM…)
#:   solo      — a single act recording alone, before the sessions began
#:   unreleased — a completed session with no verdict logged either way
TAPE_STATUSES: tuple[str, ...] = ("released", "rejected", "abandoned", "solo", "unreleased")


@dataclass(frozen=True)
class TapeView:
    """One session as the vault sees it: every take, in round order, plus
    whatever verdicts the log carries about what happened to them."""

    run_id: str
    kind: str  # "session" (a set) | "solo" (a step-a single-act run)
    condition: str  # the logged condition; "solo" when the run predates sets
    players: tuple[str, ...]
    rounds: int
    takes: tuple[TapeTake, ...]  # round order, player order within a round
    complete: bool  # False when the session stopped mid-set
    duration_s: int
    selected: Mapping[str, int] = field(default_factory=dict)  # player -> round on the cut
    dissents: Mapping[str, list] = field(default_factory=dict)  # player -> judge dissents
    veto_note: Optional[str] = None  # the Producer's 'no release' prose, when logged
    released: bool = False
    record: Optional[Mapping[str, Any]] = None  # newest release record, if any

    @property
    def status(self) -> str:
        if self.released:
            return "released"
        if self.veto_note is not None:
            return "rejected"
        if not self.complete:
            return "abandoned"
        if self.kind == "solo":
            return "solo"
        return "unreleased"

    @property
    def date(self) -> str:
        """YYYY-MM-DD from the run id (every run id starts YYYYMMDD-HHMMSS)."""
        r = self.run_id
        return f"{r[0:4]}-{r[4:6]}-{r[6:8]}"


def load_tape_view(run_dir: Path) -> TapeView:
    """Rebuild one session's tape from its run dir, tolerantly (see module
    docstring). Raises FileNotFoundError only when the material itself —
    intents + artifacts — is missing: a run with no takes has no tape."""
    run_dir = Path(run_dir)
    intents = _read_jsonl(run_dir / "intents.jsonl")
    artifacts = _read_jsonl(run_dir / "artifacts.jsonl")
    if not intents or not artifacts:
        raise FileNotFoundError(f"no takes under {run_dir} (intents/artifacts missing or empty)")
    # Two join keys, tolerantly: session runs carry `round` on both tables;
    # the step-a solo scripts logged NO round — there the artifact's
    # `intent_id` names its intent row, and file order IS take order.
    art_by_intent = {row["intent_id"]: row for row in artifacts if row.get("intent_id")}
    art_by_round = {
        (row["round"], row["player"]): row for row in artifacts if "round" in row
    }

    takes: list[TapeTake] = []
    counters: dict[str, int] = {}
    for row in intents:
        player = row["player"]
        # (round, player) is authoritative when the row carries a round —
        # intent ids are content hashes and a mock/repeated intent can share
        # one; only the round-less solo rows join by intent_id.
        if "round" in row:
            art = art_by_round.get((row["round"], player))
        else:
            art = art_by_intent.get(row.get("id"))
        if art is None:
            continue  # an intent whose render never landed — the take does not exist
        round_ = row.get("round", art.get("round"))
        if round_ is None:
            round_ = counters.get(player, 0)
        counters[player] = int(round_) + 1
        takes.append(
            TapeTake(
                player=player,
                round=int(round_),
                take_id=art["hash"],
                path=art["path"],
                line=str(row.get("line", "")),
                lyrics=str(row.get("lyrics", "")),
                rationale=str(row.get("rationale", "")),
                intent=row.get("intent", {}),
            )
        )
    takes.sort(key=lambda t: (t.round, t.player))

    run_rows = _read_jsonl(run_dir / "runs.jsonl")
    if run_rows:
        run_row = run_rows[0]
        kind = "session"
        condition = str(run_row.get("condition", "contact"))
        players = tuple(run_row.get("players", ()))
        rounds = int(run_row.get("rounds", 0))
    else:
        # A pre-sessions solo run (step-a): one act, takes in round order.
        kind = "solo"
        condition = "solo"
        players = tuple(dict.fromkeys(t.player for t in takes))
        rounds = max(t.round for t in takes) + 1

    complete = len(takes) == rounds * len(players) and rounds > 0

    record = newest_release_record(run_dir)
    staff = (record or {}).get("staff") or {}
    selected_block = staff.get("producer", {}).get("selected", {})
    selected = {pid: int(choice["round"]) for pid, choice in selected_block.items()}
    dissents = {
        pid: list(choice.get("dissents", ()))
        for pid, choice in selected_block.items()
        if choice.get("dissents")
    }

    # The Producer's verdicts, from the selections rows (newest wins).
    veto_note: Optional[str] = None
    released = bool(selected)
    for row in _read_jsonl(run_dir / "selections.jsonl"):
        if row.get("kind") != "selection":
            continue
        if row.get("released"):
            released = True
            veto_note = None
        else:
            released = False
            veto_note = str(row.get("note", "")) or "No release from this set."
    if not released and record is not None and not staff and veto_note is None:
        # A record with no staff block and no verdict: the pre-staff era's
        # mechanical publish — the set released (0002's v1 behavior).
        released = True

    duration_s = int((record or {}).get("set", {}).get("duration_s", 30))

    return TapeView(
        run_id=run_dir.name,
        kind=kind,
        condition=condition,
        players=players,
        rounds=rounds,
        takes=tuple(takes),
        complete=complete,
        duration_s=duration_s,
        selected=selected,
        dissents=dissents,
        veto_note=veto_note,
        released=released,
        record=record,
    )


def newest_shelving(run_dir: Path) -> Optional[dict[str, Any]]:
    """The Archivist's newest logged shelving row for this run, or None —
    what the tape's publish reads (the log is authoritative; Neon mirrors)."""
    rows = [r for r in _read_jsonl(Path(run_dir) / "archives.jsonl") if r.get("kind") == "shelving"]
    return rows[-1] if rows else None
