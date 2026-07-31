/**
 * Compile the world's timeline source — EVERY published release that has
 * run data — into web/fixtures/timeline-source.json as an ordered sequence
 * of set-blocks (oldest release first, newest last). The world plays the
 * blocks chronologically and loops the whole catalogue.
 *
 * Sources of truth (architecture rule 3: the JSONL log under runs/ is
 * authoritative; Neon is a derived mirror):
 *   - Neon releases rows — the catalogue: which releases exist, and their
 *     display facts that live downstream of the log (the Critic's title,
 *     era, condition, set number). Each row's metadata.runId names its run.
 *   - runs/<runId>/release-*.json — per-round lines, per-round artifact
 *     hashes, per-round signed influence edges (both spaces). A release
 *     whose run dir is missing on this machine is skipped with a note (the
 *     seeded 0001 has no step-b run at all and is always skipped).
 *
 * The committed fixture is what fixture-mode (zero env) serves; the
 * /api/timeline route overlays the same live Neon facts at request time.
 * NOTE: the fixture is baked into the deployed bundle — after a publish,
 * a redeploy/rebuild is still needed for the world to pick the new block
 * up in production (follow-up for M0/conductor: serve the timeline
 * dynamically instead).
 *
 * Usage (from web/):  node scripts/compile_timeline.mjs
 * DATABASE_URL is read from the environment, falling back to kernel/.env.
 * Nothing secret is ever printed.
 */

import { neon } from '@neondatabase/serverless';
import { readFileSync, readdirSync, existsSync, statSync, writeFileSync } from 'node:fs';
import { normalizeActNames } from '../lib/normalize-act-names.mjs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const REPO_ROOT = path.resolve(WEB_ROOT, '..');
const RUNS_ROOT = path.join(REPO_ROOT, 'runs');
const PLAYER_IDS = ['silt', 'rust', 'keep'];
const STAGE_NAMES = { silt: 'Delta Marlowe', rust: 'Roan Patina', keep: 'Evers Lane' };
const ERAS = [
  'far-past', '1950s', '1960s', '1970s', '1980s',
  '1990s', '2000s', '2010s', '2020s', '2030s', 'far-future',
];

function newestReleaseRecordFile(runDir) {
  return readdirSync(runDir)
    .filter((f) => f.startsWith('release-') && f.endsWith('.json'))
    .map((f) => ({ f, mtimeMs: statSync(path.join(runDir, f)).mtimeMs }))
    .sort((a, b) => b.mtimeMs - a.mtimeMs)
    .map(({ f }) => f)[0];
}

function loadDatabaseUrl() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  const envPath = path.join(REPO_ROOT, 'kernel', '.env');
  if (existsSync(envPath)) {
    for (const raw of readFileSync(envPath, 'utf8').split('\n')) {
      const line = raw.trim();
      if (!line || line.startsWith('#')) continue;
      const eq = line.indexOf('=');
      if (eq === -1) continue;
      if (line.slice(0, eq).trim() === 'DATABASE_URL') {
        return line.slice(eq + 1).trim().replace(/^['"]|['"]$/g, '');
      }
    }
  }
  return null;
}

/** One set-block from a release row + its run's newest release record. */
function compileBlock(releaseId, row, runId) {
  const runDir = path.join(RUNS_ROOT, runId);
  const recordFile = newestReleaseRecordFile(runDir);
  if (!recordFile) return null;
  const record = JSON.parse(readFileSync(path.join(runDir, recordFile), 'utf8'));
  const rounds = record.set.rounds;

  const linesByRound = [];
  for (let r = 0; r < rounds; r++) {
    const frame = record.rounds[String(r)] ?? record.rounds[r];
    if (!frame) throw new Error(`run ${runId} record has no round ${r}`);
    linesByRound.push(Object.fromEntries(PLAYER_IDS.map((pid) => {
      if (!frame[pid]?.line) throw new Error(`run ${runId} round ${r} is missing ${pid}'s line`);
      // Display shim: pre-voice-fix sets say "Rust"/"Keep"/"Silt"; show first names.
      return [pid, normalizeActNames(frame[pid].line)];
    })));
  }

  return {
    runId,
    releaseRecordId: record.release_id,
    releaseId,
    title: row.title ?? `AFAR-${releaseId}`,
    era: ERAS.includes(row.era) ? row.era : '2020s',
    set: typeof row.set === 'number' ? row.set : Number(releaseId),
    // The log is authoritative for the condition; the row mirrors it.
    condition: record.set.condition ?? row.condition,
    rounds,
    names: STAGE_NAMES,
    linesByRound,
    artifactsByRound: record.artifacts,
    intentEdgesByRound: record.influence.intent,
  };
}

async function main() {
  const dbUrl = loadDatabaseUrl();
  if (!dbUrl) {
    throw new Error(
      'DATABASE_URL not set and not found in kernel/.env — cannot discover the catalogue; the committed fixture is kept',
    );
  }
  const sql = neon(dbUrl);
  const rows = await sql.query('SELECT id, data FROM releases ORDER BY id');

  const blocks = [];
  for (const { id, data: row } of rows) {
    const runId = row?.metadata?.runId;
    if (!runId) {
      console.log(`release ${id} "${row?.title}" has no runId — skipped (seeded, not a logged set)`);
      continue;
    }
    if (!existsSync(path.join(RUNS_ROOT, runId))) {
      console.log(`release ${id} "${row.title}": run dir runs/${runId} missing here — skipped`);
      continue;
    }
    const block = compileBlock(id, row, runId);
    if (!block) {
      console.log(`release ${id} "${row.title}": no release-*.json in runs/${runId} — skipped`);
      continue;
    }
    blocks.push(block);
    console.log(
      `release ${id} "${block.title}" (${block.condition}, ${block.rounds} rounds) <- runs/${runId}`,
    );
  }
  if (blocks.length === 0) throw new Error('no release row joined to a run dir — nothing to compile');

  const out = path.join(WEB_ROOT, 'fixtures', 'timeline-source.json');
  writeFileSync(out, JSON.stringify({ blocks }, null, 2) + '\n');
  console.log(`wrote fixtures/timeline-source.json (${blocks.length} set-blocks, oldest first)`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((err) => { console.error(err.message); process.exit(1); });
}
