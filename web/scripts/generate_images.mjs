/**
 * AI portraits for the three acts + the album cover for release 0001.
 *
 * gpt-image-1 (the client afar_music proved out) renders one square image per
 * act and one square cover; bytes land in the Neon `media` table
 * content-addressed by sha256 (seed.mjs's pattern), agents rows get
 * data.imageUrl = /api/media/<hash>, release 0001 gets data.coverUrl, and the
 * checked-in fixtures are rewritten to carry the same URLs so fixture mode
 * stays in step (there the URLs 404 and pages fall back to the Radar plate —
 * the accepted degradation).
 *
 * Prompts are built from each act's fixture stance/palette plus the intent
 * DNA (seedPrompt, visualStyle, lyricalObsessions, era) of its newest logged
 * take — read from runs/<id>/intents.jsonl when present, otherwise from the
 * intent provenance seed.mjs mirrors onto the Neon tracks rows.
 *
 * Idempotent: an image is only generated when its slot is empty (or its
 * media row is missing). `--force silt,cover` regenerates named slots.
 * A hard budget of MAX_CALLS API calls (including retries) caps spend.
 *
 * Usage (from web/):  node scripts/generate_images.mjs [--force all|silt,rust,keep,cover]
 * OPENAI_API_KEY and DATABASE_URL come from the environment, falling back to
 * kernel/.env. Nothing secret is ever printed.
 */

import { neon } from "@neondatabase/serverless";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const RUNS_ROOT = path.join(REPO_ROOT, "runs");
const PLAYER_IDS = ["silt", "rust", "keep"];
const RELEASE_ID = "0001";
const MAX_CALLS = 6; // total gpt-image-1 calls this run, retries included

// Matches web/lib/intent/schema.ts — intent.era indexes into this scale.
const ERAS = ["far-past", "1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s", "2030s", "far-future"];

// --- env ---------------------------------------------------------------------

function loadEnv(key) {
  if (process.env[key]) return process.env[key];
  const envPath = path.join(REPO_ROOT, "kernel", ".env");
  if (existsSync(envPath)) {
    for (const raw of readFileSync(envPath, "utf8").split("\n")) {
      const line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      const eq = line.indexOf("=");
      if (eq === -1) continue;
      if (line.slice(0, eq).trim() === key) {
        return line
          .slice(eq + 1)
          .trim()
          .replace(/^['"]|['"]$/g, "");
      }
    }
  }
  throw new Error(`${key} not set and not found in kernel/.env`);
}

// --- intent DNA --------------------------------------------------------------

function readJsonl(file) {
  return readFileSync(file, "utf8")
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l));
}

/** Newest logged intent per player from runs/ (dir names sort by timestamp). */
function intentsFromRuns() {
  if (!existsSync(RUNS_ROOT)) return new Map();
  const intents = new Map();
  for (const runId of readdirSync(RUNS_ROOT).sort()) {
    const file = path.join(RUNS_ROOT, runId, "intents.jsonl");
    if (!existsSync(file)) continue;
    for (const row of readJsonl(file)) {
      if (PLAYER_IDS.includes(row.player) && row.intent) intents.set(row.player, row.intent);
    }
  }
  return intents;
}

/** Fallback: seed.mjs mirrors each take's intent onto its Neon tracks row. */
async function intentsFromDb(sql) {
  const rows = await sql.query(
    "SELECT data->>'agentId' AS player, data->'intent' AS intent FROM tracks WHERE data ? 'intent'",
  );
  const intents = new Map();
  for (const r of rows) if (PLAYER_IDS.includes(r.player) && r.intent) intents.set(r.player, r.intent);
  return intents;
}

// --- prompts -----------------------------------------------------------------

/**
 * One series style across all four images: the label's paper-toned, serif,
 * archival register. Deliberately NOT glossy pop.
 */
const SERIES_STYLE =
  "Muted paper-toned palette on a warm off-white ground, quiet archival art-label aesthetic, " +
  "like a plate from a small-press monograph. Soft natural light, matte surfaces, subtle grain. " +
  "Absolutely no text, no lettering, no logos, no watermark.";

/** Per-act medium: painterly vs photographic follows the act's character. */
const ACT_MEDIUM = {
  silt: "Painterly portrait in warm layered oils, visible strata of over-painting — earlier passes left showing through, nothing scraped away.",
  rust: "Degraded analog photograph, emulsion flaking and half gone, grey overexposure eating the edges; what survives of the figure is sharp.",
  keep: "Clean, composed film photograph in steady evening light, classically framed, gently hopeful.",
};

const ACT_ACCENT = {
  silt: "warm ochre",
  rust: "oxidized rust-brown (#94512e)",
  keep: "muted sage-green (#5f7261)",
};

function portraitPrompt(agent, intent) {
  const era = ERAS[intent?.era] ?? "2020s";
  const parts = [
    `Portrait of ${agent.displayName}, a fictional musical act on a small art-music label — the act embodying ${roleWord(agent)}.`,
    `Their stance: "${agent.stance}"`,
    intent?.seedPrompt ? `The act reads as: ${intent.seedPrompt}.` : "",
    `Era: ${era}, period-appropriate dress and instruments.`,
    intent?.visualStyle?.length ? `Visual atmosphere: ${intent.visualStyle.join(", ")}.` : "",
    intent?.lyricalObsessions?.length ? `Motifs held quietly in the scene: ${intent.lyricalObsessions.join("; ")}.` : "",
    `Dominant accent tone: ${ACT_ACCENT[agent.id]}.`,
    ACT_MEDIUM[agent.id],
    "One of a series of three roster portraits sharing a single visual language.",
    SERIES_STYLE,
  ];
  return parts.filter(Boolean).join(" ");
}

function roleWord(agent) {
  return agent.role.split("—")[1]?.trim() ?? agent.role;
}

function coverPrompt(release) {
  return [
    `Album cover artwork for a split release by three fictional acts on a small art-music label.`,
    `Era: ${release.era}. Conditions the set was played under: ${release.condition}.`,
    `The image: standing water — flat still floodwater that has stopped moving, holding the color of an overcast sky, keeping everything that fell in.`,
    `Three registers share the frame, one per act: warm ochre sediment layers settled beneath the surface (accumulation);`,
    `a worn, eroded band of oxidized rust-brown (#94512e) where the water has eaten an edge away (erosion);`,
    `and one clean, intact horizontal line in muted sage-green (#5f7261) holding the composition steady (continuity).`,
    `Square album cover composition, painterly and restrained.`,
    SERIES_STYLE,
  ].join(" ");
}

// --- generation --------------------------------------------------------------

let callsUsed = 0;

async function generateImage(apiKey, prompt, label) {
  for (let attempt = 1; attempt <= 2; attempt++) {
    if (callsUsed >= MAX_CALLS) throw new Error(`budget of ${MAX_CALLS} image calls exhausted`);
    callsUsed++;
    const start = Date.now();
    const res = await fetch("https://api.openai.com/v1/images/generations", {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({
        model: "gpt-image-1",
        prompt,
        size: "1024x1024", // every render surface (portrait plate, cover) is square
        quality: "medium",
        output_format: "jpeg",
        output_compression: 85, // afar_music's proven setting: ~300-500KB per image
      }),
    });
    if (!res.ok) {
      const body = await res.text();
      const detail = `${res.status} ${body.slice(0, 300)}`;
      if (attempt < 2 && (res.status === 429 || res.status >= 500)) {
        console.warn(`image  ${label}: transient ${res.status}, retrying once`);
        await new Promise((r) => setTimeout(r, 5000));
        continue;
      }
      throw new Error(`gpt-image-1 failed for ${label}: ${detail}`);
    }
    const json = await res.json();
    const b64 = json.data?.[0]?.b64_json;
    if (!b64) throw new Error(`gpt-image-1 returned no image data for ${label}`);
    console.log(`image  ${label}: generated in ${Math.round((Date.now() - start) / 1000)}s`);
    return Buffer.from(b64, "base64");
  }
  throw new Error(`unreachable`);
}

// --- storage -----------------------------------------------------------------

async function storeMedia(sql, bytes) {
  const id = createHash("sha256").update(bytes).digest("hex");
  await sql.query(
    `INSERT INTO media (id, content_type, bytes) VALUES ($1, $2, decode($3, 'hex'))
     ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, bytes = EXCLUDED.bytes`,
    [id, "image/jpeg", bytes.toString("hex")],
  );
  return id;
}

async function mediaExists(sql, url) {
  if (!url?.startsWith("/api/media/")) return false;
  const id = url.slice("/api/media/".length);
  const rows = await sql.query("SELECT 1 FROM media WHERE id = $1", [id]);
  return rows.length > 0;
}

async function setJsonField(sql, table, id, field, value) {
  await sql.query(
    `UPDATE ${table} SET data = jsonb_set(data, $2::text[], to_jsonb($3::text), true) WHERE id = $1`,
    [id, `{${field}}`, value],
  );
}

/** Keep the checked-in fixtures carrying the same URLs (fixture mode parity). */
function updateFixture(file, mutate) {
  const p = path.join(WEB_ROOT, "fixtures", file);
  const rows = JSON.parse(readFileSync(p, "utf8"));
  mutate(rows);
  writeFileSync(p, JSON.stringify(rows, null, 2) + "\n");
}

// --- main --------------------------------------------------------------------

async function main() {
  const forceArg = process.argv.includes("--force")
    ? (process.argv[process.argv.indexOf("--force") + 1] ?? "all")
    : "";
  const forced = new Set(forceArg === "all" ? [...PLAYER_IDS, "cover"] : forceArg.split(",").filter(Boolean));

  const apiKey = loadEnv("OPENAI_API_KEY");
  const sql = neon(loadEnv("DATABASE_URL"));

  const agents = JSON.parse(readFileSync(path.join(WEB_ROOT, "fixtures", "agents.json"), "utf8"));
  const releases = JSON.parse(readFileSync(path.join(WEB_ROOT, "fixtures", "releases.json"), "utf8"));
  const release = releases.find((r) => r.id === RELEASE_ID);
  if (!release) throw new Error(`release ${RELEASE_ID} not found in fixtures`);

  let intents = intentsFromRuns();
  if (PLAYER_IDS.some((p) => !intents.has(p))) intents = new Map([...(await intentsFromDb(sql)), ...intents]);

  const urls = new Map(); // slot -> /api/media/<id>

  // Portraits.
  for (const playerId of PLAYER_IDS) {
    const agent = agents.find((a) => a.id === playerId);
    const dbRow = await sql.query("SELECT data->>'imageUrl' AS url FROM agents WHERE id = $1", [playerId]);
    const current = dbRow[0]?.url;
    if (!forced.has(playerId) && current && (await mediaExists(sql, current))) {
      console.log(`skip   ${playerId}: portrait already at ${current}`);
      urls.set(playerId, current);
      continue;
    }
    const prompt = portraitPrompt(agent, intents.get(playerId));
    const bytes = await generateImage(apiKey, prompt, playerId);
    const id = await storeMedia(sql, bytes);
    const url = `/api/media/${id}`;
    await setJsonField(sql, "agents", playerId, "imageUrl", url);
    urls.set(playerId, url);
    console.log(`stored ${playerId}: ${url} (${bytes.length} bytes)`);
  }

  // Cover.
  {
    const dbRow = await sql.query("SELECT data->>'coverUrl' AS url FROM releases WHERE id = $1", [RELEASE_ID]);
    const current = dbRow[0]?.url;
    if (!forced.has("cover") && current && (await mediaExists(sql, current))) {
      console.log(`skip   cover: already at ${current}`);
      urls.set("cover", current);
    } else {
      const bytes = await generateImage(apiKey, coverPrompt(release), "cover");
      const id = await storeMedia(sql, bytes);
      const url = `/api/media/${id}`;
      await setJsonField(sql, "releases", RELEASE_ID, "coverUrl", url);
      urls.set("cover", url);
      console.log(`stored cover: ${url} (${bytes.length} bytes)`);
    }
  }

  // Fixtures mirror the same URLs.
  updateFixture("agents.json", (rows) => {
    for (const a of rows) if (urls.has(a.id)) a.imageUrl = urls.get(a.id);
  });
  updateFixture("releases.json", (rows) => {
    for (const r of rows) if (r.id === RELEASE_ID) r.coverUrl = urls.get("cover");
  });
  console.log("fixtures updated");

  // Verify what the site will read back.
  const agentRows = await sql.query("SELECT id, data->>'imageUrl' AS url FROM agents WHERE data->>'imageUrl' IS NOT NULL ORDER BY id");
  const releaseRows = await sql.query("SELECT id, data->>'coverUrl' AS url FROM releases ORDER BY id");
  const mediaRows = await sql.query("SELECT id, content_type, length(bytes) AS n FROM media WHERE content_type LIKE 'image/%' ORDER BY id");
  console.log("\nverify:");
  for (const a of agentRows) console.log(`  agent ${a.id} -> ${a.url}`);
  for (const r of releaseRows) console.log(`  release ${r.id} -> ${r.url}`);
  for (const m of mediaRows) console.log(`  media ${m.id.slice(0, 12)}… ${m.content_type} ${m.n} bytes`);
  console.log(`\n${callsUsed} image call(s) used`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
