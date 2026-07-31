"""The append-only JSONL log: the installation's source of truth.

Architecture rule 3: JSONL under `runs/` is authoritative; any database is a
derived mirror. Rows are facts — written once, never edited — because the
whole point of AFAR's log is that the history of what the band did can be
replayed and audited years later. Deleting or rewriting a row would be
rewriting what happened.

One file per table under `root/run_id/`, one JSON object per line. Every row
is stamped with `ts` and `run_id` automatically, plus whatever experimental
provenance the run's `RunContext` carries (condition, code_sha, seed,
renderer_version, prompt_sha) — the caller can always override per row, since
prompt_sha and renderer_version are usually only known after a render.

Artifacts rows are content-addressed: `id` IS the sha256 of the file's bytes,
and the row stores the path and hash, never the bytes — audio lives on disk,
facts live in the log.

Deliberately dependency-free: open/append/close per write. At AFAR's cadence
(one track at a time) durability beats throughput.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

TABLES: tuple[str, ...] = (
    "runs",
    "eras",
    "sets",
    "rounds",
    "perceptions",
    "intents",
    "artifacts",
    "embeddings",
    "features",
    "selections",
    "reviews",
    "briefs",
    "reactions",
    "releases",
)


@dataclass(frozen=True)
class RunContext:
    """Provenance that should ride on every row of a run.

    All optional: a field left None is simply omitted, so mock runs and live
    runs write the same tables with honest columns.
    """

    condition: Optional[str] = None
    code_sha: Optional[str] = None
    seed: Optional[int] = None
    renderer_version: Optional[str] = None
    prompt_sha: Optional[str] = None

    def stamps(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in (
                ("condition", self.condition),
                ("code_sha", self.code_sha),
                ("seed", self.seed),
                ("renderer_version", self.renderer_version),
                ("prompt_sha", self.prompt_sha),
            )
            if value is not None
        }


class JsonlLedger:
    """Append-only writer for one run's tables."""

    def __init__(self, root: Path, run_id: str, *, context: Optional[RunContext] = None) -> None:
        self.root = Path(root)
        self.run_id = run_id
        self.context = context or RunContext()
        self.run_dir = self.root / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def write(self, table: str, row: Mapping[str, Any]) -> dict[str, Any]:
        """Append one row to `table` and return it as stamped.

        Stamping order: ts/run_id first, then RunContext provenance, then the
        row itself — so a row that knows better (e.g. the real prompt_sha
        after a render) wins over the run-level default.
        """
        if table not in TABLES:
            raise ValueError(f"unknown table {table!r}; expected one of {TABLES}")
        stamped: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
        }
        stamped.update(self.context.stamps())
        stamped.update(row)
        line = json.dumps(stamped, ensure_ascii=False, separators=(",", ":"))
        with open(self.run_dir / f"{table}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return stamped
