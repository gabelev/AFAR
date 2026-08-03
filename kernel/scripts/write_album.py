"""Manual: ask one real artist for one real record. NOT a test.

    cd kernel && uv run python scripts/write_album.py --artist silt --tracks 3

Model call only — no audio is rendered and nothing is logged, so this costs
Anthropic tokens and zero ElevenLabs money. It exists to read the WRITING: the
sleeve, the song titles, the lyrics, and whether the record hangs together as
a record. With no ANTHROPIC_API_KEY set it runs on the mock voice, which is
the honest way to check the wiring before spending anything.

`--heard` seats the artist in a scene: it hears two invented sleeves by other
artists, so the traceability law has something to be traceable to.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.agents.roster import load_roster
from afar.config import build_config
from afar.perception.album_context import HeardAlbum, HeardTrack, build_album_context

_SCENE: tuple[HeardAlbum, ...] = (
    HeardAlbum(
        artist_id="rust",
        artist_name="Roan Patina",
        album_id="AFAR-0011",
        title="Oxide in the Joist",
        description=(
            "Four takes left on a windowsill through a wet month, played back "
            "with whatever the weather took out of them."
        ),
        tracks=(
            HeardTrack(
                title="Standpipe",
                note="Cut the second bar of the guitar and kept the hiss.",
                content_hash="h1",
                heard={
                    "tempo_bpm": 74.0,
                    "loudness": "quiet",
                    "brightness": "dark",
                    "duration_s": 45.0,
                    "moved": "away_from_you",
                },
            ),
            HeardTrack(
                title="The Sill It Sat On",
                note="Left the whole middle out. The edges healed over.",
                content_hash="h2",
            ),
        ),
    ),
    HeardAlbum(
        artist_id="keep",
        artist_name="Evers Lane",
        album_id="AFAR-0012",
        title="A Door Left Open",
        description=(
            "The four chords the room keeps coming back to, set plainly enough "
            "that a stranger could pick them up in one hearing."
        ),
        tracks=(
            HeardTrack(
                title="Chairs Set Out",
                note="Four chords, played plain, back to the top.",
                content_hash="h3",
                heard={
                    "tempo_bpm": 108.0,
                    "loudness": "mid",
                    "brightness": "bright",
                    "duration_s": 45.0,
                    "moved": "toward_you",
                },
            ),
            HeardTrack(
                title="The Book in Pencil",
                note="Dated it and played it once, the way I always do.",
                content_hash="h4",
            ),
        ),
    ),
)


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
    parser = argparse.ArgumentParser(description="Write one album with one artist.")
    parser.add_argument("--artist", default="silt", help="player_id (house trio or roster)")
    parser.add_argument("--tracks", type=int, default=3)
    parser.add_argument("--seconds", type=int, default=45)
    parser.add_argument("--heard", action="store_true", help="seat the artist in a scene")
    parser.add_argument("--json", action="store_true", help="dump the whole record as JSON")
    args = parser.parse_args()

    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    config = build_config()

    personas = dict(PERSONAS)
    personas.update(load_roster())
    if args.artist not in personas:
        raise SystemExit(f"unknown artist {args.artist!r}; try one of {sorted(personas)}")
    persona = personas[args.artist]

    player = Player(persona, config.model, config.renderer)
    context = build_album_context(
        args.artist, heard=_SCENE if args.heard else (), own_last=None
    )
    print(f"artist   {persona.name} ({args.artist})")
    print(f"model    {'live' if config.live else 'mock'}")
    print(f"record   {args.tracks} tracks x {args.seconds}s"
          f"{'  (heard 2 records)' if args.heard else '  (heard nothing)'}\n")

    album = player.write_album(context, n_tracks=args.tracks, duration_s=args.seconds)

    print("=" * 72)
    print(f"{album.title.upper()}")
    print(f"{album.description}")
    print("=" * 72)
    for i, track in enumerate(album.tracks, start=1):
        print(f"\n{i}. {track.title}")
        print(f'   "{track.note}"')
        for line in track.lyrics.splitlines():
            print(f"      {line}")
    print(f"\nWHY THIS RECORD: {album.rationale}\n")
    if args.json:
        print(json.dumps(album.to_row(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
