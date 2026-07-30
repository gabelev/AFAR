"""Manual Step A entry: one real round for one player. NOT a test.

    cd kernel && uv run python scripts/step_a.py --player silt

Reads .env if present (never committed). With no keys set this still runs —
MockProvider + MockRenderer — which is the honest way to check the wiring
before spending money on the live APIs.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from afar.agents.personas import PERSONAS
from afar.agents.player import Player, render_one
from afar.config import build_config
from afar.log import JsonlLedger, RunContext


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
    parser = argparse.ArgumentParser(description="Run one AFAR round for one player.")
    parser.add_argument("--player", choices=sorted(PERSONAS), default="silt")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--condition", default="manual")
    args = parser.parse_args()

    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    config = build_config()

    run_id = time.strftime("%Y%m%d-%H%M%S") + f"-step-a-{args.player}"
    ledger = JsonlLedger(config.runs_root, run_id, context=RunContext(code_sha=config.code_sha))
    player = Player(PERSONAS[args.player], config.model, config.renderer)

    print(f"run_id     {run_id}")
    print(f"model      {'live' if config.live else 'mock'}   renderer {config.renderer.name}")

    artifact = render_one(player, {}, ledger, seed=args.seed, condition=args.condition)

    print(f"track      {artifact.body}")
    print(f"artifact   {artifact.metadata['content_hash']}")
    print(f"prompt_sha {artifact.metadata['prompt_sha']}")
    print(f"line       {artifact.metadata['line']}")
    print(f"log        {ledger.run_dir}")


if __name__ == "__main__":
    main()
