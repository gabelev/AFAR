/**
 * Seed Neon with the archive's derived mirror: agents/releases/tracks as
 * `data` jsonb rows (the exact shape web/lib/data.ts parses) plus a `media`
 * table of audio bytes streamed by /api/media/[id].
 *
 * Idempotent: CREATE TABLE IF NOT EXISTS + upserts keyed on id. Safe to
 * re-run; re-running with a newer run simply repoints the takes.
 *
 * Sources of truth (architecture rule 3: the JSONL log is authoritative,
 * Neon is derived):
 *   - fixtures/*.json         — agents, release frame, take titles
 *   - runs/<id>/intents.jsonl — what each player actually said (line,
 *     rationale, intent), newest run per player wins
 *   - runs/<id>/artifacts.jsonl — content hash + path of the rendered mp3;
 *     the hash is the media id, so audio URLs are content-addressed
 *
 * Usage (from web/):  node scripts/seed.mjs
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

/** Newest logged intent + artifact per player across all runs (run dir names sort by timestamp). */
function latestTakes() {
  if (!existsSync(RUNS_ROOT)) throw new Error(`runs/ not found at ${RUNS_ROOT}`);
  const takes = new Map(); // player -> { runId, intent row, artifact row }
  for (const runId of readdirSync(RUNS_ROOT).sort()) {
    const intentsFile = path.join(RUNS_ROOT, runId, "intents.jsonl");
    const artifactsFile = path.join(RUNS_ROOT, runId, "artifacts.jsonl");
    if (!existsSync(intentsFile) || !existsSync(artifactsFile)) continue;
    const artifactsByIntent = new Map(
      readJsonl(artifactsFile).map((a) => [a.intent_id, a]),
    );
    for (const intent of readJsonl(intentsFile)) {
      const artifact = artifactsByIntent.get(intent.id);
      if (!artifact || !PLAYER_IDS.includes(intent.player)) continue;
      takes.set(intent.player, { runId, intent, artifact });
    }
  }
  const missing = PLAYER_IDS.filter((p) => !takes.has(p));
  if (missing.length) throw new Error(`no logged take found for: ${missing.join(", ")}`);
  return takes;
}

// --- main --------------------------------------------------------------------

async function main() {
  const sql = neon(loadDatabaseUrl());

  const agents = JSON.parse(readFileSync(path.join(WEB_ROOT, "fixtures", "agents.json"), "utf8"));
  const releases = JSON.parse(
    readFileSync(path.join(WEB_ROOT, "fixtures", "releases.json"), "utf8"),
  );
  const tracks = JSON.parse(readFileSync(path.join(WEB_ROOT, "fixtures", "tracks.json"), "utf8"));
  const takes = latestTakes();

  await sql.query(
    "CREATE TABLE IF NOT EXISTS media (id text PRIMARY KEY, content_type text NOT NULL, bytes bytea NOT NULL)",
  );
  for (const table of ["agents", "releases", "tracks"]) {
    await sql.query(
      `CREATE TABLE IF NOT EXISTS ${table} (id text PRIMARY KEY, data jsonb NOT NULL)`,
    );
  }

  // Media: content-addressed, id IS the file's sha256.
  for (const [player, take] of takes) {
    const file = path.isAbsolute(take.artifact.path)
      ? take.artifact.path
      : path.join(REPO_ROOT, take.artifact.path);
    const bytes = readFileSync(file);
    await sql.query(
      `INSERT INTO media (id, content_type, bytes) VALUES ($1, $2, decode($3, 'hex'))
       ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, bytes = EXCLUDED.bytes`,
      [take.artifact.hash, "audio/mpeg", bytes.toString("hex")],
    );
    console.log(`media   ${player}: ${take.artifact.hash.slice(0, 12)}… (${bytes.length} bytes, run ${take.runId})`);
  }

  const upsertJson = async (table, id, data) => {
    await sql.query(
      `INSERT INTO ${table} (id, data) VALUES ($1, $2::jsonb)
       ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data`,
      [id, JSON.stringify(data)],
    );
  };

  for (const agent of agents) await upsertJson("agents", agent.id, agent);
  console.log(`agents  ${agents.length} upserted`);

  // Takes: point audioUrl at the media row; carry the player's real line +
  // intent alongside (data.ts strips unknown keys, so this is pure provenance).
  for (const track of tracks) {
    const take = takes.get(track.agentId);
    const seeded = take
      ? {
          ...track,
          durationSec: 30, // music_v2 renders 30s takes
          audioUrl: `/api/media/${take.artifact.hash}`,
          line: take.intent.line,
          intent: take.intent.intent,
        }
      : track;
    await upsertJson("tracks", track.id, seeded);
  }
  console.log(`tracks  ${tracks.length} upserted`);

  // Release 0001: fixture frame (reviews, reaction, influence) with the
  // placeholder rationales replaced by what the players actually said.
  for (const release of releases) {
    const rationales = { ...release.rationales };
    for (const [player, take] of takes) {
      if (player in rationales) rationales[player] = take.intent.rationale;
    }
    await upsertJson("releases", release.id, { ...release, rationales });
  }
  console.log(`releases ${releases.length} upserted`);

  // Verify what the site will actually read back.
  const mediaRows = await sql.query("SELECT id, content_type, length(bytes) AS bytes FROM media ORDER BY id");
  const agentCount = await sql.query("SELECT count(*)::int AS n FROM agents");
  const trackRows = await sql.query("SELECT data->>'agentId' AS agent, data->>'audioUrl' AS url FROM tracks ORDER BY id");
  const releaseRows = await sql.query("SELECT id, data->>'title' AS title FROM releases ORDER BY id");
  console.log("\nverify:");
  for (const m of mediaRows) console.log(`  media ${m.id.slice(0, 12)}… ${m.content_type} ${m.bytes} bytes`);
  console.log(`  agents ${agentCount[0].n}`);
  for (const t of trackRows) console.log(`  track ${t.agent} -> ${t.url}`);
  for (const r of releaseRows) console.log(`  release ${r.id} "${r.title}"`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
