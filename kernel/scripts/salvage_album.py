"""Salvage one rendered-but-unpublished album: publish, react, republish.

Same shape the conductor uses (publish -> react -> republish so the staff's
words hang on the record they reacted to). Reads everything from the run's
own log; publish_album is idempotent, so the record keeps its number.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from afar.album import Album
from afar.config import build_config
from afar.agents.roster import load_roster
from afar.publish import newest_album_record_file, publish_album
from afar.staff import artist_display_name, run_reactions

# Loading the roster registers every imported artist id, without which an
# imported act's Intent will not validate.
load_roster()

run_dir = Path(sys.argv[1])
record = json.loads(newest_album_record_file(run_dir).read_text(encoding="utf-8"))
# `to_row()` writes the DNA through `to_dna_dict()`, which deliberately
# drops the sung words, the spoken line and the rationale — so a logged
# album record cannot round-trip through `from_json` on its own. The
# per-track `intents.jsonl` rows carry the complete Intent, so rebuild the
# tracklist from those (architecture rule 3: read it from the log).
intents = {}
for line in (run_dir / "intents.jsonl").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    intents[int(row["track"])] = row

blob = dict(record["album"])
blob["tracks"] = [
    {
        "title": t["title"],
        "note": t.get("note", ""),
        "intent": {
            **t["intent"],
            "lyrics": intents[i]["lyrics"],
            "line": intents[i].get("line", t.get("note", "")),
            "rationale": intents[i].get("rationale", ""),
        },
    }
    for i, t in enumerate(blob["tracks"])
]
album = Album.from_json(json.dumps(blob), artist_id=record["artist_id"])

out = publish_album(run_dir)
print("published:", out.release_id, "-", album.title, f"({len(album.tracks)} tracks)")

config = build_config()
reactions = run_reactions(
    album,
    run_dir=run_dir,
    config=config,
    release_id=out.release_id,
    artist_name=artist_display_name(record["artist_id"]),
    heard=record.get("heard", ()),
)
print("reactions:", [k for k, v in reactions.to_row().items() if v])

again = publish_album(run_dir, release_id=out.release_id)
print("republished with reactions:", again.release_id)
