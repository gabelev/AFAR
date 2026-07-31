/**
 * Portraits for the imported acts that arrived without one — plus Vess
 * Camber, the authored resident who never had a face.
 *
 * gpt-image-1 (the path generate_images.mjs proved out for the house acts)
 * renders one 1024×1536 PNG per act in the TUNZ cohort look: a hand-written
 * scene prompt in the same register as the existing tunz portraits
 * (fixtures/<id>/media.json imagePrompts.portrait), closed with the same
 * era-treatment clause — era tokens + the act's visualStyle keywords +
 * "Vertical 4:5 portrait framing."
 *
 * Bytes are written back to each act's fixture dir as portrait.png (so
 * import_tunz_roster.mjs stays idempotent and re-imports keep the face),
 * the prompt is recorded in the dir's media.json, and the same bytes land
 * in the Neon `media` table content-addressed by sha256, chunked at 1MB
 * (import_tunz_roster.mjs's pattern); agents rows get data.imageUrl.
 *
 * Idempotent: an act is only generated when its fixture dir has no
 * portrait.png; an existing portrait.png that never reached Neon is
 * uploaded without an API call. `--force slug[,slug]` (or `all`)
 * regenerates named acts. A hard budget of MAX_CALLS API calls caps spend.
 *
 * Usage (from web/):  node scripts/generate_portraits.mjs [--force all|slug,…]
 * OPENAI_API_KEY and DATABASE_URL come from the environment, falling back
 * to kernel/.env. Nothing secret is ever printed.
 */

import { neon } from "@neondatabase/serverless";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const ROSTER_DIR = path.join(REPO_ROOT, "kernel", "afar", "agents", "roster");
const TUNZ_DIR =
  process.env.AFAR_TUNZ_FIXTURES ?? path.resolve(REPO_ROOT, "..", "ai-music", "tunz", "fixtures");
const MAX_CALLS = 15; // total gpt-image-1 calls this run, retries included

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

// --- the TUNZ cohort era treatment (tunz lib/dna/mapping.ts ERA_TOKENS) ------

const ERA_TOKENS = {
  "far-past": ["ancient folk tradition", "pre-industrial acoustic", "modal melodies"],
  "1900s": ["early recording era", "78rpm mono", "parlor and ragtime sensibility"],
  "1950s": ["1950s production", "tube console warmth", "slapback echo"],
  "1960s": ["1960s production", "vintage tape recording", "live room energy"],
  "1970s": ["1970s analog production", "tape workflow", "vintage console"],
  "1980s": ["1980s production", "gated reverb drums", "analog synthesizers"],
  "1990s": ["1990s production", "sampler-based workflow", "grunge-era rawness"],
  "2000s": ["2000s digital production", "polished radio mix", "early DAW sound"],
  "2010s": ["2010s production", "sidechain pumping", "maximalist digital mix"],
  "2020s": ["contemporary production", "modern streaming-era mix", "genre-fluid"],
  "near-future": ["futuristic production", "hyperreal sound design", "AI-age textures"],
  "far-future": ["alien sound palette", "post-human sound design", "unheard timbres"],
};

/** The clause every existing tunz portrait prompt closes with. */
function eraTreatment(dna) {
  const tokens = (ERA_TOKENS[dna.era] ?? ERA_TOKENS["2020s"]).join(", ");
  return `Visual treatment consistent with: ${tokens}. Aesthetic keywords: ${dna.visualStyle.join(", ")}. Vertical 4:5 portrait framing.`;
}

// --- the scenes: one per faceless act, written from DNA seedPrompt + bio -----
// Same voice as the shipped cohort (see fixtures/<id>/media.json): a concrete
// 4:5 scene, era-appropriate dress and light, a named photographic/print
// treatment, an expression, and always "no text".

const SCENES = {
  "assembly-ghost":
    "A 4:5 portrait of a lone young man in a decommissioned 1980s Detroit auto plant at night, standing behind a Roland drum machine and two secondhand synthesizers set up on a steel workbench, extension cords snaking across the concrete floor. Work jacket over grease-stained trousers, pale face half-lit by a single caged work lamp, assembly-line conveyors receding into darkness behind him. Near-monochrome industrial palette, cold blue-grey light, grainy 35mm photojournalism aesthetic, solemn faraway expression, no text, not a real person.",
  "fren-l-ge":
    "A 4:5 portrait of a reclusive young woman singer inside the lamp room of a stone lighthouse on the Baltic coast, wrapped in a heavy wool fisherman's sweater, one hand on the dial of an old shortwave radio, fog pressing against the glass behind her. Grainy monochrome coastal atmosphere, the lighthouse beam smearing through mist, rust streaks on iron fittings, smoky diffuse light, cinematic film grain, melancholic guarded expression, no text.",
  hohlraum:
    "A 4:5 portrait of an androgynous recluse in a cavernous brutalist water tower in Berlin, hooded dark workwear, face half-lost in shadow, standing among iron pipes fitted with contact microphones, cables running down to a small tape machine on a concrete ledge. Dripping raw concrete walls, vast grayscale gloom, one shaft of cold light from a slit window, the reverberant scale of the space filling the frame, grainy low-resolution documentary-photograph aesthetic, no text.",
  "hollis-wren-the-blacklung-choir":
    "A 4:5 portrait of a young Appalachian woman singer holding a clawhammer banjo, dressed in black funeral lace, standing before a shuttered coal-mine entrance in a West Virginia hollow at dusk, a small funeral band with lanterns softly blurred behind her, high-tension power lines crossing the sky overhead. Sepia-toned vintage-tintype photographic treatment, lantern glow on her face, coal dust hanging in the air, solemn high-lonesome expression, no text.",
  "marlow-vane":
    "A 4:5 portrait of a smooth young R&B singer in a silk bomber jacket standing on rain-slick pavement at night, collar up, eyes low, neon signs and streetlights smearing into reflections around him, a hotel lounge glowing out of focus behind. Velvet blues, magentas and sodium ambers on wet asphalt, cinematic shallow depth of field, glossy modern music-video photography, wistful late-night expression, no text.",
  "nite-route":
    "A 4:5 portrait of a young South London woman producer alone on the empty top deck of a night bus at 3am, laptop balanced on her knees, large headphones on, hood up, face lit only by the screen. Sodium-orange and neon light smeared across the fogged windows behind her, faint glitching answering-machine text ghosted in the window reflections, cold desaturated tones with electric highlights, grainy handheld night photography, absorbed distant expression, no text.",
  "ore-ashes":
    "A 4:5 portrait of a desert rock trio — a woman guitarist-vocalist flanked by a bassist and a drummer-mechanic — standing before a shuttered maintenance garage in a dying Arizona copper town, amps wired to a diesel generator beside them. Grease-stained denim and work shirts, heat shimmer rising off the empty highway behind, sun-bleached haze, rust and chrome textures, harsh overexposed afternoon light, gritty film photography, defiant squinting expressions, no text.",
  "systurj-kull":
    "A 4:5 portrait of a post-rock duo — two adult Icelandic women in their late thirties, bandmates — standing far apart on a vast receding glacier beneath an ice cap, weathered expedition parkas, wind-blown hair, one holding a field-recording cable that disappears into a blue crevasse at their feet. Vast monochrome ice field, pale northern light haze softening the horizon, muted whites and glacial blues, medium-format film stillness, quiet resolute expressions, no text, not real people.",
  "the-pier-lights":
    "A 4:5 portrait of an indie-pop four-piece in their twenties — two guitarists, a bassist and a drummer — leaning against a weathered boardwalk railing in a sunny beach town, one cradling a twelve-string electric guitar, faded pastel beach huts and a pier behind them. Sun-bleached coastal film photography, warm faded-postcard colors, light leaks and soft grain, salt-worn denim and tees, easy nostalgic grins caught mid-laugh, no text.",
  "twin-signal":
    "A 4:5 portrait of a synchronized electropop duo — a man and a woman in matching sharply tailored monochrome stage outfits — frozen mid-choreography in perfect mirror-image poses on a glossy arena stage. Strictly symmetrical composition, twin spotlight beams and LED panels behind them, high-gloss reflections on the stage floor, crisp editorial pop photography, confident direct gazes, immaculate styling, no text.",
  "velvet-nadia":
    "A 4:5 portrait of a glamorous disco-revival singer in a sequined gown standing alone on an empty club dancefloor at closing time, gazing up at a slowly spinning mirrorball that scatters flecks of light across her face and the floor. Retro disco neon in magenta and gold at the edges of the frame, glittering yet melancholy atmosphere, soft haze, cinematic shallow focus, a sad half-smile beneath the glamour, no text.",
  vess:
    "A 4:5 portrait of a quiet bedroom producer wearing a soft flat cap, seated at a single mixing console in a small rented room at night, one amp beside them and crates of borrowed records stacked against the wall, an addressed unsealed envelope resting on top of the amp. The whole room washed in muted violet — console glow and one small lamp the only light. Warm lo-fi intimacy, gentle film grain, cassette-era clutter, face half-turned and half-shadowed under the cap brim, unguarded thoughtful expression, no text.",
};

// --- generation (generate_images.mjs's proven path; portrait-tall like tunz) --

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
        size: "1024x1536", // the tunz cohort's portrait aspect
        quality: "medium",
        output_format: "png", // matches the existing fixture portrait.png files
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
  throw new Error("unreachable");
}

// --- content-addressed chunked upload (import_tunz_roster.mjs's pattern) -----

const CHUNK = 1 << 20;

async function uploadMedia(sql, bytes) {
  const hash = createHash("sha256").update(bytes).digest("hex");
  const existing = await sql.query("SELECT length(bytes) AS n FROM media WHERE id = $1", [hash]);
  if (existing.length > 0 && Number(existing[0].n) === bytes.length) return { hash, skipped: true };
  await sql.query(
    `INSERT INTO media (id, content_type, bytes) VALUES ($1, $2, decode($3, 'hex'))
     ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, bytes = EXCLUDED.bytes`,
    [hash, "image/png", bytes.subarray(0, CHUNK).toString("hex")],
  );
  for (let o = CHUNK; o < bytes.length; o += CHUNK) {
    await sql.query("UPDATE media SET bytes = bytes || decode($2, 'hex') WHERE id = $1", [
      hash,
      bytes.subarray(o, o + CHUNK).toString("hex"),
    ]);
  }
  return { hash, skipped: false };
}

/** Record the prompt next to the bytes, like the shipped cohort's media.json. */
function recordPrompt(srcDir, prompt) {
  const p = path.join(srcDir, "media.json");
  const current = existsSync(p) ? JSON.parse(readFileSync(p, "utf8")) : {};
  current.imagePrompts = { ...(current.imagePrompts ?? {}), portrait: prompt };
  writeFileSync(p, JSON.stringify(current, null, 2) + "\n");
}

// --- main --------------------------------------------------------------------

async function main() {
  const forceArg = process.argv.includes("--force")
    ? (process.argv[process.argv.indexOf("--force") + 1] ?? "all")
    : "";
  const slugs = Object.keys(SCENES);
  const forced = new Set(forceArg === "all" ? slugs : forceArg.split(",").filter(Boolean));

  const apiKey = loadEnv("OPENAI_API_KEY");
  const sql = neon(loadEnv("DATABASE_URL"));

  for (const slug of slugs) {
    const entry = JSON.parse(readFileSync(path.join(ROSTER_DIR, `${slug}.json`), "utf8"));
    const srcDir =
      entry.origin === "tunz"
        ? path.join(TUNZ_DIR, slug)
        : path.join(REPO_ROOT, "kernel", "afar", "agents", "roster_src", slug);
    const dna = JSON.parse(readFileSync(path.join(srcDir, "dna.json"), "utf8"));
    const portraitPath = path.join(srcDir, "portrait.png");

    let bytes;
    if (existsSync(portraitPath) && !forced.has(slug)) {
      bytes = readFileSync(portraitPath); // already generated: re-upload only if Neon lost it
    } else {
      const prompt = `${SCENES[slug]}\n\n${eraTreatment(dna)}`;
      bytes = await generateImage(apiKey, prompt, slug);
      writeFileSync(portraitPath, bytes);
      recordPrompt(srcDir, prompt);
      console.log(`wrote  ${path.relative(REPO_ROOT, portraitPath)} (${bytes.length} bytes)`);
    }

    const { hash, skipped } = await uploadMedia(sql, bytes);
    const url = `/api/media/${hash}`;
    await sql.query(
      `UPDATE agents SET data = jsonb_set(data, '{imageUrl}', to_jsonb($2::text), true) WHERE id = $1`,
      [slug, url],
    );
    console.log(`stored ${slug}: ${url}${skipped ? " (media kept)" : ""}`);
  }

  // Verify what the site will read back.
  const players = await sql.query(
    `SELECT id, data->>'imageUrl' AS url FROM agents WHERE data->>'kind' = 'player' ORDER BY id`,
  );
  console.log("\nverify:");
  let missing = 0;
  for (const p of players) {
    if (!p.url) missing++;
    console.log(`  act ${p.id.padEnd(34)} ${p.url ? `portrait ${p.url.slice(11, 23)}…` : "NO PORTRAIT"}`);
  }
  console.log(`\n${players.length} acts, ${missing} without portraits; ${callsUsed} image call(s) used`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
