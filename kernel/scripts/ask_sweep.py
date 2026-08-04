"""Ask the whole roster, in four honestly-constructed states, with real calls.

    cd kernel && uv run python scripts/ask_sweep.py            # all 25 x 4
    cd kernel && uv run python scripts/ask_sweep.py --states just-released

This is the verification the ask exists to survive: if every artist says yes
whatever state it is in, "artists decide when they record" is rotation with
extra cost, and the prompt (`player._ASK_LAW`) is the bug. It is a manual
script, not a test — it spends real Anthropic tokens (the cheap ask model
only; no renderer runs, no ElevenLabs spend, no rows are logged into `runs/`).

The four states are the corners of the space the live loop actually produces:

  debut           never recorded here, town silent (the cold-start corner)
  just-released   2 hours since its own record, town silent
  fresh-busy      20 hours since its own record, 3 records out since, heard
  long-silent     30 days since its own record, town silent, heard nothing
  long-heard      18 days since its own record, 6 records out since, heard 4
  dead-town       120 days since its own record, town silent, heard nothing

Prints the yes/no distribution per state and every reason verbatim.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from afar.agents.personas import PERSONAS  # noqa: E402
from afar.agents.player import Player  # noqa: E402
from afar.agents.roster import load_roster  # noqa: E402
from afar.conductor import _load_dotenv  # noqa: E402
from afar.intent import PLAYER_IDS  # noqa: E402
from afar.perception.album_context import HeardAlbum, HeardTrack, build_ask_context  # noqa: E402
from afar.render.base import MockRenderer  # noqa: E402

#: Invented sleeves — plausible records by artists who do not exist, so the
#: sweep never depends on what happens to be in the live log.
_SLEEVES = [
    HeardAlbum(
        artist_id="ghost-a",
        artist_name="Nell Faraday",
        album_id="AFAR-9001",
        title="Sixteen Feet of Rope",
        description="Four songs recorded in a stairwell with the door propped open.",
        tracks=(
            HeardTrack(title="Cold Landing", note="I sang it facing the wall.", content_hash="g1"),
            HeardTrack(title="Handrail", note="One take, one hand.", content_hash="g2"),
        ),
    ),
    HeardAlbum(
        artist_id="ghost-b",
        artist_name="Otis Vane",
        album_id="AFAR-9002",
        title="Municipal Pool, Drained",
        description="A record about tiled rooms and the noise they make back at you.",
        tracks=(
            HeardTrack(title="Deep End Ladder", note="The reverb is the room.", content_hash="g3"),
            HeardTrack(title="Chlorine Light", note="Kept the hum in.", content_hash="g4"),
        ),
    ),
    HeardAlbum(
        artist_id="ghost-c",
        artist_name="Marisol Deene",
        album_id="AFAR-9003",
        title="Two Cans and a Long Wire",
        description="Everything on it was played twice and mixed once.",
        tracks=(
            HeardTrack(title="String Telephone", note="Recorded from the far end.", content_hash="g5"),
            HeardTrack(title="Tin Bottom", note="I let the clipping stay.", content_hash="g6"),
        ),
    ),
    HeardAlbum(
        artist_id="ghost-d",
        artist_name="Ruben Alcott",
        album_id="AFAR-9004",
        title="Feeder Road at Four",
        description="Written in a parked car, played standing up.",
        tracks=(
            HeardTrack(title="Hazard Lights", note="Counted it in with the indicator.", content_hash="g7"),
            HeardTrack(title="Verge Grass", note="No chorus. There wasn't one.", content_hash="g8"),
        ),
    ),
]


def _own_last(artist_id: str, name: str) -> HeardAlbum:
    return HeardAlbum(
        artist_id=artist_id,
        artist_name=name,
        album_id="AFAR-8999",
        title="The Last One You Made",
        description="Your previous record, as the archive has it.",
        # Deliberately inert: an own-last sleeve that hints at unfinished
        # business ("you left the ending open") is a leading question, and the
        # first sweep proved it — every artist answered it instead of the ask.
        tracks=(
            HeardTrack(title="First Side", note="That one came out the way I wanted.", content_hash="o1"),
            HeardTrack(title="Second Side", note="Played it plain, and it stayed plain.", content_hash="o2"),
        ),
    )


#: name -> (hours since own last record — None for a debut, records released
#: since, how many of them reached this artist)
STATES: dict[str, tuple[float | None, int, int]] = {
    "debut": (None, 0, 0),
    "just-released": (2.0, 0, 0),
    "fresh-busy": (20.0, 3, 3),
    "long-silent": (30 * 24.0, 0, 0),
    "long-heard": (18 * 24.0, 6, 4),
    # The deadlock corner: a town that went completely quiet. If this is 0%
    # forever, silence is self-sustaining and the piece can die of it.
    "dead-town": (120 * 24.0, 0, 0),
}


def _build_ask_model():
    from afar.config import ASK_MAX_TOKENS

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set — this script makes real calls.")
    from ensemble.providers.anthropic import AnthropicProvider

    model_id = os.environ.get("AFAR_ASK_MODEL", "claude-haiku-4-5")
    print(f"ask model: {model_id}\n", flush=True)
    return AnthropicProvider(api_key, model=model_id, max_tokens=ASK_MAX_TOKENS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", nargs="*", default=list(STATES), choices=list(STATES))
    parser.add_argument("--limit", type=int, default=0, help="only the first N artists")
    args = parser.parse_args(argv)

    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    model = _build_ask_model()
    renderer = MockRenderer(Path("/tmp/afar-ask-sweep"))

    personas = {pid: PERSONAS[pid] for pid in PLAYER_IDS}
    personas.update(load_roster())
    if args.limit:
        personas = dict(list(personas.items())[: args.limit])

    totals: dict[str, tuple[int, int]] = {}
    for state_name in args.states:
        hours, released, heard_count = STATES[state_name]
        yes = no = 0
        span = "never recorded" if hours is None else f"{hours:.0f}h since"
        print(f"\n=== {state_name} "
              f"({span}, {released} released since, {heard_count} heard) ===",
              flush=True)
        for artist_id, persona in personas.items():
            player = Player(persona, model, renderer)
            name = persona.metadata.get("display_name", artist_id)
            context = build_ask_context(
                artist_id,
                heard=tuple(_SLEEVES[:heard_count]),
                own_last=None if hours is None else _own_last(artist_id, name),
                hours_since_last_record=hours,
                records_released_since=released,
            )
            try:
                urge = player.consider_record(context)
            except Exception as err:  # noqa: BLE001 — a sweep reports, never dies
                print(f"  !! {artist_id}: {type(err).__name__}: {err}", flush=True)
                continue
            yes, no = (yes + 1, no) if urge.ready else (yes, no + 1)
            mark = "YES" if urge.ready else "no "
            print(f"  {mark} {artist_id:<28} {urge.why}", flush=True)
        totals[state_name] = (yes, no)

    print("\n=== distribution ===")
    for state_name, (yes, no) in totals.items():
        total = yes + no
        share = f"{yes / total:.0%}" if total else "n/a"
        print(f"  {state_name:<16} yes {yes:>3} / no {no:>3}   ({share} yes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
