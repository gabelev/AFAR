/**
 * Publish one Step B set as a release. First use: release 0002 ("First
 * Contact"), the first real three-player set (contact condition, 6 rounds,
 * live ElevenLabs renderer, MERT embedder).
 *
 * (History: the first published run used the MOCK audio embedder — its
 * audio-space features were placeholders. kernel/scripts/reembed.py appended
 * corrected MERT rows and a NEW release-*.json; that is why this script picks
 * the NEWEST release record by mtime — the newest is the corrected one, and
 * its `provenance` block rides along in the release metadata.)
 *
 * Modeled on seed.mjs (same tables, same idempotent upserts). Sources of
 * truth (architecture rule 3: the JSONL log is authoritative, Neon is a
 * derived mirror):
 *   - runs/<id>/release-*.json  — the content-addressed interaction record
 *     (influence graphs per round in both spaces, convergence, novelty,
 *     asymmetry, per-round line/lyrics/rationale, artifact hashes)
 *   - runs/<id>/intents.jsonl   — full DNA per (player, round), for era +
 *     track provenance
 *   - runs/<id>/artifacts.jsonl — content hash -> mp3 path; the hash is the
 *     media id, so audio URLs are content-addressed
 *
 * Take selection: when the newest release record carries a `staff` block
 * (kernel/afar/staff.py — the Producer's cut and the Critic's word, appended
 * at the set boundary), this script publishes the PRODUCER-selected takes
 * (which may come from different rounds per act), the Critic's release title
 * and per-take titles (superseding the interim line-derived titles), the
 * Critic's reviews (release verdict + per-act verdicts), and the Producer's
 * public selection note. Panel reasoning and dissents ride along in metadata.
 * Records without a staff block fall back to the pre-staff behavior: the
 * FINAL round's three takes, mechanically, with placeholder prose. The
 * influence triangle shows the final round's INTENT-space graph either way —
 * it is a fact about the set, not about the cut; the zod InfluenceEdgeSchema
 * wants weights in [0, 1], so the zero-centred kernel values are normalized
 * for display and the raw signed edges (both spaces, every round) ride along
 * in metadata — web/lib/data.ts strips unknown keys on read, so metadata is
 * pure provenance, exactly like seed.mjs's track.line/intent.
 *
 * Idempotent: upserts keyed on id. Touches ONLY release "0002" and its
 * tracks/media — release 0001 and the agents table are never written.
 *
 * Usage (from web/):  node scripts/publish_set.mjs [runId]
 *   runId optional; defaults to the newest runs/<id> ending in
 *   "step-b-contact" that contains a release-*.json.
 * DATABASE_URL is read from the environment, falling back to kernel/.env.
 * Nothing secret is ever printed.
 */

import { neon } from "@neondatabase/serverless";
import { readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const RUNS_ROOT = path.join(REPO_ROOT, "runs");
const PLAYER_IDS = ["silt", "rust", "keep"];

const RELEASE_ID = "0002";
const RELEASE_TITLE = "First Contact"; // fallback for pre-staff records; the Critic's title supersedes it
const SITE = "https://afar.band";

// Display-only stage names (DECISIONS.md: stage names over stable ids).
const STAGE_NAMES = { silt: "Delta Marlowe", rust: "Roan Patina", keep: "Evers Lane" };

// Mirror of web/lib/intent/schema.ts ERAS — the kernel logs era as an index.
const ERAS = [
  "far-past", "1950s", "1960s", "1970s", "1980s",
  "1990s", "2000s", "2010s", "2020s", "2030s", "far-future",
];

// --- env ---------------------------------------------------------------------

function loadDatabaseUrl() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  const envPath = path.join(REPO_ROOT, "kernel", ".env");
  if (existsSync(envPath)) {
    for (const raw of readFileSync(envPath, "utf8").split("\n")) {
      const line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      const eq = line.indexOf("=");
      if (eq === -1) continue;
      if (line.slice(0, eq).trim() === "DATABASE_URL") {
        return line
          .slice(eq + 1)
          .trim()
          .replace(/^['"]|['"]$/g, "");
      }
    }
  }
  throw new Error("DATABASE_URL not set and not found in kernel/.env");
}

// --- run log harvesting ------------------------------------------------------

function readJsonl(file) {
  return readFileSync(file, "utf8")
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l));
}

/**
 * The run dir's release record to publish: the NEWEST release-*.json by mtime.
 * A run can carry several — the kernel's append-only correction path
 * (kernel/scripts/reembed.py) writes a new content-addressed record next to
 * the superseded one — and the newest is always the corrected/current one.
 * Returns the file name, or undefined when the dir has no record.
 */
export function newestReleaseRecordFile(runDir) {
  return readdirSync(runDir)
    .filter((f) => f.startsWith("release-") && f.endsWith(".json"))
    .map((f) => ({ f, mtimeMs: statSync(path.join(runDir, f)).mtimeMs }))
    .sort((a, b) => b.mtimeMs - a.mtimeMs)
    .map(({ f }) => f)[0];
}

/** The run to publish: argv[2], or the newest step-b-contact run with a release record. */
export function findRun(runIdArg, runsRoot = RUNS_ROOT) {
  const candidates = runIdArg
    ? [runIdArg]
    : readdirSync(runsRoot)
        .filter((d) => d.endsWith("step-b-contact"))
        .sort()
        .reverse();
  for (const runId of candidates) {
    const runDir = path.join(runsRoot, runId);
    if (!existsSync(runDir)) continue;
    const recordFile = newestReleaseRecordFile(runDir);
    if (recordFile) return { runId, runDir, record: JSON.parse(readFileSync(path.join(runDir, recordFile), "utf8")) };
  }
  throw new Error("no step-b-contact run with a release-*.json found under runs/");
}

const clamp01 = (x) => Math.min(1, Math.max(0, x));

/**
 * The takes to publish: the Producer's cut when the record carries a staff
 * block, otherwise (pre-staff records) the final round's takes, mechanically.
 * Returns { [pid]: { round, hash } }; the Producer's cut may span rounds.
 */
export function selectedTakes(record) {
  const finalRound = record.set.rounds - 1;
  const selected = record.staff?.producer?.selected;
  return Object.fromEntries(
    PLAYER_IDS.map((pid) =>
      selected?.[pid]
        ? [pid, { round: selected[pid].round, hash: selected[pid].take_id }]
        : [pid, { round: finalRound, hash: record.artifacts[finalRound][pid] }],
    ),
  );
}

// --- main --------------------------------------------------------------------

async function main() {
  const sql = neon(loadDatabaseUrl());
  const { runId, runDir, record } = findRun(process.argv[2]);
  const finalRound = record.set.rounds - 1;
  const staff = record.staff ?? null;
  const takes = selectedTakes(record);
  console.log(
    `publishing run ${runId} (release_record ${record.release_id.slice(0, 12)}…), ` +
      (staff
        ? `Producer's cut: ${PLAYER_IDS.map((pid) => `${pid} r${takes[pid].round}`).join(", ")}`
        : `no staff block — final round ${finalRound} mechanically`),
  );

  // Selected-take facts: takes (hash -> mp3 path), frames, full intents.
  const artifactPathByHash = new Map(readJsonl(path.join(runDir, "artifacts.jsonl")).map((a) => [a.hash, a.path]));
  const intentRows = readJsonl(path.join(runDir, "intents.jsonl"));
  const takeIntents = new Map(
    PLAYER_IDS.map((pid) => [
      pid,
      intentRows.find((row) => row.player === pid && row.round === takes[pid].round),
    ]),
  );
  const takeFrames = Object.fromEntries(
    PLAYER_IDS.map((pid) => [pid, record.rounds[takes[pid].round]?.[pid]]),
  ); // pid -> {line, lyrics, rationale} for the SELECTED round
  for (const pid of PLAYER_IDS) {
    if (!takes[pid]?.hash || !takeFrames[pid] || !takeIntents.get(pid)) {
      throw new Error(`selected take is missing player ${pid}`);
    }
  }

  // Era: majority vote over the selected takes' DNA (kernel logs an ERAS index).
  const eraCounts = new Map();
  for (const pid of PLAYER_IDS) {
    const era = ERAS[takeIntents.get(pid).intent.era] ?? "2020s";
    eraCounts.set(era, (eraCounts.get(era) ?? 0) + 1);
  }
  const era = [...eraCounts.entries()].sort((a, b) => b[1] - a[1])[0][0];

  // Titles and staff prose: the Critic names releases and takes; the Producer
  // explains the cut. Pre-staff records keep the interim placeholder prose.
  const releaseTitle = staff?.critic?.release_title ?? RELEASE_TITLE;

  // Influence triangle: the FINAL round's INTENT-space graph — per DECISIONS.md
  // the interaction record leads with intent space (audio-space features are
  // real MERT since the re-embed, but flagged weak until the persona gate
  // passes in audio). Kernel edges are zero-centred and, with near-orthogonal
  // personas, all negative
  // (identity held); the legible signal is RELATIVE pull, so min-max normalize
  // the six final-round edges into the display schema's [0, 1]. Raw signed
  // values (both spaces, every round) ride along in metadata.
  const finalIntentEdges = record.influence.intent[String(finalRound)];
  const edgeValues = Object.values(finalIntentEdges);
  const lo = Math.min(...edgeValues);
  const hi = Math.max(...edgeValues);
  const span = hi - lo || 1;
  const influence = Object.entries(finalIntentEdges).map(([key, value]) => {
    const [to, from] = key.split("<-");
    return { from, to, weight: Number(clamp01((value - lo) / span).toFixed(4)) };
  });

  const date = `${runId.slice(0, 4)}-${runId.slice(4, 6)}-${runId.slice(6, 8)}`;

  const release = {
    id: RELEASE_ID,
    title: releaseTitle,
    era,
    set: 2,
    condition: record.set.condition, // "contact"
    date,
    brief:
      "No brief this time — the Muse was not yet built. The acts went in with nothing from outside: six rounds, each able to hear the others.",
    selection:
      staff?.producer?.note ??
      "The Producer was not yet built, so nothing was cut: these are the last round's takes, kept automatically.",
    review:
      staff?.critic?.release_review ??
      "The Critic was not yet built. Nobody has judged this or named it — the chart and the acts' own words are the whole record.",
    reaction: "The Listener was not yet built. Nobody has heard this from the cheap seats yet.",
    takeIds: PLAYER_IDS.map((pid) => `${RELEASE_ID}-${pid}`),
    // The Producer's picks, act id -> take id. Only written when the staff
    // block exists — the act pages feature these as each act's single.
    ...(staff?.producer?.selected
      ? { selections: Object.fromEntries(PLAYER_IDS.map((pid) => [pid, `${RELEASE_ID}-${pid}`])) }
      : {}),
    influence,
    rationales: Object.fromEntries(PLAYER_IDS.map((pid) => [pid, takeFrames[pid].rationale])),
    // Per-act verdicts from the Critic — rendered on the act pages.
    ...(staff?.critic?.act_reviews ? { reviews: staff.critic.act_reviews } : {}),
    // Everything below is provenance: web/lib/data.ts strips unknown keys.
    metadata: {
      titlePlaceholder: !staff?.critic?.release_title,
      titledBy: staff?.critic?.release_title ? "the Critic" : null,
      briefPlaceholder: true, // no Muse yet
      reviewPlaceholder: !staff?.critic,
      reactionPlaceholder: true, // no Listener yet
      producerSelection: staff?.producer
        ? `the Producer's cut — one take per act, chosen from all rounds by a three-judge panel reading the log (round per act: ${PLAYER_IDS.map((pid) => `${pid}=${takes[pid].round}`).join(", ")})`
        : "not built — final round's takes published mechanically",
      producerReasoning: staff?.producer?.selected ?? null, // scores, reasoning, dissents per act
      criticActReviews: staff?.critic?.act_reviews ?? null,
      criticTakeTitles: staff?.critic?.take_titles ?? null,
      runId,
      releaseRecordId: record.release_id,
      set: record.set,
      // The kernel's correction trail (e.g. {audio_reembedded_from: "mock",
      // embedder: "mert", supersedes_release_id} or the staff supersession) —
      // absent on first-take records.
      recordProvenance: record.provenance ?? null,
      influenceDisplay:
        `final-round INTENT-space graph, min-max normalized to [0,1] for InfluenceEdgeSchema (audio-space embedder: ${record.set.embedder.name})`,
      influenceRawByRound: record.influence, // both spaces, every round, signed
      convergence: record.convergence, // both spaces, full curves
      novelty: record.novelty,
      asymmetry: record.asymmetry,
      artifactsByRound: record.artifacts,
      lines: Object.fromEntries(PLAYER_IDS.map((pid) => [pid, takeFrames[pid].line])),
    },
  };

  // --- upserts (media -> tracks -> release), keyed on id — idempotent --------

  await sql.query(
    "CREATE TABLE IF NOT EXISTS media (id text PRIMARY KEY, content_type text NOT NULL, bytes bytea NOT NULL)",
  );
  for (const table of ["releases", "tracks"]) {
    await sql.query(`CREATE TABLE IF NOT EXISTS ${table} (id text PRIMARY KEY, data jsonb NOT NULL)`);
  }

  for (const pid of PLAYER_IDS) {
    const hash = takes[pid].hash;
    const file = artifactPathByHash.get(hash);
    if (!file) throw new Error(`no artifact row for hash ${hash}`);
    // The logged path is authoritative; if the run was copied between
    // machines the content-addressed basename under runs/audio still resolves.
    let mp3 = path.isAbsolute(file) ? file : path.join(REPO_ROOT, file);
    if (!existsSync(mp3)) mp3 = path.join(RUNS_ROOT, "audio", path.basename(file));
    const bytes = readFileSync(mp3);
    if (bytes.length < 1000) throw new Error(`suspiciously small mp3 for ${pid}: ${bytes.length} bytes`);
    await sql.query(
      `INSERT INTO media (id, content_type, bytes) VALUES ($1, $2, decode($3, 'hex'))
       ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, bytes = EXCLUDED.bytes`,
      [hash, "audio/mpeg", bytes.toString("hex")],
    );
    console.log(`media   ${pid}: ${hash.slice(0, 12)}… (${bytes.length} bytes)`);
  }

  const upsertJson = async (table, id, data) => {
    await sql.query(
      `INSERT INTO ${table} (id, data) VALUES ($1, $2::jsonb)
       ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data`,
      [id, JSON.stringify(data)],
    );
  };

  for (const pid of PLAYER_IDS) {
    const row = takeIntents.get(pid);
    await upsertJson("tracks", `${RELEASE_ID}-${pid}`, {
      id: `${RELEASE_ID}-${pid}`,
      releaseId: RELEASE_ID,
      agentId: pid,
      // The Critic's take title supersedes the interim line-derived title.
      title: staff?.critic?.take_titles?.[pid] ?? `${releaseTitle} — ${STAGE_NAMES[pid]}'s take`,
      durationSec: 30, // music_v2 renders 30s takes
      audioUrl: `/api/media/${takes[pid].hash}`,
      // provenance (stripped by data.ts on read)
      titledBy: staff?.critic?.take_titles?.[pid] ? "the Critic" : null,
      line: row.line,
      intent: row.intent,
      round: takes[pid].round,
      runId,
    });
  }
  console.log(`tracks  ${PLAYER_IDS.length} upserted`);

  await upsertJson("releases", RELEASE_ID, release);
  console.log(`release ${RELEASE_ID} "${releaseTitle}" upserted (era ${era}, ${influence.length} influence edges)`);

  // --- verify: what the site will actually read back -------------------------

  const releaseRows = await sql.query("SELECT id, data->>'title' AS title FROM releases ORDER BY id");
  for (const r of releaseRows) console.log(`  release ${r.id} "${r.title}"`);
  const trackRows = await sql.query(
    "SELECT id, data->>'audioUrl' AS url FROM tracks WHERE data->>'releaseId' = $1 ORDER BY id",
    [RELEASE_ID],
  );
  for (const t of trackRows) console.log(`  track ${t.id} -> ${t.url}`);
  const mediaRows = await sql.query(
    "SELECT id, content_type, length(bytes) AS bytes FROM media WHERE id = ANY($1) ORDER BY id",
    [PLAYER_IDS.map((pid) => takes[pid].hash)],
  );
  for (const m of mediaRows) console.log(`  media ${m.id.slice(0, 12)}… ${m.content_type} ${m.bytes} bytes`);

  // Live check: the deployed site must serve every selected take.
  for (const pid of PLAYER_IDS) {
    const url = `${SITE}/api/media/${takes[pid].hash}`;
    const res = await fetch(url, { method: "GET" });
    const type = res.headers.get("content-type") ?? "?";
    await res.body?.cancel();
    console.log(`  live  ${pid} ${res.status} ${type} ${url}`);
    if (res.status !== 200 || !type.startsWith("audio/mpeg")) {
      throw new Error(`live media check failed for ${pid}: ${res.status} ${type}`);
    }
  }
  console.log("done.");
}

// Import-safe (tests import the record-selection helpers); run only as a CLI.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((err) => {
    console.error(err.message);
    process.exit(1);
  });
}
