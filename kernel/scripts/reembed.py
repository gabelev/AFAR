"""Re-embed one logged run's audio and append corrected audio-space rows. NOT a test.

    cd kernel && uv run python scripts/reembed.py --run <run_id> --embedder mert

The append-only correction path (architecture rule 3: rows are facts, never
edited). When a run's audio-space embeddings were produced by the wrong model
— the release 0002 case: a LIVE ElevenLabs set embedded with MockEmbedder, so
every audio-space feature was placeholder junk — the fix is never to rewrite
the log. Embeddings and features are derived, so this script:

  1. reads the run's artifacts.jsonl (content hash -> mp3 path) and re-embeds
     every clip with the requested embedder (audio read transiently, rule 6);
  2. APPENDS new embeddings rows (space="audio", the new model_id, a `note`
     naming the superseded model) — the mock rows stay in the log as history;
  3. recomputes the audio-space features (influence / convergence / novelty /
     asymmetry) through the same `compute_space_features` path `run_set` uses,
     and APPENDS them as new features rows stamped with the new model_id;
  4. writes a NEW content-addressed release-<hash>.json next to the old one
     (the old file is kept), with corrected audio-space blocks, the new
     embedder in `set.embedder`, and a `provenance` note
     {"audio_reembedded_from": ..., "embedder": ...} so the record says out
     loud that its audio space was recomputed after the fact.

Intent-space rows and features are untouched — they were real the first time.
At analysis time the model_id column is what separates the generations; the
newest release record is the corrected one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from afar.config import _code_sha, _kernel_root
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import AudioEmbedder, MockEmbedder
from afar.run import compute_space_features


@dataclass(frozen=True)
class ReembedResult:
    """The corrected record, where it landed, and the recomputed vectors."""

    release_record: dict[str, Any]
    release_path: Path
    superseded_release_id: str
    embeddings_by_player: dict[str, list[list[float]]]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def newest_release_path(run_dir: Path) -> Path:
    """The run's most recent release-*.json by mtime — the record to correct."""
    candidates = sorted(
        run_dir.glob("release-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        raise FileNotFoundError(f"no release-*.json under {run_dir}")
    return candidates[0]


def reembed_run(runs_root: Path, run_id: str, embedder: AudioEmbedder) -> ReembedResult:
    """Append corrected audio-space rows + a new release record for one run.

    See module docstring for the four steps. Raises if the run has no
    artifacts, no release record, or an artifact whose file is missing —
    a partial correction would be worse than none.
    """
    run_dir = Path(runs_root) / run_id
    artifacts = _read_jsonl(run_dir / "artifacts.jsonl")
    if not artifacts:
        raise ValueError(f"{run_dir}/artifacts.jsonl is empty — nothing to re-embed")
    (run_row,) = _read_jsonl(run_dir / "runs.jsonl")
    old_path = newest_release_path(run_dir)
    old_record = json.loads(old_path.read_text(encoding="utf-8"))
    old_model = old_record["set"]["embedder"]["name"]
    if old_model == embedder.name:
        raise ValueError(
            f"run {run_id} is already embedded with {embedder.name!r} — nothing to supersede"
        )

    ids: list[str] = run_row["players"]
    rounds: int = run_row["rounds"]
    note = f"re-embed: supersedes {old_model!r} audio-space rows for this run"
    ledger = JsonlLedger(Path(runs_root), run_id, context=RunContext(code_sha=_code_sha()))

    # --- step 1 + 2: re-embed every artifact, append new embeddings rows -----
    by_round_player = {(row["round"], row["player"]): row for row in artifacts}
    embs: dict[str, list[list[float]]] = {pid: [] for pid in ids}
    for t in range(rounds):
        for pid in ids:
            row = by_round_player[(t, pid)]
            clip = Path(row["path"])
            if not clip.exists():
                raise FileNotFoundError(f"artifact file missing for ({pid}, round {t}): {clip}")
            vector = embedder.embed(clip)
            ledger.write(
                "embeddings",
                {
                    # Same provenance stamps as the artifact row being re-read.
                    "condition": row["condition"],
                    "seed": row["seed"],
                    "renderer_version": row["renderer_version"],
                    "prompt_sha": row["prompt_sha"],
                    "round": t,
                    "player": pid,
                    "space": "audio",
                    "model_id": embedder.name,
                    "dim": embedder.dim,
                    "artifact_id": row["hash"],
                    "vector": vector,
                    "note": note,
                },
            )
            embs[pid].append(vector)

    # --- step 3: recompute audio-space features through the shared path ------
    set_stamps = {"condition": run_row["condition"], "seed": run_row["seed"]}
    block = compute_space_features(
        embs,
        rounds=rounds,
        ledger=ledger,
        space="audio",
        stamps=set_stamps,
        row_extra={"model_id": embedder.name, "note": note},
    )

    # --- step 4: the corrected, content-addressed release record -------------
    record_body = {key: value for key, value in old_record.items() if key != "release_id"}
    for feature_name, value in block.items():
        record_body[feature_name] = {**record_body[feature_name], "audio": value}
    record_body["set"] = {
        **record_body["set"],
        "embedder": {"name": embedder.name, "dim": embedder.dim},
    }
    record_body["provenance"] = {
        "audio_reembedded_from": old_model,
        "embedder": embedder.name,
        "supersedes_release_id": old_record["release_id"],
    }
    canonical = json.dumps(record_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    release_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    release_record = {"release_id": release_id, **record_body}
    ledger.write("releases", {**set_stamps, "id": release_id, "record": release_record})
    release_path = run_dir / f"release-{release_id[:12]}.json"
    release_path.write_text(
        json.dumps(release_record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return ReembedResult(
        release_record=release_record,
        release_path=release_path,
        superseded_release_id=old_record["release_id"],
        embeddings_by_player=embs,
    )


def _print_influence(record: dict[str, Any], space: str) -> None:
    edges_by_round = record["influence"][space]
    if not edges_by_round:
        print(f"  ({space}: single round — influence needs a previous round)")
        return
    columns = sorted(next(iter(edges_by_round.values())))
    print(f"  [{space} space]")
    print("  round  " + "  ".join(f"{c:>10}" for c in columns))
    for t in sorted(edges_by_round, key=int):
        cells = "  ".join(f"{edges_by_round[t][c]:>+10.4f}" for c in columns)
        print(f"  {t:>5}  {cells}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append corrected audio-space embeddings/features for a logged run."
    )
    parser.add_argument("--run", required=True, help="run_id under the runs root")
    parser.add_argument("--embedder", choices=["mert", "mock"], default="mert",
                        help="mock exists only to exercise the plumbing offline")
    args = parser.parse_args()

    runs_root = Path(
        os.environ.get("AFAR_RUNS_ROOT", str(_kernel_root() / ".." / "runs"))
    ).resolve()

    embedder: AudioEmbedder
    if args.embedder == "mert":
        from afar.perception.embedder import MERTEmbedder

        embedder = MERTEmbedder()
    else:
        embedder = MockEmbedder()

    result = reembed_run(runs_root, args.run, embedder)
    record = result.release_record
    print(f"run         {args.run}")
    print(f"embedder    {embedder.name} (dim {embedder.dim})")
    print(f"superseded  {result.superseded_release_id[:12]}…")
    print(f"release     {result.release_path}")
    print(f"release_id  {record['release_id']}")
    print("influence   I(a<-b): + means b pulled a, - means a stayed home")
    for space in ("audio", "intent"):
        _print_influence(record, space)
    print("convergence [audio]  " + "  ".join(f"{v:+.4f}" for v in record["convergence"]["audio"]))
    print("convergence [intent] " + "  ".join(f"{v:+.4f}" for v in record["convergence"]["intent"]))


if __name__ == "__main__":
    main()
