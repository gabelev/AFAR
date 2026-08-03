"""EXPERIMENT-ONLY: walk the ROUND-BASED staff over one completed set.

The live piece does not come here — an artist publishes an album and
`afar.staff.run_reactions` runs the five reactions over it. This script
drives the round-based instrument (afar.staff_rounds, behind
AFAR_EXPERIMENT_MODE): the panel, the cut, the naming call, the brief.

Manual staff entry: run the staff on one COMPLETED run. NOT a test.

    cd kernel && uv run python scripts/run_staff.py --run <run_id>

The set-boundary pass (architecture rule 1: staff act on the frame between
sets, never inside one), full order Producer -> Critic -> Muse -> Listener.
Reads the run's append-only JSONL, has the Producer make the cut, the Critic
review and name it (last word on the finished work), then — after the release
exists — the Muse composes the carry-forward brief (discourse scan + what
shipped + the Listener's prior reactions) and the Listener reacts to the
release like a fan. Appends `selections` / `reviews` / `briefs` / `reactions`
rows and writes new content-addressed release records whose provenance chains
supersede the previous ones — the reembed pattern.

`--muse-listener-only` runs just the outward half on a run whose newest
record already carries the Producer/Critic block (the retrospective
enrichment path). `--stance` is the era's stance toward the outside world
(porous | hostile | oblivious); until the conductor exists it defaults to the
first era's stance from the authored cycle.

Reads .env if present (never committed). With no ANTHROPIC_API_KEY this still
runs on MockProvider — the honest way to check the wiring offline. Model
calls only (the Muse's web searches ride the model API): no renderer, no
embedder, no audio is touched.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from afar.config import build_config
from afar.schedule import ScheduleConfig
from afar.staff_rounds import run_muse_listener, run_staff


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


def _print_boundary(brief, reaction) -> None:
    print("\nTHE MUSE'S BRIEF (carried forward)")
    print(f"  stance     {brief.stance}")
    print(f"  theme      {brief.theme}" + ("  (thin: scan came back empty)" if brief.thin else ""))
    print(f"  brief      {brief.body}")
    for note in brief.palette_notes:
        print(f"  palette    {note}")
    for move in brief.forbidden_moves:
        print(f"  forbidden  {move}")
    for url in brief.sources:
        print(f"  source     {url}")

    print("\nTHE LISTENER'S REACTION")
    print(f"  valence    {reaction.valence}")
    print(f"  reaction   {reaction.text}")
    for d in reaction.disagreements_with_critic:
        print(f"  vs critic  {d}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the staff on a completed run.")
    parser.add_argument("--run", required=True, help="run_id under the runs root")
    parser.add_argument(
        "--stance",
        default=None,
        choices=ScheduleConfig().eras_stance_cycle,
        help="the era's stance toward the outside world (default: the cycle's first)",
    )
    parser.add_argument(
        "--muse-listener-only",
        action="store_true",
        help="skip Producer/Critic (their rows must already exist) and run just the Muse + Listener enrichment",
    )
    args = parser.parse_args()

    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    config = build_config()
    run_dir = config.runs_root / args.run
    if not run_dir.exists():
        raise SystemExit(f"no such run: {run_dir}")

    print(f"run    {args.run}")
    print(f"model  {'live' if config.live else 'mock (no ANTHROPIC_API_KEY)'}")

    if args.muse_listener_only:
        boundary = run_muse_listener(run_dir, config, stance=args.stance)
        _print_boundary(boundary.brief, boundary.reaction)
        print(f"\nsupersedes  {boundary.superseded_release_id[:12]}…")
        print(f"release     {boundary.release_path}")
        print(f"release_id  {boundary.release_record['release_id']}")
        return

    result = run_staff(run_dir, config, stance=args.stance)

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

    _print_boundary(result.brief, result.reaction)

    print(f"\nsupersedes  {result.superseded_release_id[:12]}…")
    print(f"release     {result.release_path}")
    print(f"release_id  {result.release_record['release_id']}")


if __name__ == "__main__":
    main()
