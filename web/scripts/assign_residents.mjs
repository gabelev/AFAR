/**
 * Assign every roster artist a street address on Archive Row, and write
 * the tenant fields the world reads (lib/world/residents.ts contract)
 * onto their Neon agent rows: top-level `building`, `accent`,
 * `accentDark`, `prop` (plus the kernel import's nested resident.building,
 * kept in sync).
 *
 * Assignment is STABLE and deterministic:
 *   - vess keeps the authored res-03 with the design's guest violet + amp;
 *   - a row that already names a valid building KEEPS it (a re-run, or a
 *     future arrival, never reshuffles the town);
 *   - every unhoused import artist then takes the next free shell in
 *     registry id order (res-01, res-02, res-04, …), themselves ordered by
 *     slug — so the initial 21 imports land res-01..res-22 around vess and
 *     res-23..res-28 stay FOR LEASE headroom;
 *   - accent/accentDark/prop are derived from the artist's Creative DNA by
 *     scripts/lib/dna.mjs — the same derivation that builds their sprite
 *     (world-sprites.json), so the console trim in their room matches
 *     their coat.
 *
 * Usage (from web/):  node scripts/assign_residents.mjs [--dry-run]
 * DATABASE_URL is read from the environment, falling back to the repo
 * root .env, then kernel/.env. Nothing secret is ever printed.
 */

import { neon } from "@neondatabase/serverless";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { residentLook } from "./lib/dna.mjs";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const ROSTER_DIR = path.join(REPO_ROOT, "kernel", "afar", "agents", "roster");

const VESS = {
  building: "res-03",
  accent: "#8a6f9e",
  accentDark: "#5e4a6c",
  prop: "amp",
};

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

async function main() {
  const dryRun = process.argv.includes("--dry-run");
  const sql = neon(loadDatabaseUrl());

  const registry = JSON.parse(readFileSync(path.join(WEB_ROOT, "world-geometry.json"), "utf8"));
  const shells = registry.street.buildings.map((b) => b.id);

  const roster = readdirSync(ROSTER_DIR)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .map((f) => JSON.parse(readFileSync(path.join(ROSTER_DIR, f), "utf8")));

  const rows = await sql.query("SELECT id, data FROM agents ORDER BY id");
  const byId = new Map(rows.map((r) => [r.id, r.data]));

  // Existing claims hold: never reshuffle a housed artist.
  const taken = new Map(); // building -> slug
  for (const [id, data] of byId) {
    const b = data?.building ?? data?.resident?.building;
    if (typeof b === "string" && shells.includes(b) && !taken.has(b)) taken.set(b, id);
  }
  // vess's authored room is reserved even before her row claims it
  if (!taken.has(VESS.building)) taken.set(VESS.building, "vess");

  const freeShells = shells.filter((s) => !taken.has(s));
  const patches = [];
  for (const entry of roster) {
    const slug = entry.player_id;
    const data = byId.get(slug);
    if (!data) {
      console.log(`skip    ${slug} — no agents row (run import_tunz_roster first)`);
      continue;
    }
    const existing = [data.building, data.resident?.building].find(
      (b) => typeof b === "string" && shells.includes(b),
    );
    let building;
    if (slug === "vess") building = VESS.building;
    else if (existing && taken.get(existing) === slug) building = existing;
    else {
      building = freeShells.shift();
      if (!building) throw new Error(`the street is full — no shell left for ${slug}`);
      taken.set(building, slug);
    }
    const tenant =
      slug === "vess"
        ? VESS
        : (({ accent, accentD, prop }) => ({ building, accent, accentDark: accentD, prop }))(
            residentLook(slug, entry.palette),
          );
    patches.push({
      slug,
      patch: {
        ...tenant,
        building,
        resident: { ...(data.resident ?? { origin: entry.origin }), building },
      },
    });
  }

  for (const { slug, patch } of patches) {
    console.log(
      `${dryRun ? "would " : ""}assign ${slug.padEnd(34)} ${patch.building}  accent=${patch.accent} prop=${patch.prop ?? "—"}`,
    );
    if (dryRun) continue;
    await sql.query(
      `UPDATE agents SET data = data || $2::jsonb WHERE id = $1`,
      [slug, JSON.stringify(patch)],
    );
  }

  // verify what the site will read back
  const check = await sql.query(
    `SELECT id, data->>'building' AS building FROM agents WHERE data->>'building' IS NOT NULL ORDER BY data->>'building'`,
  );
  console.log(`\n${dryRun ? "(dry run) " : ""}housed rows in Neon: ${check.length}`);
  for (const r of check) console.log(`  ${r.building}  ${r.id}`);
}

main().catch((err) => {
  console.error(err.message ?? err);
  process.exit(1);
});
