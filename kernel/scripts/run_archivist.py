"""The vault opens: the Archivist's retrospective pass over ALL history. NOT a test.

    cd kernel && uv run python scripts/run_archivist.py --runs            # shelve + publish every session tape
    cd kernel && uv run python scripts/run_archivist.py --runs <id> ...   # specific runs only
    cd kernel && uv run python scripts/run_archivist.py --albums          # liner notes for the import back-catalogue
    cd kernel && uv run python scripts/run_archivist.py --release-0001    # liner notes for the seeded release row
    cd kernel && uv run python scripts/run_archivist.py --install-agent   # upsert the Archivist's agents row
    cd kernel && uv run python scripts/run_archivist.py --dump-tapes      # print the tapes rows (fixture material)

Meant to run ON THE DROPLET (the canonical runs/ lives there) from a temp
worktree, BETWEEN sets — the salvage precedent. The script refuses to start
while the conductor is mid-set (`--force` overrides): it reads the conductor
ledger's tail and requires the last set-shaped event to be closed.

What each mode does (model calls only — ZERO audio is generated):

--runs        For every non-smoke run dir (chronological), `run_archivist`
              shelves the session's tape (an `archives` row; released runs
              also get release liner notes + a superseding release record),
              then publishes: every take's audio (content-addressed) + the
              tapes row; released runs additionally get `linerNotes` set on
              their existing releases row via a surgical jsonb update — the
              row is NEVER rebuilt wholesale, so the display-name shim on the
              pre-voice-fix corpus stays intact (the normalize_names.mjs
              precedent). Idempotent: runs with a logged shelving are skipped
              (--reshelve to redo).

--albums      For every Neon agent row carrying an import album, the
              Archivist writes "what this record is" from the act's profile/
              DNA + the album's track titles, stored at data.album.linerNotes
              (skip when present; --reshelve to redo).

--release-0001  The seeded release has no run dir; its notes are written
              from the release row itself + its three source solo tapes.

Reads .env if present (never committed; nothing secret is ever printed).
With no ANTHROPIC_API_KEY this runs on MockProvider — the honest offline
wiring check; pair with --dry-run to write nothing anywhere.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from afar.archive import load_tape_view, newest_shelving
from afar.config import build_config
from afar.publish import load_database_url, publish_tape
from afar.staff import STAGE_NAMES
from afar.staff_rounds import run_archivist

#: Run-dir name fragments that are sessions (everything the vault shelves).
_RUN_MARKERS = ("step-a", "step-b", "-set-")

#: The Archivist's agents row — the staff page's data (web fixtures carry the
#: same row; keep the two in sync by hand, like the other staff).
ARCHIVIST_AGENT_ROW: dict[str, Any] = {
    "id": "archivist",
    "kind": "staff",
    "name": "The Archivist",
    "displayName": "The Archivist",
    "role": "Staff — placement",
    "stance": "Nothing recorded is ever worthless. Some things are just shelved wrong.",
    "description": [
        "The Archivist decides where everything belongs. Sessions produce far more "
        "than the releases keep — takes nobody picked, whole sessions the Producer "
        "refused, sketches that stopped mid-set — and all of it goes on the public "
        "shelf: every session's full tape, catalogued, with the Archivist's notes "
        "on the back of the sleeve.",
        "The Critic judges. The Archivist just knows where it goes.",
    ],
    "bio": (
        "The Archivist keeps the vault, and keeps it open: every session's full "
        "tape — the takes the Producer passed over, the session the panel refused, "
        "the set a machine failure cut short — shelved public, catalogued, with "
        "liner notes on the back. \"Nothing recorded is ever worthless. Some "
        "things are just shelved wrong.\""
    ),
    "palette": None,
    "imageUrl": None,
}


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


def conductor_between_sets(runs_root: Path) -> bool:
    """True when the conductor's ledger says no set is in flight — the only
    time this retrospective may touch the canonical runs/ (one-writer
    courtesy; the salvage precedent). A missing ledger is 'between sets'."""
    path = Path(runs_root) / "conductor" / "conductor.jsonl"
    if not path.exists():
        return True
    open_set: Optional[int] = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        kind = row.get("kind")
        if row.get("smoke"):
            continue
        if kind == "set_started":
            open_set = int(row.get("set_index", -1))
        elif kind in ("set_completed", "set_failed", "set_aborted", "stopped"):
            open_set = None
    return open_set is None


def _connect():
    import psycopg

    url = load_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL not set and not found in kernel/.env")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return psycopg.connect(url)


def _release_by_run(conn) -> dict[str, str]:
    """runId -> release id, from the live releases rows."""
    rows = conn.execute("SELECT id, data->'metadata'->>'runId' FROM releases").fetchall()
    return {run_id: str(rid) for rid, run_id in rows if run_id}


def _session_run_dirs(runs_root: Path) -> list[Path]:
    return sorted(
        p
        for p in Path(runs_root).iterdir()
        if p.is_dir()
        and any(marker in p.name for marker in _RUN_MARKERS)
        and "smoke" not in p.name
        and (p / "artifacts.jsonl").exists()
    )


def do_runs(args, config) -> int:
    conn = None if args.dry_run else _connect()
    by_run = _release_by_run(conn) if conn else {}
    try:
        run_dirs = (
            [Path(config.runs_root) / rid for rid in args.run_ids]
            if args.run_ids
            else _session_run_dirs(config.runs_root)
        )
        for run_dir in run_dirs:
            release_id = by_run.get(run_dir.name)
            if args.dry_run:
                # Writes NOTHING — not even shelving rows (the canonical log
                # is the droplet's; a preview must not touch it).
                tape = publish_tape(run_dir, release_id=release_id, dry_run=True)
                print(
                    f"{run_dir.name}: DRY tape={tape.tape_id} takes={tape.takes} "
                    f"bytes={tape.media_bytes} shelved={tape.shelved} release={release_id}"
                )
                continue

            shelved = newest_shelving(run_dir)
            if shelved is not None and not args.reshelve:
                print(f"{run_dir.name}: already shelved — skipping (use --reshelve to redo)")
            else:
                print(f"{run_dir.name}: shelving …", flush=True)
                outcome = run_archivist(run_dir, config)
                if outcome.degraded:
                    print(f"  DEGRADED: {outcome.degraded} — tape will publish unshelved")
                elif outcome.shelving is not None:
                    s = outcome.shelving
                    print(f"  placement  {s.placement}")
                    print(f"  tape       {s.tape_title}")
                    print(f"  arc        {s.arc}")

            tape = publish_tape(run_dir, release_id=release_id, connection=conn)
            conn.commit()
            print(
                f"  published TAPE-{tape.tape_id} \"{tape.title}\" — {tape.takes} takes, "
                f"{tape.media_bytes} bytes of audio"
            )
            if release_id:
                # Surgical liner-notes update on the existing releases row —
                # never a wholesale rebuild (protects the display-name shim
                # on the pre-voice-fix corpus).
                view = load_tape_view(run_dir)
                staff = (view.record or {}).get("staff") or {}
                notes = (staff.get("archivist") or {}).get("liner_notes")
                if notes:
                    from afar.display import normalize_act_names

                    conn.execute(
                        "UPDATE releases SET data = jsonb_set(jsonb_set(data, "
                        "'{linerNotes}', %s::jsonb), '{metadata,linerNotesBy}', "
                        "'\"the Archivist\"'::jsonb) WHERE id = %s",
                        (json.dumps(normalize_act_names(str(notes))), release_id),
                    )
                    conn.commit()
                    print(f"  releases/{release_id}: linerNotes set")
    finally:
        if conn is not None:
            conn.close()
    return 0


def do_albums(args, config) -> int:
    from afar.agents.archivist import ArchivistAgent

    conn = None if args.dry_run else _connect()
    archivist = ArchivistAgent(config.model)
    try:
        if conn is None:
            print("--albums needs the live rows; use without --dry-run (model calls only)")
            return 1
        rows = conn.execute(
            "SELECT id, data FROM agents WHERE data->'album' IS NOT NULL ORDER BY id"
        ).fetchall()
        for agent_id, data in rows:
            data = data if isinstance(data, dict) else json.loads(data)
            album = data.get("album") or {}
            if album.get("linerNotes") and not args.reshelve:
                print(f"{agent_id}: album notes present — skipping")
                continue
            track_rows = conn.execute(
                "SELECT data->>'title' FROM tracks WHERE data->>'releaseId' = %s ORDER BY id",
                (album.get("id"),),
            ).fetchall()
            profile = {
                "act": data.get("displayName") or data.get("name"),
                "genre_and_era": data.get("genreLine"),
                "descriptor": data.get("descriptor"),
                "stance": data.get("stance"),
                "bio": data.get("bio"),
                "sound_palette": data.get("palette"),
                "album_title": album.get("title"),
                "tracks": [t[0] for t in track_rows] or "(no audio has arrived in town yet)",
                "origin": (data.get("resident") or {}).get("origin"),
            }
            print(f"{agent_id}: writing notes for \"{album.get('title')}\" …", flush=True)
            notes = archivist.album_liner_notes(profile)
            conn.execute(
                "UPDATE agents SET data = jsonb_set(data, '{album,linerNotes}', %s::jsonb) "
                "WHERE id = %s",
                (json.dumps(notes), agent_id),
            )
            conn.commit()
            print(f"  {notes[:140]}…" if len(notes) > 140 else f"  {notes}")
    finally:
        if conn is not None:
            conn.close()
    return 0


def do_release_0001(args, config) -> int:
    """The seeded release (no run dir): notes from the row + its solo tapes."""
    from afar.agents.archivist import ArchivistAgent

    conn = _connect()
    try:
        (row,) = conn.execute("SELECT data FROM releases WHERE id = '0001'").fetchall()
        data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        if data.get("linerNotes") and not args.reshelve:
            print("0001: linerNotes present — skipping")
            return 0
        # Its session context: the newest solo run per act (seed.mjs's rule).
        solo_context = {}
        for run_dir in _session_run_dirs(config.runs_root):
            if "step-a" not in run_dir.name:
                continue
            view = load_tape_view(run_dir)
            act = view.players[0] if view.players else None
            if act:
                solo_context[STAGE_NAMES.get(act, act)] = {
                    "solo_session": run_dir.name,
                    "takes": len(view.takes),
                    "last_line": view.takes[-1].line if view.takes else "",
                }
        record_like = {
            "release": {k: data.get(k) for k in ("title", "era", "brief", "selection", "review")},
            "rationales": data.get("rationales"),
            "context": (
                "This is the world's first release, assembled from three SOLO sessions "
                "recorded before the acts could hear each other — one single per act, "
                "the newest take of each act's solo tapes: "
                + json.dumps(solo_context, ensure_ascii=False)
            ),
        }
        archivist = ArchivistAgent(config.model)
        notes = archivist.album_liner_notes(record_like)
        if args.dry_run:
            print(notes)
            return 0
        conn.execute(
            "UPDATE releases SET data = jsonb_set(jsonb_set(data, '{linerNotes}', %s::jsonb), "
            "'{metadata,linerNotesBy}', '\"the Archivist\"'::jsonb) WHERE id = '0001'",
            (json.dumps(notes),),
        )
        conn.commit()
        print("0001: linerNotes set")
        print(notes)
    finally:
        conn.close()
    return 0


def do_install_agent(args) -> int:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO agents (id, data) VALUES (%s, %s::jsonb) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
            ("archivist", json.dumps(ARCHIVIST_AGENT_ROW)),
        )
        conn.commit()
        print("agents/archivist: upserted")
    finally:
        conn.close()
    return 0


def do_dump_tapes(args) -> int:
    conn = _connect()
    try:
        rows = conn.execute("SELECT data FROM tapes ORDER BY id").fetchall()
        tapes = [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows]
        print(json.dumps(tapes, indent=2, ensure_ascii=False))
    finally:
        conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="The Archivist's retrospective pass.")
    parser.add_argument("--runs", action="store_true", help="shelve + publish session tapes")
    parser.add_argument("run_ids", nargs="*", help="specific run ids (default: all sessions)")
    parser.add_argument("--albums", action="store_true", help="import back-catalogue liner notes")
    parser.add_argument("--release-0001", action="store_true", help="notes for the seeded release")
    parser.add_argument("--install-agent", action="store_true", help="upsert the agents row")
    parser.add_argument("--dump-tapes", action="store_true", help="print the tapes rows as JSON")
    parser.add_argument("--reshelve", action="store_true", help="redo already-shelved work")
    parser.add_argument("--dry-run", action="store_true", help="write nothing anywhere")
    parser.add_argument("--force", action="store_true", help="skip the between-sets check")
    args = parser.parse_args()

    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    config = build_config()

    if args.runs and not args.force and not conductor_between_sets(config.runs_root):
        print("the conductor is MID-SET — refusing to touch the canonical runs/ "
              "(wait for the boundary, or --force if you know better)")
        return 1

    if args.install_agent:
        return do_install_agent(args)
    if args.dump_tapes:
        return do_dump_tapes(args)
    if args.albums:
        return do_albums(args, config)
    if args.release_0001:
        return do_release_0001(args, config)
    if args.runs:
        return do_runs(args, config)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
