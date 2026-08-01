/**
 * Regenerate web/world-sprites.json — the committed sprite/tenant spec for
 * every IMPORT resident (origin "tunz"): slug → { accent, accentD, chest,
 * hair, head, prop }, deterministically derived from the roster's Creative
 * DNA by scripts/lib/dna.mjs. Vess Camber (origin "design") is authored in
 * the handoff and never appears here.
 *
 * The registry's spriteOrder appends these slugs (sorted) after the
 * designed 8; render_pixels.mjs turns each entry into a spritesheet row
 * via scripts/lib/spritegen.mjs. Deterministic: same roster in, identical
 * file out. Re-run whenever the roster (or the derivation) changes:
 *   node scripts/generate_resident_sprites.mjs
 */

import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { residentLook } from "./lib/dna.mjs";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROSTER_DIR = path.resolve(WEB_ROOT, "..", "kernel", "afar", "agents", "roster");
const OUT = path.join(WEB_ROOT, "world-sprites.json");

const entries = readdirSync(ROSTER_DIR)
  .filter((f) => f.endsWith(".json"))
  .sort()
  .map((f) => JSON.parse(readFileSync(path.join(ROSTER_DIR, f), "utf8")))
  .filter((e) => e.origin === "tunz");

const spec = {};
for (const entry of entries) {
  const look = residentLook(entry.player_id, entry.palette);
  spec[entry.player_id] = Object.fromEntries(
    Object.keys(look)
      .sort()
      .map((k) => [k, look[k]]),
  );
}

writeFileSync(OUT, JSON.stringify(spec, null, 2) + "\n");
console.log(`world-sprites.json — ${Object.keys(spec).length} import residents`);
