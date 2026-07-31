/**
 * Press photos for the three acts — the design handoff's 960×1200 pixel
 * portraits (design/handoff/photos/, checked in under web/public/press/).
 * They replace the AI-image portraits.
 *
 * Bytes land in the Neon `media` table content-addressed by sha256
 * (seed.mjs's pattern); agents rows get data.imageUrl = /api/media/<hash>,
 * and the checked-in fixtures are rewritten to carry the same URLs. In
 * fixture mode those URLs 404 and the pages fall back to the identical
 * static file under /press/ — zero-env pages show the same photo.
 *
 * Idempotent: content-addressed upserts + jsonb_set. Safe to re-run.
 *
 * Usage (from web/):  node scripts/press_photos.mjs [--verify-live]
 * DATABASE_URL is read from the environment, falling back to kernel/.env.
 * Nothing secret is ever printed.
 */

import { neon } from "@neondatabase/serverless";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const SITE = "https://afar.band";

// stable act id -> checked-in press photo
const PRESS = {
  keep: "press-evers.png",
  rust: "press-roan.png",
  silt: "press-delta.png",
};

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

async function main() {
  const verifyLive = process.argv.includes("--verify-live");
  const sql = neon(loadDatabaseUrl());

  await sql.query(
    "CREATE TABLE IF NOT EXISTS media (id text PRIMARY KEY, content_type text NOT NULL, bytes bytea NOT NULL)",
  );

  const urls = new Map(); // act id -> /api/media/<hash>
  for (const [actId, file] of Object.entries(PRESS)) {
    const bytes = readFileSync(path.join(WEB_ROOT, "public", "press", file));
    const hash = createHash("sha256").update(bytes).digest("hex");
    await sql.query(
      `INSERT INTO media (id, content_type, bytes) VALUES ($1, $2, decode($3, 'hex'))
       ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, bytes = EXCLUDED.bytes`,
      [hash, "image/png", bytes.toString("hex")],
    );
    const url = `/api/media/${hash}`;
    await sql.query(
      `UPDATE agents SET data = jsonb_set(data, '{imageUrl}', to_jsonb($2::text), true) WHERE id = $1`,
      [actId, url],
    );
    urls.set(actId, url);
    console.log(`media  ${actId}: ${file} -> ${hash.slice(0, 12)}… (${bytes.length} bytes)`);
  }

  // Fixtures mirror the same URLs (fixture-mode parity; ArtImage falls back
  // to the identical /press/ static file when these 404 without a DB).
  const fixturePath = path.join(WEB_ROOT, "fixtures", "agents.json");
  const agents = JSON.parse(readFileSync(fixturePath, "utf8"));
  for (const agent of agents) {
    if (urls.has(agent.id)) agent.imageUrl = urls.get(agent.id);
  }
  writeFileSync(fixturePath, JSON.stringify(agents, null, 2) + "\n");
  console.log("fixtures updated");

  // Verify what the site will read back.
  const rows = await sql.query(
    "SELECT id, data->>'imageUrl' AS url FROM agents WHERE data->>'kind' = 'player' ORDER BY id",
  );
  console.log("\nverify:");
  for (const r of rows) console.log(`  agent ${r.id} -> ${r.url}`);

  if (verifyLive) {
    for (const [actId, url] of urls) {
      const res = await fetch(`${SITE}${url}`);
      const type = res.headers.get("content-type") ?? "?";
      await res.body?.cancel();
      console.log(`  live  ${actId} ${res.status} ${type} ${SITE}${url}`);
      if (res.status !== 200 || !type.startsWith("image/")) {
        throw new Error(`live media check failed for ${actId}: ${res.status} ${type}`);
      }
    }
  }
  console.log("done.");
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
