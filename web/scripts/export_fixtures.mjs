/**
 * Snapshot Neon into the committed fixtures — the zero-env data source.
 *
 * web/lib/data.ts reads Neon when DATABASE_URL is set and falls back to
 * fixtures/*.json otherwise (local dev without a DB, tests, a Neon outage).
 * This script keeps that fallback world current: it reads the `data` jsonb
 * of agents/releases/tracks/tapes plus the compiled timeline row
 * (timeline_source, id 'current') and rewrites the fixture files.
 *
 * Row payloads are copied VERBATIM — no whitelist — so provenance and
 * forward-compatible fields (a track's `line`/`intent`, an agent's future
 * `building` metadata) ride along; data.ts's zod schemas tolerate and strip
 * unknown keys at parse time. Media stays out: the jsonb rows reference
 * audio and art by `/api/media/<hash>` URL only, and those URLs are kept
 * as-is (fixture mode 404s them; the UI's fallback ladder handles it).
 *
 * Output is deterministic — rows sorted by id (codepoint order), object
 * keys sorted recursively, 2-space indent, trailing newline — so a re-run
 * against unchanged data is a no-op and diffs stay reviewable.
 *
 * Usage (from web/):  node scripts/export_fixtures.mjs
 * DATABASE_URL is read from the environment, falling back to the repo
 * root .env, then kernel/.env. Nothing secret is ever printed.
 */

import { neon } from "@neondatabase/serverless";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const FIXTURES = path.join(WEB_ROOT, "fixtures");

// --- env ---------------------------------------------------------------------

function loadDatabaseUrl() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  for (const envPath of [path.join(REPO_ROOT, ".env"), path.join(REPO_ROOT, "kernel", ".env")]) {
    if (!existsSync(envPath)) continue;
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
  throw new Error("DATABASE_URL not set and not found in .env or kernel/.env");
}

// --- deterministic serialization ---------------------------------------------

/** Recursively sort object keys (arrays keep their order) so diffs are stable. */
function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((k) => [k, sortKeys(value[k])]),
    );
  }
  return value;
}

function writeFixture(name, value) {
  const file = path.join(FIXTURES, name);
  writeFileSync(file, `${JSON.stringify(sortKeys(value), null, 2)}\n`);
  return file;
}

// --- main --------------------------------------------------------------------

async function main() {
  const sql = neon(loadDatabaseUrl());
  const rowsOf = async (query) => {
    const result = await sql.query(query);
    return Array.isArray(result) ? result : (result.rows ?? []);
  };

  for (const table of ["agents", "releases", "tracks", "tapes"]) {
    const rows = (await rowsOf(`SELECT data FROM ${table} ORDER BY id`)).map((r) => r.data);
    // Never write an empty snapshot — an outage mid-export must not wipe
    // the fallback world the fixtures exist to provide.
    if (rows.length === 0) throw new Error(`${table}: no rows — refusing to write an empty fixture`);
    for (const row of rows) {
      if (typeof row?.id !== "string" || row.id.length === 0) {
        throw new Error(`${table}: a row is missing its string id — refusing to snapshot`);
      }
      if ("bytes" in row) throw new Error(`${table} row ${row.id}: unexpected embedded bytes`);
    }
    // Codepoint sort in JS so the order never depends on the DB collation.
    rows.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    writeFixture(`${table}.json`, rows);
    console.log(`${table.padEnd(8)} ${rows.length} rows -> fixtures/${table}.json`);
  }

  const tlRows = await rowsOf("SELECT data FROM timeline_source WHERE id = 'current'");
  const timeline = tlRows[0]?.data;
  if (!Array.isArray(timeline?.blocks) || timeline.blocks.length === 0) {
    throw new Error("timeline_source 'current' is missing or empty — refusing to snapshot");
  }
  writeFixture("timeline-source.json", timeline);
  console.log(`timeline ${timeline.blocks.length} blocks -> fixtures/timeline-source.json`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
