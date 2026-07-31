/**
 * Generate bios for the universe's seven inhabitants — one short paragraph
 * per act, one shorter one per staff member — and store them as `bio` in
 * fixtures/agents.json AND in the Neon agents rows (data jsonb).
 *
 * The bios are CONTENT, not chrome: profiles of artists living in this
 * universe (not record-label press copy — universe framing per Gabe,
 * 2026-07-31), in plain language a non-music person enjoys, grounded in what
 * is actually on the record — the acts' stances, their logged rationales, the
 * Critic's verdicts, the Producer's notes. Nothing is invented beyond that
 * record. Generated words get reviewed by a human before the fixtures are
 * committed (DECISIONS.md: bios generated + register).
 *
 * Usage (from web/):  node scripts/generate_bios.mjs [--dry-run]
 *   --dry-run prints the bios without writing fixtures or Neon.
 * ANTHROPIC_API_KEY and DATABASE_URL come from the environment, falling back
 * to kernel/.env. Nothing secret is ever printed.
 */

import Anthropic from "@anthropic-ai/sdk";
import { neon } from "@neondatabase/serverless";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const DRY_RUN = process.argv.includes("--dry-run");

// --- env ---------------------------------------------------------------------

function envFromKernel(name) {
  if (process.env[name]) return process.env[name];
  const envPath = path.join(REPO_ROOT, "kernel", ".env");
  if (existsSync(envPath)) {
    for (const raw of readFileSync(envPath, "utf8").split("\n")) {
      const line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      const eq = line.indexOf("=");
      if (eq === -1) continue;
      if (line.slice(0, eq).trim() === name) {
        return line.slice(eq + 1).trim().replace(/^['"]|['"]$/g, "");
      }
    }
  }
  throw new Error(`${name} not set and not found in kernel/.env`);
}

// --- grounding: what is actually on the record -------------------------------

/** Neon releases/tracks rows when reachable, fixtures otherwise. */
async function loadRecord(sql) {
  const fromTable = async (table, fixture) => {
    try {
      const rows = await sql.query(`SELECT data FROM ${table} ORDER BY id`);
      const list = (Array.isArray(rows) ? rows : (rows.rows ?? [])).map((r) => r.data);
      if (list.length > 0) return list;
    } catch {
      /* fall through to fixtures */
    }
    return JSON.parse(readFileSync(path.join(WEB_ROOT, "fixtures", fixture), "utf8"));
  };
  return {
    releases: await fromTable("releases", "releases.json"),
    tracks: await fromTable("tracks", "tracks.json"),
  };
}

function groundingFor(agent, agents, releases) {
  const lines = [
    `id: ${agent.id}`,
    `kind: ${agent.kind}`,
    `display name: ${agent.displayName ?? agent.name}`,
    `role: ${agent.role}`,
    `stance (their own words): "${agent.stance}"`,
    `current site description:\n${agent.description.join("\n")}`,
  ];
  for (const r of releases) {
    lines.push(`\n--- release ${r.id} "${r.title}" (set ${r.set}, era ${r.era}) ---`);
    if (agent.kind === "player") {
      if (r.rationales?.[agent.id]) lines.push(`their own words on their take: "${r.rationales[agent.id]}"`);
      if (r.reviews?.[agent.id]) lines.push(`the Critic's verdict on them: "${r.reviews[agent.id]}"`);
      const incoming = (r.influence ?? []).filter((e) => e.to === agent.id && e.from !== agent.id);
      if (incoming.length) {
        const names = Object.fromEntries(agents.map((a) => [a.id, a.displayName ?? a.name]));
        lines.push(
          `measured pull toward them: ${incoming.map((e) => `${names[e.from]} (${e.weight})`).join(", ")}`,
        );
      }
    } else {
      const pick = { muse: r.brief, producer: r.selection, critic: r.review, listener: r.reaction }[agent.id];
      if (pick) lines.push(`their work on this release: "${pick}"`);
    }
  }
  return lines.join("\n");
}

// --- generation --------------------------------------------------------------

const SYSTEM = `You write profiles for AFAR.MUSIC, a small universe where every musician is software. Three acts live there — Delta Marlowe, Roan Patina, Evers Lane — recording around the clock and hearing each other only on record. Four staff work in the office — the Muse, the Producer, the Critic, the Listener — and each makes exactly one kind of decision.

Register: a profile of an artist (or an office worker) living in this universe — warm, specific, a little wry, never corporate. This is NOT record-label press copy: never call AFAR "a label" or use record-industry framing ("signed", "roster", "the label"). The place is "the universe", "the world", or just AFAR; the staff work in "the office". The hard rule is CLARITY: a curious stranger with no music-production background and no AI background must enjoy every sentence on first read. No jargon of any kind — never say "multi-agent", "generative", "model", "parameters", "output", "sonic palette", "iteration". Words like song, take, record, session are fine. Do not mention that the bio (or the musician) was generated, and do not explain the AI mechanics — the site does that elsewhere.

Ground every claim in the record you are given: their stance, their own quoted words, what the Critic said, what actually happened in the sessions. Do not invent history, influences, hometowns, or humans — and do not describe instruments, sounds, or musical details unless they appear verbatim in the record. Short sentences beat long ones. Stay inside the sentence count you are given.`;

function promptFor(agent, grounding) {
  const isAct = agent.kind === "player";
  return `Write the press bio for ${agent.displayName ?? agent.name}.

${isAct
    ? "One paragraph, 3 to 5 sentences. This sits under their name at the top of their page — it should make a stranger want to press play."
    : "One paragraph, 2 to 3 sentences. This sits under their name on their page — it should tell a stranger exactly what this person does in the office."}

Return ONLY the paragraph — no title, no quotes around it, no commentary.

Here is everything on the record about them:

${grounding}`;
}

async function main() {
  const anthropic = new Anthropic({ apiKey: envFromKernel("ANTHROPIC_API_KEY") });
  const sql = neon(envFromKernel("DATABASE_URL"));

  const fixturesPath = path.join(WEB_ROOT, "fixtures", "agents.json");
  const agents = JSON.parse(readFileSync(fixturesPath, "utf8"));
  const { releases } = await loadRecord(sql);

  for (const agent of agents) {
    const response = await anthropic.messages.create({
      model: "claude-opus-5",
      max_tokens: 2000,
      system: SYSTEM,
      messages: [{ role: "user", content: promptFor(agent, groundingFor(agent, agents, releases)) }],
    });
    if (response.stop_reason === "refusal") throw new Error(`refusal for ${agent.id}`);
    const bio = response.content
      .filter((b) => b.type === "text")
      .map((b) => b.text)
      .join("")
      .trim();
    if (!bio) throw new Error(`empty bio for ${agent.id}`);
    agent.bio = bio;
    console.log(`\n== ${agent.displayName ?? agent.name} (${agent.id}) ==\n${bio}`);
  }

  if (DRY_RUN) {
    console.log("\n--dry-run: nothing written.");
    return;
  }

  // Fixtures: machine-canonical 2-space JSON, bio carried on each agent.
  writeFileSync(fixturesPath, JSON.stringify(agents, null, 2) + "\n");
  console.log(`\nfixtures ${path.relative(WEB_ROOT, fixturesPath)} updated`);

  // Neon: merge bio into each existing agents row (read-modify-write keeps
  // any fields the row has that fixtures do not).
  await sql.query("CREATE TABLE IF NOT EXISTS agents (id text PRIMARY KEY, data jsonb NOT NULL)");
  for (const agent of agents) {
    const rows = await sql.query("SELECT data FROM agents WHERE id = $1", [agent.id]);
    const existing = (Array.isArray(rows) ? rows : (rows.rows ?? []))[0]?.data ?? agent;
    await sql.query(
      `INSERT INTO agents (id, data) VALUES ($1, $2::jsonb)
       ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data`,
      [agent.id, JSON.stringify({ ...existing, bio: agent.bio })],
    );
  }
  console.log(`agents  ${agents.length} rows updated with bios`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
