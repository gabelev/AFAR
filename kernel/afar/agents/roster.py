"""The town roster: compiled resident/in-town act personas, loaded from
committed files.

Every file under `kernel/afar/agents/roster/` is one act compiled by
`kernel/scripts/compile_roster.py` (see `persona_compiler`) and then
HUMAN-REVIEWED before commit — the files are the artifacts, not the compiler
run. Loading a roster registers its player ids with `afar.intent`, so
roster intents validate; the conductor never imports this module, so an
unattended house session's id guard stays exactly the trio.
"""

from __future__ import annotations

import json
from pathlib import Path

from ensemble.agent import Persona

from afar.intent import register_player_ids

ROSTER_DIR = Path(__file__).resolve().parent / "roster"


def load_roster_entries(roster_dir: Path = ROSTER_DIR) -> list[dict]:
    """The raw committed roster entries, sorted by player_id."""
    entries = []
    for path in sorted(roster_dir.glob("*.json")):
        with open(path, encoding="utf-8") as fh:
            entries.append(json.load(fh))
    return sorted(entries, key=lambda e: e["player_id"])


def persona_from_entry(entry: dict) -> Persona:
    """One committed roster entry -> a Persona (base_prompt is stored as a
    list of lines so the committed files diff cleanly)."""
    return Persona(
        name=entry["name"],
        base_prompt="\n".join(entry["base_prompt"]),
        personality=entry["personality"],
        metadata={
            "player_id": entry["player_id"],
            "display_name": entry["display_name"],
            "first_name": entry["first_name"],
            "addresses": dict(entry["addresses"]),
            "origin": entry.get("origin"),
            "building": entry.get("building"),
            "compiled": True,
        },
    )


def load_roster(roster_dir: Path = ROSTER_DIR) -> dict[str, Persona]:
    """player_id -> Persona for every committed roster act. Registers the ids
    with afar.intent so roster intents validate."""
    personas = {e["player_id"]: persona_from_entry(e) for e in load_roster_entries(roster_dir)}
    if personas:
        register_player_ids(*personas)
    return personas
