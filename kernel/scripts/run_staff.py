"""Manual staff entry: run the Producer + Critic on one COMPLETED run. NOT a test.

    cd kernel && uv run python scripts/run_staff.py --run <run_id>

The set-boundary pass (architecture rule 1: staff act on the frame between
sets, never inside one). Reads the run's append-only JSONL, has the Producer
make the cut (which single take per act makes the release, judged by a panel
reading the LOG — intents, lines, lyrics, rationales, features; not audio),
then the Critic review the finished cut and name it, last. Appends
`selections` and `reviews` rows and writes a new content-addressed release
record whose provenance supersedes the previous one — the reembed pattern.

Reads .env if present (never committed). With no ANTHROPIC_API_KEY this still
runs on MockProvider — the honest way to check the wiring offline. Model
calls only: no renderer, no embedder, no audio is touched.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from afar.config import build_config
from afar.staff import run_staff


def _load_dotenv(path: Path) -> None:
    """Tiny KEY=VALUE loader; real env always wins over the file."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Producer + Critic on a completed run.")
    parser.add_argument("--run", required=True, help="run_id under the runs root")
    args = parser.parse_args()

    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    config = build_config()
    run_dir = config.runs_root / args.run
    if not run_dir.exists():
        raise SystemExit(f"no such run: {run_dir}")

    print(f"run    {args.run}")
    print(f"model  {'live' if config.live else 'mock (no ANTHROPIC_API_KEY)'}")
    result = run_staff(run_dir, config)

    if not result.released:
        print("\nTHE PRODUCER: no release this set")
        print(f"  {result.selection.note}")
        print(f"  failed acts: {', '.join(result.selection.failed_players)}")
        return

    print("\nTHE PRODUCER'S CUT")
    for pid, choice in result.selection.takes.items():
        scores = ", ".join(f"{k}={v:.2f}" for k, v in choice.scores.items())
        print(f"  {pid}: round {choice.round}  ({scores})")
        print(f"      why: {choice.reasoning}")
        for d in choice.dissents:
            print(f"      dissent [{d['judge']}] preferred round {d['preferred_round']}: {d['rationale']}")
    print(f"  note: {result.selection.note}")

    print("\nTHE CRITIC'S WORD")
    for pid, verdict in result.review.per_act.items():
        print(f"  {pid}: {verdict}")
    print(f"  release: {result.review.release}")

    print("\nTHE NAME, LAST")
    print(f"  release title: {result.names.release_title}")
    for pid, title in result.names.take_titles.items():
        print(f"  {pid}: {title}")

    print(f"\nsupersedes  {result.superseded_release_id[:12]}…")
    print(f"release     {result.release_path}")
    print(f"release_id  {result.release_record['release_id']}")


if __name__ == "__main__":
    main()
