/**
 * Staff press photos — GENERATED, not pre-made. The three acts' photos came
 * finished from the design handoff; the four staff (producer / critic /
 * listener / muse) get photos rendered here from their authoritative 16×16
 * sprite maps (scripts/lib/pixelspec.mjs), in the act-photo register but
 * QUIETER: staff grey palette, office backdrop (flat wall + floorboard
 * bands from PAL), film grain, and the archival paper caption strip
 * (Archivo bold + IBM Plex Mono, chip + NAME · ROLE + one-decision line).
 *
 * 960×1200, same frame as the act photos. Regenerate whenever the sprite
 * maps change — the figure IS the world sprite, big.
 *
 * Publishing mirrors scripts/press_photos.mjs exactly: PNGs are written to
 * web/public/press/ (the static fallback), uploaded to the Neon media
 * table content-addressed by sha256, agents rows get data.imageUrl, and
 * fixtures/agents.json is rewritten to carry the same URLs (fixture mode
 * 404s them and falls back to the identical /press/ file).
 *
 * Usage (from web/):  node scripts/press_photos_staff.mjs [--skip-db]
 * DATABASE_URL is read from the environment, falling back to kernel/.env.
 * Nothing secret is ever printed.
 */

import { createCanvas, registerFont } from 'canvas';
import { neon } from '@neondatabase/serverless';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { PAL, S } from './lib/pixelspec.mjs';

const SCRIPTS = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPTS, '..');
const REPO_ROOT = path.resolve(WEB_ROOT, '..');
const FONTS = path.join(SCRIPTS, 'assets', 'fonts');

registerFont(path.join(FONTS, 'Archivo-Bold.ttf'), { family: 'Archivo', weight: 'bold' });
registerFont(path.join(FONTS, 'Archivo-Regular.ttf'), { family: 'Archivo' });
registerFont(path.join(FONTS, 'IBMPlexMono-Regular.ttf'), { family: 'IBM Plex Mono' });
registerFont(path.join(FONTS, 'IBMPlexMono-Medium.ttf'), { family: 'IBM Plex Mono', weight: '500' });
registerFont(path.join(FONTS, 'IBMPlexMono-Italic.ttf'), { family: 'IBM Plex Mono', style: 'italic' });

/**
 * Caption copy. NAME · ROLE mirror the agents rows ("Staff — selection" →
 * SELECTION); the one-decision line says, in plain language, the one thing
 * this staff member decides (web plain-language rule).
 */
export const STAFF_PHOTOS = {
  producer: {
    sprite: 'producer',
    role: 'SELECTION',
    decision: 'Decides what a session should sound like, and which recordings surface.',
  },
  critic: {
    sprite: 'critic',
    role: 'JUDGMENT',
    decision: 'Decides whether a release was any good, and what it is called.',
  },
  listener: {
    sprite: 'listener',
    role: 'RECEPTION',
    decision: 'Decides nothing. Hears every release from the cheap seats, and is moved or not.',
  },
  muse: {
    sprite: 'muse',
    role: 'DIRECTION',
    decision: 'Decides what the outside world sounds like this week, and dares the acts to answer.',
  },
};

const NAME = { producer: 'THE PRODUCER', critic: 'THE CRITIC', listener: 'THE LISTENER', muse: 'THE MUSE' };

const PHOTO_W = 960, PHOTO_H = 1200;
const STRIP_Y = 1030; // paper caption strip starts here (act-photo register)
const FLOOR_Y = 640; // wall / floorboard split

/** Deterministic PRNG (mulberry32) so re-runs are byte-identical per staff id. */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function drawSpaced(c, text, x, y, spacing) {
  let cx = x;
  for (const ch of text) {
    c.fillText(ch, cx, y);
    cx += c.measureText(ch).width + spacing;
  }
  return cx - spacing - x;
}
export function renderStaffPhoto(staffId) {
  const spec = STAFF_PHOTOS[staffId];
  const map = S[spec.sprite].down;
  const cv = createCanvas(PHOTO_W, PHOTO_H);
  const c = cv.getContext('2d');
  c.imageSmoothingEnabled = false;

  // — office backdrop: flat wall, then floorboard bands, all from PAL —
  c.fillStyle = PAL.wallFace;
  c.fillRect(0, 0, PHOTO_W, FLOOR_Y);
  c.fillStyle = PAL.floor;
  c.fillRect(0, FLOOR_Y, PHOTO_W, STRIP_Y - FLOOR_Y);
  c.fillStyle = PAL.floorD;
  for (let y = FLOOR_Y + 56; y < STRIP_Y; y += 56) c.fillRect(0, y, PHOTO_W, 3);
  c.fillStyle = PAL.ink;
  c.fillRect(0, FLOOR_Y - 3, PHOTO_W, 3);

  // quiet light: a soft centre lift and a vignette (radial gradients)
  let g = c.createRadialGradient(480, 430, 0, 480, 430, 760);
  g.addColorStop(0, 'rgba(214,207,188,0.09)');
  g.addColorStop(1, 'rgba(214,207,188,0)');
  c.fillStyle = g; c.fillRect(0, 0, PHOTO_W, STRIP_Y);
  g = c.createRadialGradient(480, 470, 320, 480, 470, 860);
  g.addColorStop(0, 'rgba(10,11,13,0)');
  g.addColorStop(1, 'rgba(10,11,13,0.42)');
  c.fillStyle = g; c.fillRect(0, 0, PHOTO_W, STRIP_Y);

  // — the figure: the 16×16 world sprite, scaled up nearest-neighbour —
  const SCALE = 56;
  let minX = 16, maxX = -1, maxY = -1;
  map.forEach((row, y) => row.split('').forEach((ch, x) => {
    if (ch !== '.') { minX = Math.min(minX, x); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); }
  }));
  const px = Math.round(PHOTO_W / 2 - ((minX + maxX + 1) / 2) * SCALE);
  const py = 900 - (maxY + 1) * SCALE;

  // drop shadow on the floorboards
  c.fillStyle = 'rgba(10,11,13,0.35)';
  c.beginPath();
  c.ellipse(PHOTO_W / 2, 902, ((maxX - minX + 1) * SCALE) / 2 + 24, 34, 0, 0, Math.PI * 2);
  c.fill();

  const dk = { o: PAL.ink, c: PAL.staff, d: PAL.staffD, s: PAL.skin, h: PAL.hair, p: PAL.paper, m: PAL.metal };
  map.forEach((row, y) => row.split('').forEach((ch, x) => {
    const col = dk[ch];
    if (col) { c.fillStyle = col; c.fillRect(px + x * SCALE, py + y * SCALE, SCALE, SCALE); }
  }));

  // — film grain (seeded per staff id, deterministic) —
  const rand = rng([...staffId].reduce((a, ch) => a * 31 + ch.charCodeAt(0), 7));
  for (let i = 0; i < 560; i++) {
    const x = Math.floor(rand() * PHOTO_W), y = Math.floor(rand() * STRIP_Y);
    const light = rand() > 0.25;
    c.fillStyle = light
      ? `rgba(214,207,188,${(0.18 + rand() * 0.35).toFixed(3)})`
      : `rgba(10,11,13,${(0.2 + rand() * 0.3).toFixed(3)})`;
    c.fillRect(x, y, 2, 2);
  }

  // — archival paper caption strip —
  c.fillStyle = '#ddd6c4';
  c.fillRect(0, STRIP_Y, PHOTO_W, PHOTO_H - STRIP_Y);

  // chip + NAME · ROLE (Archivo bold, letterspaced)
  c.fillStyle = PAL.staff;
  c.fillRect(46, 1066, 22, 22);
  c.fillStyle = '#1c1a15';
  c.font = 'bold 40px Archivo';
  let x = 86;
  x += drawSpaced(c, NAME[staffId], x, 1092, 6) + 24;
  x += drawSpaced(c, '·', x, 1092, 0) + 24;
  drawSpaced(c, spec.role, x, 1092, 6);

  // the one-decision line (plain language), mono italic, wrapped to the strip
  c.fillStyle = '#4a463c';
  c.font = 'italic 20px "IBM Plex Mono"';
  const words = spec.decision.split(' ');
  const lines = [''];
  for (const w of words) {
    const probe = lines[lines.length - 1] ? `${lines[lines.length - 1]} ${w}` : w;
    if (c.measureText(probe).width > PHOTO_W - 92 && lines[lines.length - 1]) lines.push(w);
    else lines[lines.length - 1] = probe;
  }
  lines.forEach((line, i) => c.fillText(line, 46, 1126 + i * 26));

  // archive line, mono letterspaced
  c.fillStyle = '#5e5a4f';
  c.font = '500 18px "IBM Plex Mono"';
  drawSpaced(c, 'AFAR PRESS ARCHIVE · THE LABEL OFFICE · ERA 2020s', 46, 1178, 1.5);

  return cv.toBuffer('image/png', { compressionLevel: 9 });
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
  throw new Error('DATABASE_URL not set and not found in kernel/.env');
}

async function main() {
  const skipDb = process.argv.includes('--skip-db');
  const pressDir = path.join(WEB_ROOT, 'public', 'press');
  mkdirSync(pressDir, { recursive: true });

  const files = new Map(); // staff id -> {file, bytes, hash}
  for (const staffId of Object.keys(STAFF_PHOTOS)) {
    const bytes = renderStaffPhoto(staffId);
    const file = `press-${staffId}.png`;
    writeFileSync(path.join(pressDir, file), bytes);
    const hash = createHash('sha256').update(bytes).digest('hex');
    files.set(staffId, { file, bytes, hash });
    console.log(`press  ${staffId}: ${file} ${bytes.length} bytes -> ${hash.slice(0, 12)}…`);
  }
  if (skipDb) { console.log('(--skip-db: not touching Neon or fixtures)'); return; }

  const sql = neon(loadDatabaseUrl());
  await sql.query(
    'CREATE TABLE IF NOT EXISTS media (id text PRIMARY KEY, content_type text NOT NULL, bytes bytea NOT NULL)',
  );
  const urls = new Map();
  for (const [staffId, { file, bytes, hash }] of files) {
    await sql.query(
      `INSERT INTO media (id, content_type, bytes) VALUES ($1, $2, decode($3, 'hex'))
       ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, bytes = EXCLUDED.bytes`,
      [hash, 'image/png', bytes.toString('hex')],
    );
    const url = `/api/media/${hash}`;
    await sql.query(
      `UPDATE agents SET data = jsonb_set(data, '{imageUrl}', to_jsonb($2::text), true) WHERE id = $1`,
      [staffId, url],
    );
    urls.set(staffId, url);
    console.log(`media  ${staffId}: ${file} -> ${url}`);
  }

  // Fixtures mirror the same URLs (fixture mode 404s them and the static
  // /press/ file — identical bytes — takes over).
  const fixturePath = path.join(WEB_ROOT, 'fixtures', 'agents.json');
  const agents = JSON.parse(readFileSync(fixturePath, 'utf8'));
  for (const agent of agents) {
    if (urls.has(agent.id)) agent.imageUrl = urls.get(agent.id);
  }
  writeFileSync(fixturePath, JSON.stringify(agents, null, 2) + '\n');
  console.log('fixtures updated');

  const rows = await sql.query(
    "SELECT id, data->>'imageUrl' AS url FROM agents WHERE data->>'kind' = 'staff' ORDER BY id",
  );
  console.log('\nverify:');
  for (const r of rows) console.log(`  agent ${r.id} -> ${r.url}`);
  console.log('done.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((err) => { console.error(err.message); process.exit(1); });
}
