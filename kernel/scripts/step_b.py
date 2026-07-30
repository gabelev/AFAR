"""Manual Step B entry: one full set — three players, N rounds. NOT a test.

    cd kernel && uv run python scripts/step_b.py --rounds 6 --condition contact

Reads .env if present (never committed). With no keys set this still runs —
MockProvider + MockRenderer + MockEmbedder — which is the honest way to check
the wiring before spending money on the live APIs. `--renderer elevenlabs`
forces the live renderer (needs ELEVENLABS_API_KEY); `--embedder mert` needs
the listen extra (uv sync --extra listen).
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.config import build_config
from afar.intent import PLAYER_IDS
from afar.log import JsonlLedger, RunContext
from afar.perception.context import CONDITIONS
from afar.perception.embedder import AudioEmbedder, MockEmbedder
from afar.run import run_set


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


def _print_influence(record: dict, space: str) -> None:
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
    parser = argparse.ArgumentParser(description="Run one full AFAR set (three players, N rounds).")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--condition", choices=sorted(CONDITIONS), default="contact")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--renderer", choices=["mock", "elevenlabs"], default=None,
                        help="override AFAR_RENDERER for this run")
    parser.add_argument("--embedder", choices=["mock", "mert"], default="mock")
    args = parser.parse_args()

    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if args.renderer is not None:
        os.environ["AFAR_RENDERER"] = args.renderer
    config = build_config()

    embedder: AudioEmbedder
    if args.embedder == "mert":
        from afar.perception.embedder import MERTEmbedder

        embedder = MERTEmbedder()
    else:
        embedder = MockEmbedder()

    run_id = time.strftime("%Y%m%d-%H%M%S") + f"-step-b-{args.condition}"
    ledger = JsonlLedger(config.runs_root, run_id, context=RunContext(code_sha=config.code_sha))
    players = [Player(PERSONAS[pid], config.model, config.renderer) for pid in PLAYER_IDS]

    print(f"run_id     {run_id}")
    print(f"model      {'live' if config.live else 'mock'}   renderer {config.renderer.name}   "
          f"embedder {embedder.name}")
    print(f"condition  {args.condition}   rounds {args.rounds}   seed {args.seed}")

    result = run_set(
        players,
        rounds=args.rounds,
        condition=args.condition,
        config=config,
        ledger=ledger,
        embedder=embedder,
        seed=args.seed,
    )

    print(f"release    {result.paths['release']}")
    print(f"release_id {result.release_record['release_id']}")
    print(f"log        {result.paths['run_dir']}")
    print("influence  I(a<-b): + means b pulled a, - means a stayed home")
    for space in ("audio", "intent"):
        _print_influence(result.release_record, space)


if __name__ == "__main__":
    main()
