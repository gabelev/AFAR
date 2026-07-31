"""Compile the town roster: tunz fixtures + Vess Camber -> committed persona files.

Usage (from kernel/):
    uv run python scripts/compile_roster.py               # write roster files
    uv run python scripts/compile_roster.py --distances   # intent-space report

Reads each artist's dna.json + profile.json from the tunz fixtures dir
(default ../ai-music/tunz/fixtures next to this repo; override with
AFAR_TUNZ_FIXTURES) plus the authored Vess source under
afar/agents/roster_src/vess, and writes one reviewed-artifact JSON per act to
afar/agents/roster/. Deterministic: rerunning writes identical bytes — BUT
the committed files are the reviewed artifacts and may carry human review
edits on top of compiler output (stances, example lines). Diff before
committing a recompile; never blind-overwrite a reviewed file.

--distances prints cosine distances in intent space (features.intent_vector)
between every compiled act's few-shot intent and (a) the house trio's
few-shot intents, (b) every other compiled act — the review table that shows
who actually contrasts with whom. Report, not gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

KERNEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KERNEL))

from afar.agents.persona_compiler import compile_roster_entry, extract_example_intent  # noqa: E402
from afar.agents.personas import PERSONAS  # noqa: E402
from afar.agents.roster import ROSTER_DIR, load_roster  # noqa: E402
from afar.features import _cosine, intent_vector  # noqa: E402
from afar.intent import Intent  # noqa: E402

TUNZ_DEFAULT = KERNEL.parent.parent / "ai-music" / "tunz" / "fixtures"
VESS_SRC = KERNEL / "afar" / "agents" / "roster_src" / "vess"

# What the room calls each act (the profile names are stage names; these are
# the spoken first names, chosen by hand — bands keep their band name).
FIRST_NAMES: dict[str, str] = {
    "assembly-ghost": "Assembly Ghost",
    "b-9-the-lucky-draw": "B-9",
    "deuce-the-dust-servos": "Deuce",
    "fren-l-ge": "Fren",
    "hohlraum": "HOHLRAUM",
    "hollis-wren-the-blacklung-choir": "Hollis",
    "josie-ryland": "Josie",
    "lolgorithm": "lolgorithm",
    "los-novios-del-m-s-all": "Los Novios",
    "marlow-vane": "Marlow",
    "marlowe-quiet": "Marlowe",
    "midnight-vendo": "Vendo",
    "nite-route": "Nite Route",
    "ore-ashes": "Ore & Ashes",
    "systurj-kull": "Systurjökull",
    "the-harbor-belles": "the Belles",
    "the-pier-lights": "the Pier Lights",
    "the-sardis-fasola-society": "Sardis",
    "twin-signal": "Twin Signal",
    "valentina-sol": "Valentina",
    "velvet-nadia": "Nadia",
    "vess": "Vess",
}

# Street residences (design canon: RES 03 is Vess's — console/amp/crates).
# The other three move-ins are chosen for maximal intent-space contrast with
# the house trio AND each other — see --distances and the PR body.
BUILDINGS: dict[str, str] = {
    "vess": "res-03",
    "lolgorithm": "res-01",
    "deuce-the-dust-servos": "res-02",
    "the-sardis-fasola-society": "res-04",
}


def tunz_dir() -> Path:
    return Path(os.environ.get("AFAR_TUNZ_FIXTURES", str(TUNZ_DEFAULT)))


def sources() -> list[tuple[str, Path]]:
    """(player_id, dir) for every act to compile — tunz artists + Vess."""
    root = tunz_dir()
    out = [
        (d.name, d)
        for d in sorted(root.iterdir())
        if d.is_dir() and (d / "dna.json").exists() and (d / "profile.json").exists()
    ]
    out.append(("vess", VESS_SRC))
    return out


def compile_all() -> list[dict]:
    entries = []
    for player_id, src in sources():
        dna = json.loads((src / "dna.json").read_text(encoding="utf-8"))
        profile = json.loads((src / "profile.json").read_text(encoding="utf-8"))
        entries.append(
            compile_roster_entry(
                dna,
                profile,
                player_id=player_id,
                display_name=profile["name"],
                first_name=FIRST_NAMES.get(player_id, profile["name"]),
                origin="design" if player_id == "vess" else "tunz",
                building=BUILDINGS.get(player_id),
            )
        )
    return entries


def write_roster(entries: list[dict]) -> None:
    ROSTER_DIR.mkdir(exist_ok=True)
    for entry in entries:
        path = ROSTER_DIR / f"{entry['player_id']}.json"
        path.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(KERNEL)}")


def _house_intents() -> dict[str, Intent]:
    """The house trio's few-shot intents, parsed back out of their prompts."""
    out = {}
    for pid, persona in PERSONAS.items():
        match = re.search(r"```json\n(.*?)\n```", persona.base_prompt, re.DOTALL)
        out[pid] = Intent.from_json(match.group(1))
    return out


def distances() -> None:
    personas = load_roster()
    vectors = {pid: intent_vector(extract_example_intent(p)) for pid, p in personas.items()}
    house = {pid: intent_vector(i) for pid, i in _house_intents().items()}

    def dist(a, b) -> float:
        return 1.0 - _cosine(a, b)

    print(f"{'act':34s} {'silt':>6s} {'rust':>6s} {'keep':>6s} {'min-house':>9s}  nearest import")
    for pid in sorted(vectors):
        d_house = {h: dist(vectors[pid], hv) for h, hv in house.items()}
        others = {o: dist(vectors[pid], ov) for o, ov in vectors.items() if o != pid}
        nearest = min(others, key=others.get)
        print(
            f"{pid:34s} {d_house['silt']:6.3f} {d_house['rust']:6.3f} {d_house['keep']:6.3f} "
            f"{min(d_house.values()):9.3f}  {nearest} ({others[nearest]:.3f})"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distances", action="store_true", help="print the intent-space report")
    args = parser.parse_args()
    if args.distances:
        distances()
    else:
        write_roster(compile_all())


if __name__ == "__main__":
    main()
