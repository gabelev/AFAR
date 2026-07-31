"""Publish one completed set to Neon — the Python port of web/scripts/publish_set.mjs.

The conductor runs on the droplet, where there is no Node toolchain, so the
publish path lives here now: media upserts (content-addressed audio bytes),
the release + tracks rows, and — new — the compiled world timeline written
STRAIGHT to Neon (`timeline_source`, id 'current', data jsonb), the shape
`web/lib/world/timeline.ts` compiles from. `/api/timeline` prefers that row
over the build-time fixture, so a publish from the droplet reaches production
WITHOUT a rebuild — closing the old "publish recompiles the fixture but a
redeploy is still needed" caveat (DECISIONS.md 2026-07-31).

Sources of truth are unchanged (architecture rule 3: the JSONL log under
runs/ is authoritative; Neon is a derived mirror):

  - runs/<id>/release-*.json  — newest by mtime (the corrected/staff-enriched
    record; the append-only supersede chain writes several)
  - runs/<id>/intents.jsonl   — full DNA per (player, round)
  - runs/<id>/artifacts.jsonl — content hash -> mp3 path

Everything decision-shaped is a pure function (`selected_takes`,
`brief_prose`, `reaction_prose`, `build_release_row`, `build_track_rows`,
`normalized_influence`, `compile_timeline_block`) mirrored one-to-one from
publish_set.mjs / compile_timeline.mjs, so the vitest oracles over there and
the pytest units here pin the same behavior.

DRY-RUN GUARD: `publish_run(dry_run=True)` computes everything and writes
NOTHING — no psycopg import, no network. The conductor forces dry-run
whenever the renderer is mock: mock bytes must never land in the public
media table, the same never-cross-the-streams law as the live-renderer/
mock-embedder guard in scripts/step_b.py.

Requires the `publish` extra for live writes:  uv sync --extra publish
Nothing secret is ever printed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from afar.display import normalize_act_names
from afar.intent import ERAS
from afar.staff import STAGE_NAMES

PLAYER_IDS: tuple[str, ...] = ("silt", "rust", "keep")
SITE = "https://afar.band"

#: The zod default in web (ERAS mirror there) when a logged era index is junk.
_FALLBACK_ERA = "2020s"


# --- env ----------------------------------------------------------------------


def load_database_url(repo_root: Optional[Path] = None) -> Optional[str]:
    """DATABASE_URL from the environment, falling back to kernel/.env.
    Returned, never printed."""
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    root = repo_root or Path(__file__).resolve().parents[2]
    env_path = root / "kernel" / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "DATABASE_URL":
                return value.strip().strip("'\"")
    return None


# --- run log harvesting (ports of the mjs helpers, oracle-pinned) -------------


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def newest_release_record_file(run_dir: Path) -> Optional[Path]:
    """The newest release-*.json by MTIME — the corrected/staff-enriched record,
    never the alphabetically-first one (the release 0002 lesson)."""
    candidates = sorted(
        Path(run_dir).glob("release-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def selected_takes(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The takes to publish: the Producer's cut when the record carries a staff
    block, otherwise the final round's takes, mechanically. pid -> {round, hash}."""
    final_round = record["set"]["rounds"] - 1
    selected = (record.get("staff") or {}).get("producer", {}).get("selected", {})
    out: dict[str, dict[str, Any]] = {}
    for pid in PLAYER_IDS:
        if pid in selected:
            out[pid] = {"round": selected[pid]["round"], "hash": selected[pid]["take_id"]}
        else:
            out[pid] = {"round": final_round, "hash": record["artifacts"][final_round][pid]}
    return out


def brief_prose(staff: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The Muse's words — labeled honestly when carried-forward (composed AFTER
    the release it reads). None keeps the placeholder prose."""
    muse = (staff or {}).get("muse") or {}
    text = muse.get("text")
    if not text:
        return None
    if muse.get("carried_forward"):
        return (
            "What the Muse heard in this release, carried forward into the next "
            f"session: {text}"
        )
    return str(text)


def reaction_prose(staff: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The Listener's words, untouched. None keeps the placeholder."""
    text = ((staff or {}).get("listener") or {}).get("text")
    return str(text) if text else None


def normalized_influence(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The final round's INTENT-space edges, min-max normalized into the
    display schema's [0, 1] (InfluenceEdgeSchema). Kernel edges are signed
    and zero-centred; the legible signal is RELATIVE pull. An isolation set
    can leave no edges — an empty list IS the honest cover."""
    final_round = record["set"]["rounds"] - 1
    edges = (record.get("influence") or {}).get("intent", {}).get(str(final_round), {})
    values = list(edges.values())
    lo = min(values) if values else 0.0
    hi = max(values) if values else 0.0
    span = (hi - lo) or 1.0
    out = []
    for key, value in edges.items():
        to, _, frm = key.partition("<-")
        weight = round(min(1.0, max(0.0, (value - lo) / span)), 4)
        out.append({"from": frm, "to": to, "weight": weight})
    return out


def next_release_id(existing_ids: Iterable[str]) -> str:
    """The next 4-digit catalogue number after the numeric ids already in the
    releases table ('0001' seeded -> '0002' -> …)."""
    numeric = [int(i) for i in existing_ids if str(i).isdigit()]
    return f"{(max(numeric) + 1) if numeric else 1:04d}"


# --- the rows (pure ports of publish_set.mjs main()) --------------------------


def build_release_row(
    release_id: str,
    record: Mapping[str, Any],
    run_id: str,
    take_intents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """The releases-row jsonb, exactly the shape web/lib/data.ts ReleaseSchema
    parses (unknown keys under `metadata` are provenance and stripped on read)."""
    staff = record.get("staff") or None
    degraded = record.get("staff_degraded") or {}

    def _degraded_note(stage: str) -> Optional[str]:
        """The honest sentence a failed staff stage left behind (afar.staff
        STAGE_DEGRADED_NOTES) — preferred over the never-built placeholders."""
        note = (degraded.get(stage) or {}).get("note")
        return str(note) if note else None

    takes = selected_takes(record)
    take_frames = {pid: record["rounds"][takes[pid]["round"]][pid] for pid in PLAYER_IDS}

    # Era: majority vote over the selected takes' DNA (the kernel logs an index).
    era_counts: dict[str, int] = {}
    for pid in PLAYER_IDS:
        idx = take_intents[pid]["intent"].get("era")
        era = ERAS[idx] if isinstance(idx, int) and 0 <= idx < len(ERAS) else _FALLBACK_ERA
        era_counts[era] = era_counts.get(era, 0) + 1
    era = max(era_counts.items(), key=lambda kv: kv[1])[0]

    critic_title = (staff or {}).get("critic", {}).get("release_title")
    release_title = critic_title or f"Untitled Session {release_id}"
    influence = normalized_influence(record)
    date = f"{run_id[0:4]}-{run_id[4:6]}-{run_id[6:8]}"
    condition = record["set"]["condition"]
    hearing = {
        "contact": "each able to hear the others",
        "isolation": "each hearing only itself, doors closed",
        "parallel": "side by side but unable to hear each other",
    }.get(condition, f"condition {condition}")
    numbers = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
               "ten", "eleven", "twelve"]
    rounds_word = (
        numbers[record["set"]["rounds"]]
        if record["set"]["rounds"] < len(numbers)
        else str(record["set"]["rounds"])
    )

    row: dict[str, Any] = {
        "id": release_id,
        "title": release_title,
        "era": era,
        "set": int(release_id) if release_id.isdigit() else 0,
        "condition": condition,
        "date": date,
        "brief": brief_prose(staff)
        or _degraded_note("muse")
        or (
            "No brief this time — the Muse had not yet spoken. The acts went in "
            f"with nothing from outside: {rounds_word} rounds, {hearing}."
        ),
        "selection": (staff or {}).get("producer", {}).get("note")
        or _degraded_note("producer")
        or "The Producer was not yet built, so nothing was cut: these are the last "
        "round's takes, kept automatically.",
        "review": (staff or {}).get("critic", {}).get("release_review")
        or _degraded_note("critic")
        or "The Critic was not yet built. Nobody has judged this or named it — the "
        "chart and the acts' own words are the whole record.",
        "reaction": reaction_prose(staff)
        or _degraded_note("listener")
        or "The Listener was not yet built. Nobody has heard this from the cheap seats yet.",
        "takeIds": [f"{release_id}-{pid}" for pid in PLAYER_IDS],
        "influence": influence,
        "rationales": {pid: take_frames[pid].get("rationale", "") for pid in PLAYER_IDS},
        "metadata": {
            "titlePlaceholder": not critic_title,
            "titledBy": "the Critic" if critic_title else None,
            "briefPlaceholder": not (staff or {}).get("muse"),
            "reviewPlaceholder": not (staff or {}).get("critic"),
            "reactionPlaceholder": not (staff or {}).get("listener"),
            "staffDegraded": degraded or None,
            "museBrief": (staff or {}).get("muse"),
            "listenerReaction": (staff or {}).get("listener"),
            "producerSelection": (
                "the Producer's cut — one take per act, chosen from all rounds by a "
                "three-judge panel reading the log (round per act: "
                + ", ".join(f"{pid}={takes[pid]['round']}" for pid in PLAYER_IDS)
                + ")"
                if (staff or {}).get("producer")
                else (
                    "the Producer did not file this time — the final round's takes "
                    "were published mechanically"
                    if "producer" in degraded
                    else "not built — final round's takes published mechanically"
                )
            ),
            "producerReasoning": (staff or {}).get("producer", {}).get("selected"),
            "criticActReviews": (staff or {}).get("critic", {}).get("act_reviews"),
            "criticTakeTitles": (staff or {}).get("critic", {}).get("take_titles"),
            "runId": run_id,
            "releaseRecordId": record["release_id"],
            "set": record["set"],
            "recordProvenance": record.get("provenance"),
            "influenceDisplay": (
                "final-round INTENT-space graph, min-max normalized to [0,1] for "
                f"InfluenceEdgeSchema (audio-space embedder: {record['set']['embedder']['name']})"
            ),
            "influenceRawByRound": record.get("influence"),
            "convergence": record.get("convergence"),
            "novelty": record.get("novelty"),
            "asymmetry": record.get("asymmetry"),
            "artifactsByRound": record.get("artifacts"),
            "lines": {pid: take_frames[pid].get("line", "") for pid in PLAYER_IDS},
            "publishedBy": "afar.publish (conductor)",
        },
    }
    valence = (staff or {}).get("listener", {}).get("valence")
    if valence:
        row["reactionValence"] = valence
    if (staff or {}).get("producer", {}).get("selected"):
        row["selections"] = {pid: f"{release_id}-{pid}" for pid in PLAYER_IDS}
    reviews = (staff or {}).get("critic", {}).get("act_reviews")
    if reviews:
        row["reviews"] = reviews
    return row


def build_track_rows(
    release_id: str,
    record: Mapping[str, Any],
    take_intents: Mapping[str, Mapping[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    """The tracks-row jsonb per act — TrackSchema plus provenance keys."""
    staff = record.get("staff") or {}
    takes = selected_takes(record)
    release_title = staff.get("critic", {}).get("release_title") or f"Untitled Session {release_id}"
    take_titles = staff.get("critic", {}).get("take_titles", {})
    rows = []
    for pid in PLAYER_IDS:
        row = take_intents[pid]
        rows.append(
            {
                "id": f"{release_id}-{pid}",
                "releaseId": release_id,
                "agentId": pid,
                "title": take_titles.get(pid)
                or f"{release_title} — {STAGE_NAMES.get(pid, pid)}'s take",
                # The set's take length (the Producer's direction); 30 for
                # every record written before lengths were variable.
                "durationSec": int(record.get("set", {}).get("duration_s", 30)),
                "audioUrl": f"/api/media/{takes[pid]['hash']}",
                # provenance (stripped by data.ts on read)
                "titledBy": "the Critic" if take_titles.get(pid) else None,
                "line": row.get("line", ""),
                "intent": row.get("intent", {}),
                "round": takes[pid]["round"],
                "runId": run_id,
            }
        )
    return rows


# --- the timeline (pure port of compile_timeline.mjs) -------------------------


def compile_timeline_block(
    release_id: str,
    row: Mapping[str, Any],
    run_id: str,
    runs_root: Path,
) -> Optional[dict[str, Any]]:
    """One world set-block from a release row + its run's newest release record.
    Exactly the TimelineSource shape web/lib/world/timeline.ts expects.
    Returns None when the run dir has no release record."""
    run_dir = Path(runs_root) / run_id
    record_file = newest_release_record_file(run_dir)
    if record_file is None:
        return None
    record = json.loads(record_file.read_text(encoding="utf-8"))
    rounds = record["set"]["rounds"]

    lines_by_round = []
    for r in range(rounds):
        frames = record["rounds"][r]
        entry = {}
        for pid in PLAYER_IDS:
            line = (frames.get(pid) or {}).get("line")
            if not line:
                raise ValueError(f"run {run_id} round {r} is missing {pid}'s line")
            # Display shim: pre-voice-fix sets say "Rust"/"Keep"/"Silt"; show
            # first names (mirrors compile_timeline.mjs; no-op post-fix).
            entry[pid] = normalize_act_names(line)
        lines_by_round.append(entry)

    era = row.get("era")
    set_number = row.get("set")
    return {
        "runId": run_id,
        "releaseRecordId": record["release_id"],
        "releaseId": release_id,
        "title": row.get("title") or f"AFAR-{release_id}",
        "era": era if era in ERAS else _FALLBACK_ERA,
        "set": set_number if isinstance(set_number, int) else int(release_id),
        # The log is authoritative for the condition; the row mirrors it.
        "condition": record["set"].get("condition") or row.get("condition"),
        "rounds": rounds,
        "names": dict(STAGE_NAMES),
        "linesByRound": lines_by_round,
        "artifactsByRound": record["artifacts"],
        "intentEdgesByRound": record["influence"]["intent"],
    }


def compile_timeline_blocks(
    release_rows: Sequence[tuple[str, Mapping[str, Any]]],
    runs_root: Path,
) -> dict[str, Any]:
    """The whole catalogue as ordered set-blocks (oldest release first), the
    `timeline_source.data` payload. Rows without a runId (the seeded 0001) or
    with a missing run dir are skipped — same rules as compile_timeline.mjs."""
    blocks = []
    for release_id, row in sorted(release_rows, key=lambda kv: str(kv[0])):
        run_id = ((row.get("metadata") or {}).get("runId")) if isinstance(row, Mapping) else None
        if not run_id:
            continue
        if not (Path(runs_root) / run_id).is_dir():
            continue
        block = compile_timeline_block(str(release_id), row, str(run_id), runs_root)
        if block is not None:
            blocks.append(block)
    return {"blocks": blocks}


# --- publish ------------------------------------------------------------------


@dataclass(frozen=True)
class PublishOutcome:
    """What one publish did (or, dry, would have done). Never carries secrets."""

    release_id: str
    run_id: str
    release_title: str
    dry_run: bool
    media: dict[str, int] = field(default_factory=dict)  # pid -> byte count
    track_ids: tuple[str, ...] = ()
    timeline_blocks: int = 0


def _resolve_audio(path_str: str, runs_root: Path) -> Path:
    """The logged artifact path is authoritative; if the run was copied between
    machines the content-addressed basename under runs/audio still resolves."""
    p = Path(path_str)
    if p.is_file():
        return p
    fallback = Path(runs_root) / "audio" / p.name
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(f"audio file not found: {path_str} (or runs/audio/{p.name})")


def publish_run(
    run_dir: Path,
    *,
    release_id: Optional[str] = None,
    db_url: Optional[str] = None,
    dry_run: bool = False,
    connection: Any = None,
) -> PublishOutcome:
    """Publish one completed run: media -> tracks -> release -> timeline_source.

    Idempotent (upserts keyed on id). `dry_run=True` computes everything and
    touches NOTHING external — no psycopg import, no bytes read beyond the
    local run. `connection` injects a DB connection for tests; live callers
    leave it None and need the `publish` extra (psycopg[binary]).
    """
    run_dir = Path(run_dir)
    run_id = run_dir.name
    runs_root = run_dir.parent

    record_file = newest_release_record_file(run_dir)
    if record_file is None:
        raise FileNotFoundError(f"no release-*.json under {run_dir}")
    record = json.loads(record_file.read_text(encoding="utf-8"))
    takes = selected_takes(record)

    intent_rows = read_jsonl(run_dir / "intents.jsonl")
    take_intents: dict[str, Mapping[str, Any]] = {}
    for pid in PLAYER_IDS:
        match = next(
            (r for r in intent_rows if r["player"] == pid and r["round"] == takes[pid]["round"]),
            None,
        )
        if match is None:
            raise ValueError(f"selected take is missing player {pid}")
        take_intents[pid] = match

    artifact_paths = {
        a["hash"]: a["path"] for a in read_jsonl(run_dir / "artifacts.jsonl")
    }
    audio: dict[str, bytes] = {}
    for pid in PLAYER_IDS:
        file = artifact_paths.get(takes[pid]["hash"])
        if not file:
            raise ValueError(f"no artifact row for hash {takes[pid]['hash']}")
        data = _resolve_audio(file, runs_root).read_bytes()
        if len(data) < 1000:
            raise ValueError(f"suspiciously small mp3 for {pid}: {len(data)} bytes")
        audio[pid] = data

    if dry_run:
        rid = release_id or "0000"
        release_row = build_release_row(rid, record, run_id, take_intents)
        track_rows = build_track_rows(rid, record, take_intents, run_id)
        block = compile_timeline_block(rid, release_row, run_id, runs_root)
        return PublishOutcome(
            release_id=rid,
            run_id=run_id,
            release_title=release_row["title"],
            dry_run=True,
            media={pid: len(audio[pid]) for pid in PLAYER_IDS},
            track_ids=tuple(t["id"] for t in track_rows),
            timeline_blocks=1 if block else 0,
        )

    conn = connection
    if conn is None:
        import psycopg

        url = db_url or load_database_url()
        if not url:
            raise RuntimeError("DATABASE_URL not set and not found in kernel/.env")
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        conn = psycopg.connect(url)

    try:
        jsonb = _jsonb_wrapper(connection is None)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS media "
            "(id text PRIMARY KEY, content_type text NOT NULL, bytes bytea NOT NULL)"
        )
        for table in ("releases", "tracks", "timeline_source"):
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table} (id text PRIMARY KEY, data jsonb NOT NULL)"
            )

        if release_id is None:
            rows = conn.execute("SELECT id FROM releases").fetchall()
            release_id = next_release_id(r[0] for r in rows)
        release_row = build_release_row(release_id, record, run_id, take_intents)
        track_rows = build_track_rows(release_id, record, take_intents, run_id)

        for pid in PLAYER_IDS:
            conn.execute(
                "INSERT INTO media (id, content_type, bytes) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, "
                "bytes = EXCLUDED.bytes",
                (takes[pid]["hash"], "audio/mpeg", audio[pid]),
            )
        for track in track_rows:
            conn.execute(
                "INSERT INTO tracks (id, data) VALUES (%s, %s) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                (track["id"], jsonb(track)),
            )
        conn.execute(
            "INSERT INTO releases (id, data) VALUES (%s, %s) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
            (release_id, jsonb(release_row)),
        )

        # The world's timeline, recompiled over the WHOLE catalogue and written
        # to Neon — /api/timeline prefers this row, so no rebuild is needed.
        all_rows = conn.execute("SELECT id, data FROM releases ORDER BY id").fetchall()
        release_rows = [(r[0], _as_mapping(r[1])) for r in all_rows]
        timeline = compile_timeline_blocks(release_rows, runs_root)
        conn.execute(
            "INSERT INTO timeline_source (id, data) VALUES ('current', %s) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
            (jsonb(timeline),),
        )
        conn.commit()
    finally:
        if connection is None:
            conn.close()

    return PublishOutcome(
        release_id=release_id,
        run_id=run_id,
        release_title=release_row["title"],
        dry_run=False,
        media={pid: len(audio[pid]) for pid in PLAYER_IDS},
        track_ids=tuple(t["id"] for t in track_rows),
        timeline_blocks=len(timeline["blocks"]),
    )


def _jsonb_wrapper(live: bool):
    """psycopg needs dicts wrapped in Jsonb; injected test connections take raw."""
    if live:
        from psycopg.types.json import Jsonb

        return Jsonb
    return lambda value: value


def _as_mapping(value: Any) -> Mapping[str, Any]:
    """Rows come back as dicts from psycopg's jsonb loader; injected test
    connections may hand back JSON strings."""
    if isinstance(value, str):
        return json.loads(value)
    return value
