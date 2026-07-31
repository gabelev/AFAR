/**
 * One-time, idempotent display fix for the ALREADY-PUBLISHED Neon rows from
 * the pre-voice-fix sets (releases 0002–0004): the acts addressed each other
 * by internal id ("Rust", "Keep", "Silt") because the kernel didn't know the
 * stage names yet (fixed in PR #20). Neon is a derived display mirror — the
 * append-only JSONL log under runs/ is never edited — so the display rows are
 * normalized to first names via the shared, human-reviewed shim in
 * web/lib/normalize-act-names.mjs (see DECISIONS.md).
 *
 * Touches ONLY quoted generated speech on display surfaces:
 *   - releases rows: data.rationales.* and data.metadata.lines.*
 *   - tracks rows:   data.line
 *   - timeline_source row (when the conductor has published one): each
 *     block's linesByRound — the world's speech bubbles
 * Titles, reviews, briefs, reactions, and internal staff reasoning
 * (metadata.producerReasoning) are left exactly as published.
 *
 * Idempotent: rows already normalized produce no writes. Safe to re-run.
 *
 * Usage (from web/):  node scripts/normalize_names.mjs [--dry-run]
 * DATABASE_URL is read from the environment, falling back to kernel/.env.
 * Nothing secret is ever printed.
 */

import { neon } from '@neondatabase/serverless';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeActNames } from '../lib/normalize-act-names.mjs';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const DRY_RUN = process.argv.includes('--dry-run');

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

/** Normalize every string value of a flat record in place; return field count changed. */
function normalizeRecord(record) {
  if (!record || typeof record !== 'object') return 0;
  let changed = 0;
  for (const [key, value] of Object.entries(record)) {
    if (typeof value !== 'string') continue;
    const after = normalizeActNames(value);
    if (after !== value) {
      record[key] = after;
      changed += 1;
    }
  }
  return changed;
}

async function main() {
  const dbUrl = loadDatabaseUrl();
  if (!dbUrl) throw new Error('DATABASE_URL not set and not found in kernel/.env');
  const sql = neon(dbUrl);

  let rowsUpdated = 0;
  let fieldsChanged = 0;

  for (const { id, data } of await sql.query('SELECT id, data FROM releases ORDER BY id')) {
    let changed = normalizeRecord(data.rationales);
    changed += normalizeRecord(data.metadata?.lines);
    if (changed === 0) continue;
    fieldsChanged += changed;
    rowsUpdated += 1;
    console.log(`releases/${id}: ${changed} field(s) normalized${DRY_RUN ? ' (dry run)' : ''}`);
    if (!DRY_RUN) {
      await sql.query('UPDATE releases SET data = $2::jsonb WHERE id = $1', [
        id,
        JSON.stringify(data),
      ]);
    }
  }

  for (const { id, data } of await sql.query('SELECT id, data FROM tracks ORDER BY id')) {
    if (typeof data.line !== 'string') continue;
    const after = normalizeActNames(data.line);
    if (after === data.line) continue;
    data.line = after;
    fieldsChanged += 1;
    rowsUpdated += 1;
    console.log(`tracks/${id}: line normalized${DRY_RUN ? ' (dry run)' : ''}`);
    if (!DRY_RUN) {
      await sql.query('UPDATE tracks SET data = $2::jsonb WHERE id = $1', [
        id,
        JSON.stringify(data),
      ]);
    }
  }

  // The publish-time timeline (kernel/afar/publish.py writes it; the table
  // does not exist before the conductor's first publish).
  try {
    for (const { id, data } of await sql.query('SELECT id, data FROM timeline_source')) {
      let changed = 0;
      for (const block of data?.blocks ?? []) {
        for (const round of block.linesByRound ?? []) changed += normalizeRecord(round);
      }
      if (changed === 0) continue;
      fieldsChanged += changed;
      rowsUpdated += 1;
      console.log(`timeline_source/${id}: ${changed} line(s) normalized${DRY_RUN ? ' (dry run)' : ''}`);
      if (!DRY_RUN) {
        await sql.query('UPDATE timeline_source SET data = $2::jsonb WHERE id = $1', [
          id,
          JSON.stringify(data),
        ]);
      }
    }
  } catch {
    console.log('timeline_source table not present yet — skipped');
  }

  console.log(
    `${DRY_RUN ? '[dry run] would update' : 'updated'} ${rowsUpdated} row(s), ${fieldsChanged} field(s)`,
  );
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
