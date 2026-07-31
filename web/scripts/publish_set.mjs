/**
 * Publish one Step B set as a release. First use: release 0002 ("First
 * Contact"), the first real three-player set (contact condition, 6 rounds,
 * live ElevenLabs renderer, MERT embedder).
 *
 * (Note: the first published run used the MOCK audio embedder — its audio-space
 * feature rows are placeholders pending a MERT re-embed; intent-space is real.)
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
 * Take selection: the Producer is NOT built yet, so for v1 this publishes the
 * FINAL round's three takes (one per player), mechanically. That fact is
 * recorded in the release row's metadata. The influence triangle shows the
 * final round's AUDIO-space graph; the zod InfluenceEdgeSchema wants weights
 * in [0, 1], so the zero-centred kernel values are clamped for display and
 * the raw signed edges (both spaces, every round) ride along in metadata —
 * web/lib/data.ts strips unknown keys on read, so metadata is pure
 * provenance, exactly like seed.mjs's track.line/intent.
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
import { readFileSync, readdirSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const RUNS_ROOT = path.join(REPO_ROOT, "runs");
const PLAYER_IDS = ["silt", "rust", "keep"];

const RELEASE_ID = "0002";
const RELEASE_TITLE = "0002 · First Contact"; // placeholder — the Critic doesn't exist yet
const SITE = "https://afar.band";

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

/** The run to publish: argv[2], or the newest step-b-contact run with a release record. */
function findRun(runIdArg) {
  const candidates = runIdArg
    ? [runIdArg]
    : readdirSync(RUNS_ROOT)
        .filter((d) => d.endsWith("step-b-contact"))
        .sort()
        .reverse();
  for (const runId of candidates) {
    const runDir = path.join(RUNS_ROOT, runId);
    if (!existsSync(runDir)) continue;
    const recordFile = readdirSync(runDir).find(
      (f) => f.startsWith("release-") && f.endsWith(".json"),
    );
    if (recordFile) return { runId, runDir, record: JSON.parse(readFileSync(path.join(runDir, recordFile), "utf8")) };
  }
  throw new Error("no step-b-contact run with a release-*.json found under runs/");
}

const clamp01 = (x) => Math.min(1, Math.max(0, x));

// --- main --------------------------------------------------------------------

async function main() {
  const sql = neon(loadDatabaseUrl());
  const { runId, runDir, record } = findRun(process.argv[2]);
  const finalRound = record.set.rounds - 1;
  console.log(`publishing run ${runId} (release_record ${record.release_id.slice(0, 12)}…), final round ${finalRound}`);

  // Final round facts: takes (hash -> mp3 path), frames, full intents.
  const artifactPathByHash = new Map(readJsonl(path.join(runDir, "artifacts.jsonl")).map((a) => [a.hash, a.path]));
  const finalIntents = new Map(
    readJsonl(path.join(runDir, "intents.jsonl"))
      .filter((row) => row.round === finalRound)
      .map((row) => [row.player, row]),
  );
  const finalFrames = record.rounds[finalRound]; // pid -> {line, lyrics, rationale}
  const finalHashes = record.artifacts[finalRound]; // pid -> content hash
  for (const pid of PLAYER_IDS) {
    if (!finalHashes[pid] || !finalFrames[pid] || !finalIntents.get(pid)) {
      throw new Error(`final round is missing player ${pid}`);
    }
  }

  // Era: majority vote over the final round's DNA (kernel logs an ERAS index).
  const eraCounts = new Map();
  for (const pid of PLAYER_IDS) {
    const era = ERAS[finalIntents.get(pid).intent.era] ?? "2020s";
    eraCounts.set(era, (eraCounts.get(era) ?? 0) + 1);
  }
  const era = [...eraCounts.entries()].sort((a, b) => b[1] - a[1])[0][0];

  // Influence triangle: the FINAL round's INTENT-space graph. This run's audio
  // embeddings are mock (embedder defaulted to mock — recompute later), and per
  // DECISIONS.md the interaction record leads with intent space anyway. Kernel
  // edges are zero-centred and, with near-orthogonal personas, all negative
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
    title: RELEASE_TITLE,
    era,
    set: 2,
    condition: record.set.condition, // "contact"
    date,
    brief:
      "No brief opened this set — the Muse is not built yet. The room was cold: three players, six rounds, contact condition. Whatever they converged on, they found in each other.",
    selection:
      "The Producer is not built yet, so no takes were culled: these are the final round's three takes, one per player, selected mechanically. Selection as a creative act begins with the next release.",
    review:
      "The Critic is not built yet. Until it exists, the record speaks uncommented: the influence graph and the players' own rationales below are the whole review.",
    reaction:
      "The Listener is not built yet. Nobody has heard this from the cheap seats.",
    takeIds: PLAYER_IDS.map((pid) => `${RELEASE_ID}-${pid}`),
    influence,
    rationales: Object.fromEntries(PLAYER_IDS.map((pid) => [pid, finalFrames[pid].rationale])),
    // Everything below is provenance: web/lib/data.ts strips unknown keys.
    metadata: {
      titlePlaceholder: true, // the Critic names releases; it doesn't exist yet
      briefPlaceholder: true, // no Muse yet
      reviewPlaceholder: true, // no Critic yet
      reactionPlaceholder: true, // no Listener yet
      producerSelection: "not built — final round's takes published mechanically",
      runId,
      releaseRecordId: record.release_id,
      set: record.set,
      influenceDisplay:
        "final-round INTENT-space graph, min-max normalized to [0,1] for InfluenceEdgeSchema (audio space was mock-embedded this run; re-embed pending)",
      influenceRawByRound: record.influence, // both spaces, every round, signed
      convergence: record.convergence, // both spaces, full curves
      novelty: record.novelty,
      asymmetry: record.asymmetry,
      artifactsByRound: record.artifacts,
      lines: Object.fromEntries(PLAYER_IDS.map((pid) => [pid, finalFrames[pid].line])),
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
    const hash = finalHashes[pid];
    const file = artifactPathByHash.get(hash);
    if (!file) throw new Error(`no artifact row for hash ${hash}`);
    const bytes = readFileSync(path.isAbsolute(file) ? file : path.join(REPO_ROOT, file));
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
    const row = finalIntents.get(pid);
    await upsertJson("tracks", `${RELEASE_ID}-${pid}`, {
      id: `${RELEASE_ID}-${pid}`,
      releaseId: RELEASE_ID,
      agentId: pid,
      title: `First Contact — ${pid.toUpperCase()}'s take`,
      durationSec: 30, // music_v2 renders 30s takes
      audioUrl: `/api/media/${finalHashes[pid]}`,
      // provenance (stripped by data.ts on read)
      line: row.line,
      intent: row.intent,
      round: finalRound,
      runId,
    });
  }
  console.log(`tracks  ${PLAYER_IDS.length} upserted`);

  await upsertJson("releases", RELEASE_ID, release);
  console.log(`release ${RELEASE_ID} "${RELEASE_TITLE}" upserted (era ${era}, ${influence.length} influence edges)`);

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
    [PLAYER_IDS.map((pid) => finalHashes[pid])],
  );
  for (const m of mediaRows) console.log(`  media ${m.id.slice(0, 12)}… ${m.content_type} ${m.bytes} bytes`);

  // Live check: the deployed site must serve every selected take.
  for (const pid of PLAYER_IDS) {
    const url = `${SITE}/api/media/${finalHashes[pid]}`;
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

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
