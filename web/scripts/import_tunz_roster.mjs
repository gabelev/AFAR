/**
 * Import the tunz roster into Neon: every artist becomes an AFAR act with a
 * back catalogue — agents rows (bio, palette, portrait, cover, resident
 * metadata), tracks rows for the three album mp3s, and content-addressed
 * media bytes. Vess Camber (authored, design canon) joins with no catalogue.
 *
 * Sources of truth:
 *   - kernel/afar/agents/roster/<id>.json — the compiled+reviewed persona
 *     entries (stance, role word, descriptor, building, origin)
 *   - <tunz fixtures>/<id>/{profile.json,dna.json,portrait.png,cover.png,
 *     track-{1,2,3}.mp3} — bios, album facts, media bytes
 *     (default ../../ai-music/tunz/fixtures; override AFAR_TUNZ_FIXTURES)
 *
 * Deliberate shape decisions (see PR body):
 *   - NO rows are written to the releases table. Import albums are not
 *     sessions; a T-<slug> row would either break the deployed ReleaseSchema
 *     parse (voiding ALL live releases to fixtures) or force fake staff
 *     prose. The album lives on the agent row (data.album) and the tracks'
 *     releaseId points at the album id `T-<slug>`.
 *   - Media is content-addressed by sha256 (seed.mjs pattern), uploaded in
 *     1MB chunks so multi-MB portraits fit the HTTP driver comfortably.
 *
 * Idempotent: CREATE TABLE IF NOT EXISTS + upserts keyed on id; media
 * skipped when the hash row already carries the right byte length.
 *
 * Usage (from web/):  node scripts/import_tunz_roster.mjs [--verify-only]
 * DATABASE_URL is read from the environment, falling back to kernel/.env.
 * Nothing secret is ever printed.
 */

import { neon } from "@neondatabase/serverless";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const ROSTER_DIR = path.join(REPO_ROOT, "kernel", "afar", "agents", "roster");
const TUNZ_DIR =
  process.env.AFAR_TUNZ_FIXTURES ??
  path.resolve(REPO_ROOT, "..", "ai-music", "tunz", "fixtures");

// --- env ---------------------------------------------------------------------

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

// --- mp3 duration (no ffprobe on this box; Xing header, CBR fallback) --------

const BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320];
const BITRATES_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160];

function mp3DurationSec(buf) {
  let off = 0;
  if (buf.length > 10 && buf.toString("latin1", 0, 3) === "ID3") {
    const size =
      ((buf[6] & 0x7f) << 21) | ((buf[7] & 0x7f) << 14) | ((buf[8] & 0x7f) << 7) | (buf[9] & 0x7f);
    off = 10 + size;
  }
  while (off < buf.length - 4 && !(buf[off] === 0xff && (buf[off + 1] & 0xe0) === 0xe0)) off++;
  if (off >= buf.length - 4) return null;
  const b1 = buf[off + 1];
  const b2 = buf[off + 2];
  const b3 = buf[off + 3];
  const isV1 = ((b1 >> 3) & 3) === 3;
  const srIdx = (b2 >> 2) & 3;
  const srTable = isV1 ? [44100, 48000, 32000] : ((b1 >> 3) & 3) === 2 ? [22050, 24000, 16000] : [11025, 12000, 8000];
  const sampleRate = srTable[srIdx];
  const bitrate = (isV1 ? BITRATES_V1_L3 : BITRATES_V2_L3)[(b2 >> 4) & 0xf] * 1000;
  if (!sampleRate || !bitrate) return null;
  const samplesPerFrame = isV1 ? 1152 : 576;
  const channelMode = (b3 >> 6) & 3;
  const sideInfo = isV1 ? (channelMode === 3 ? 17 : 32) : channelMode === 3 ? 9 : 17;
  const tagOff = off + 4 + sideInfo;
  const tag = buf.toString("latin1", tagOff, tagOff + 4);
  if ((tag === "Xing" || tag === "Info") && buf.length > tagOff + 12) {
    const flags = buf.readUInt32BE(tagOff + 4);
    if (flags & 1) {
      const frames = buf.readUInt32BE(tagOff + 8);
      return Math.max(1, Math.round((frames * samplesPerFrame) / sampleRate));
    }
  }
  return Math.max(1, Math.round(((buf.length - off) * 8) / bitrate));
}

// --- content-addressed chunked media upload ----------------------------------

const CHUNK = 1 << 20; // 1MB of bytes -> 2MB hex per statement

async function uploadMedia(sql, bytes, contentType) {
  const hash = createHash("sha256").update(bytes).digest("hex");
  const existing = await sql.query("SELECT length(bytes) AS n FROM media WHERE id = $1", [hash]);
  if (existing.length > 0 && Number(existing[0].n) === bytes.length) return { hash, skipped: true };
  await sql.query(
    `INSERT INTO media (id, content_type, bytes) VALUES ($1, $2, decode($3, 'hex'))
     ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, bytes = EXCLUDED.bytes`,
    [hash, contentType, bytes.subarray(0, CHUNK).toString("hex")],
  );
  for (let o = CHUNK; o < bytes.length; o += CHUNK) {
    await sql.query("UPDATE media SET bytes = bytes || decode($2, 'hex') WHERE id = $1", [
      hash,
      bytes.subarray(o, o + CHUNK).toString("hex"),
    ]);
  }
  return { hash, skipped: false };
}

// --- main --------------------------------------------------------------------

async function main() {
  const verifyOnly = process.argv.includes("--verify-only");
  const sql = neon(loadDatabaseUrl());

  const entries = readdirSync(ROSTER_DIR)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .map((f) => JSON.parse(readFileSync(path.join(ROSTER_DIR, f), "utf8")));
  if (entries.length === 0) throw new Error(`no roster entries found in ${ROSTER_DIR}`);

  await sql.query(
    "CREATE TABLE IF NOT EXISTS media (id text PRIMARY KEY, content_type text NOT NULL, bytes bytea NOT NULL)",
  );
  for (const table of ["agents", "tracks"]) {
    await sql.query(
      `CREATE TABLE IF NOT EXISTS ${table} (id text PRIMARY KEY, data jsonb NOT NULL)`,
    );
  }

  const upsertJson = async (table, id, data) => {
    await sql.query(
      `INSERT INTO ${table} (id, data) VALUES ($1, $2::jsonb)
       ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data`,
      [id, JSON.stringify(data)],
    );
  };

  let agentCount = 0;
  let trackCount = 0;
  for (const entry of entries) {
    const slug = entry.player_id;
    const srcDir =
      entry.origin === "tunz"
        ? path.join(TUNZ_DIR, slug)
        : path.join(REPO_ROOT, "kernel", "afar", "agents", "roster_src", slug);
    const profile = JSON.parse(readFileSync(path.join(srcDir, "profile.json"), "utf8"));

    if (verifyOnly) continue;

    // media: portrait + cover (content-addressed; absent for authored acts)
    let imageUrl = null;
    let coverUrl = null;
    const portraitPath = path.join(srcDir, "portrait.png");
    const coverPath = path.join(srcDir, "cover.png");
    if (existsSync(portraitPath)) {
      const { hash, skipped } = await uploadMedia(sql, readFileSync(portraitPath), "image/png");
      imageUrl = `/api/media/${hash}`;
      console.log(`media   ${slug} portrait ${hash.slice(0, 12)}…${skipped ? " (kept)" : ""}`);
    }
    if (existsSync(coverPath)) {
      const { hash, skipped } = await uploadMedia(sql, readFileSync(coverPath), "image/png");
      coverUrl = `/api/media/${hash}`;
      console.log(`media   ${slug} cover    ${hash.slice(0, 12)}…${skipped ? " (kept)" : ""}`);
    }

    const albumId = `T-${slug}`;
    const album = profile.album
      ? { id: albumId, title: profile.album.title, description: profile.album.description }
      : undefined;

    // agents row — every field the DEPLOYED AgentSchema requires is present,
    // so production keeps parsing the moment the row lands.
    await upsertJson("agents", slug, {
      id: slug,
      kind: "player",
      name: entry.name,
      displayName: entry.display_name,
      role: `Act — ${entry.role_word}`,
      stance: entry.stance,
      description: [profile.bio],
      bio: profile.bio,
      palette: entry.palette,
      imageUrl,
      coverUrl,
      genreLine: entry.genre_line,
      descriptor: entry.descriptor,
      resident: { origin: entry.origin, building: entry.building ?? null },
      ...(album ? { album } : {}),
    });
    agentCount++;

    // tracks: the back catalogue (release-shaped id, no releases row)
    const tracks = profile.tracks ?? [];
    for (let i = 0; i < tracks.length; i++) {
      const mp3Path = path.join(srcDir, `track-${i + 1}.mp3`);
      if (!existsSync(mp3Path)) continue;
      const bytes = readFileSync(mp3Path);
      const { hash, skipped } = await uploadMedia(sql, bytes, "audio/mpeg");
      const durationSec = mp3DurationSec(bytes);
      await upsertJson("tracks", `${albumId}-${i + 1}`, {
        id: `${albumId}-${i + 1}`,
        releaseId: albumId,
        agentId: slug,
        title: tracks[i].title,
        durationSec,
        audioUrl: `/api/media/${hash}`,
        // provenance (data.ts strips unknown keys)
        kind: "import",
        albumTitle: profile.album?.title,
        theme: tracks[i].theme,
        lyricSeed: tracks[i].lyricSeed,
      });
      trackCount++;
      console.log(
        `track   ${albumId}-${i + 1} "${tracks[i].title}" ${durationSec}s ${hash.slice(0, 12)}…${skipped ? " (kept)" : ""}`,
      );
    }
    console.log(`agent   ${slug} (${entry.display_name}) building=${entry.building ?? "in town"}`);
  }

  if (!verifyOnly) console.log(`\nupserted ${agentCount} agents, ${trackCount} tracks`);

  // Verify what the site will actually read back.
  const players = await sql.query(
    `SELECT id, data->>'displayName' AS name, data->'resident'->>'building' AS building,
            data->>'imageUrl' AS portrait
     FROM agents WHERE data->>'kind' = 'player' ORDER BY id`,
  );
  const trackRows = await sql.query(
    `SELECT count(*)::int AS n FROM tracks WHERE data->>'releaseId' LIKE 'T-%'`,
  );
  const mediaRows = await sql.query(
    "SELECT count(*)::int AS n, sum(length(bytes))::bigint AS bytes FROM media",
  );
  console.log("\nverify:");
  for (const p of players) {
    console.log(
      `  act ${p.id.padEnd(34)} ${String(p.name).padEnd(36)} ${p.building ?? "-"} ${p.portrait ? "portrait✓" : "no-portrait"}`,
    );
  }
  console.log(`  import tracks ${trackRows[0].n}`);
  console.log(`  media rows ${mediaRows[0].n} (${mediaRows[0].bytes} bytes total)`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
