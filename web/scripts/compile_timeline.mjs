/**
 * Compile the world's timeline source for release 0002 (the First Contact
 * set) into web/fixtures/timeline-source.json.
 *
 * Sources of truth (architecture rule 3: the JSONL log under runs/ is
 * authoritative; Neon is a derived mirror):
 *   - runs/<id>/release-*.json — per-round lines, per-round artifact
 *     hashes, per-round signed influence edges (both spaces).
 *   - Neon releases row 0002 — display facts that live downstream of the
 *     log: the Critic's title, era, condition. Read-only here; used when
 *     reachable, otherwise the fixture keeps its last committed values.
 *
 * The committed fixture is what fixture-mode (zero env) serves; the
 * /api/timeline route overlays the same live Neon facts at request time.
 *
 * Usage (from web/):  node scripts/compile_timeline.mjs [runId]
 */

import { neon } from '@neondatabase/serverless';
import { readFileSync, readdirSync, existsSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const REPO_ROOT = path.resolve(WEB_ROOT, '..');
const RUNS_ROOT = path.join(REPO_ROOT, 'runs');
const RELEASE_ID = '0002';
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

function findRun(runIdArg) {
  const candidates = runIdArg
    ? [runIdArg]
    : readdirSync(RUNS_ROOT).filter((d) => d.endsWith('step-b-contact')).sort().reverse();
  for (const runId of candidates) {
    const runDir = path.join(RUNS_ROOT, runId);
    if (!existsSync(runDir)) continue;
    const recordFile = newestReleaseRecordFile(runDir);
    if (recordFile) {
      return { runId, record: JSON.parse(readFileSync(path.join(runDir, recordFile), 'utf8')) };
    }
  }
  throw new Error('no step-b-contact run with a release-*.json found under runs/');
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

async function main() {
  const { runId, record } = findRun(process.argv[2]);
  const rounds = record.set.rounds;

  const linesByRound = [];
  for (let r = 0; r < rounds; r++) {
    const frame = record.rounds[String(r)] ?? record.rounds[r];
    if (!frame) throw new Error(`run record has no round ${r}`);
    linesByRound.push(Object.fromEntries(PLAYER_IDS.map((pid) => {
      if (!frame[pid]?.line) throw new Error(`round ${r} is missing ${pid}'s line`);
      return [pid, frame[pid].line];
    })));
  }

  // Era from the log's final-round DNA lives in intents.jsonl; the release
  // row already carries the published era — prefer the row, fall back to 2020s.
  const source = {
    runId,
    releaseRecordId: record.release_id,
    releaseId: RELEASE_ID,
    title: 'First Contact', // overwritten by the live release row below when reachable
    era: '2020s',
    set: 2,
    condition: record.set.condition,
    rounds,
    names: STAGE_NAMES,
    linesByRound,
    artifactsByRound: record.artifacts,
    intentEdgesByRound: record.influence.intent,
  };

  const dbUrl = loadDatabaseUrl();
  if (dbUrl) {
    try {
      const sql = neon(dbUrl);
      const rows = await sql.query('SELECT data FROM releases WHERE id = $1', [RELEASE_ID]);
      const row = rows[0]?.data;
      if (row && row.metadata?.runId === runId) {
        source.title = row.title;
        source.era = ERAS.includes(row.era) ? row.era : source.era;
        source.set = row.set;
        source.condition = row.condition;
        console.log(`overlaid live release row: "${row.title}" (era ${row.era})`);
      } else if (row) {
        console.log(`release row is from run ${row.metadata?.runId} — keeping log-only fixture`);
      }
    } catch (err) {
      console.log(`Neon unreachable (${err.message}) — keeping log-only fixture`);
    }
  }

  const out = path.join(WEB_ROOT, 'fixtures', 'timeline-source.json');
  writeFileSync(out, JSON.stringify(source, null, 2) + '\n');
  console.log(`wrote fixtures/timeline-source.json (run ${runId}, ${rounds} rounds)`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((err) => { console.error(err.message); process.exit(1); });
}
