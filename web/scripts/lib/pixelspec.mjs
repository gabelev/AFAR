/**
 * Port of design/handoff/pixel.js — the AUTHORITATIVE tile/sprite/palette
 * spec — for the build-time pipeline (render_pixels.mjs, press photos).
 *
 * The handoff says: port the data (palette, era LUT, sprite maps, room
 * grid/paint, era prop diffs) into real PNG assets; never ship pixel.js to
 * the client. This module is that port: identical pixel maps and painters,
 * adapted only where build needs differ from the design doc:
 *   - painters take a 2d context (node-canvas), not a <canvas> element;
 *   - paintWorld() can skip the people layer (characters ship as their own
 *     spritesheet and are placed by the Phaser scene at runtime);
 *   - sprite maps, frame expansion and prop painters are exported.
 *
 * When the design's pixel.js changes, re-sync this file and re-run
 * scripts/render_pixels.mjs (the determinism test guards the output).
 */

export const PAL = {
  void: '#0e1013', rain: '#1b2027',
  wallCap: '#1e2126', wallFace: '#4b4f57',
  conc: '#383b40', concD: '#33363b',
  floor: '#463d31', floorD: '#3c342a',
  rug: '#544130', rugD: '#463628',
  wood: '#5c4b37', woodD: '#443726',
  ink: '#16140f', paper: '#d6cfbc', paperD: '#a9a290',
  lamp: '#e0b25a', metal: '#6a6f78', metalD: '#43474e',
  glass: '#31404c', skin: '#c39a7d', hair: '#292319',
  staff: '#8b8577', staffD: '#5e5a4f',
  evers: '#a34c2e', eversD: '#6e3220',
  roan: '#71917d', roanD: '#4b6355',
  delta: '#bd9040', deltaD: '#7c5e2a',
};

/** Era B = the same world through a LUT: 8 entries remapped, everything else untouched. */
export function eraPal(era) {
  if (era !== 'B') return PAL;
  return Object.assign({}, PAL, {
    void: '#13100b', rain: '#13100b', glass: '#4d4026',
    floor: '#4b4033', floorD: '#403629', conc: '#3d3a33', concD: '#37342d',
    wallFace: '#55503f', lamp: '#d8a248',
  });
}

export const T = 16, W = 33, H = 34;

function P(c, x, y, w, h, col) { c.fillStyle = col; c.fillRect(x, y, w, h); }
function box(c, x, y, w, h, fill, edge) { P(c, x, y, w, h, edge); P(c, x + 1, y + 1, w - 2, h - 2, fill); }
function disc(c, cx, cy, r, col) {
  for (let dy = -r; dy <= r; dy++) {
    const w = Math.floor(Math.sqrt(r * r - dy * dy));
    P(c, cx - w, cy + dy, 2 * w + 1, 1, col);
  }
}
export function ring(c, cx, cy, r, col, step) {
  for (let a = 0; a < 360; a += step) {
    const x = Math.round(cx + r * Math.cos((a * Math.PI) / 180));
    const y = Math.round(cy + r * Math.sin((a * Math.PI) / 180));
    P(c, x, y, 1, 1, col);
  }
}

// ---- sprites: 16x16 maps. . none / o ink / c coat / d coat-dark / s skin / h hair / p paper / m metal
export const S = {
evers:{down:[
"................","......oooo......",".....odddddo....","...ooddddddoo...",
"....osssssso....","....osossoso....",".....osssso.....","....occccco.....",
"...occccccco....","...occcpccco....","...occcoccco....","...odccoccdo....",
"...odccoccdo....","...odcccccdo....","....oo...oo.....","................"],
side:[
"................","......oooo......",".....odddddo....","...ooddddddoo...",
"....osssso......","....ososso......",".....ossso......","....occcco......",
"....occccco.....","....ocdccco.....","....ocdccco.....","....ocdccco.....",
"....occccco.....","....odcccdo.....",".....oo.oo......","................"],
up:["................","......oooo......",".....odddddo....","...ooddddddoo...",
"....odddddo.....","....odddddo.....",".....odddo......","....occccco.....",
"...occccccco....","...occccccco....","...occccccco....","...odcccccdo....",
"...odcccccdo....","...odcccccdo....","....oo...oo.....","................"]},
roan:{down:[
"................","................","......ooo.......",".....occco......",
".....ocsso......",".....ososo......","......oss.......",".....occc.o.....",
".....occcco.....","......occo......",".....occ.co.....","......occo......",
"......oc.o......","......o..o......","......o..o......","................"],
side:[
"................","................","......ooo.......",".....occco......",
".....oscco......",".....oosco......","......oso.......",".....occ.o......",
".....occco......","......occo......",".....oc.co......","......occo......",
"......o.co......","......o..o......","......oo........","................"],
up:["................","................","......ooo.......",".....occco......",
".....occco......",".....occco......","......occ.......",".....occc.o.....",
".....occcco.....","......occo......",".....occ.co.....","......occo......",
"......oc.o......","......o..o......","......o..o......","................"]},
delta:{down:[
"................","................",".....ohhho......",".....ohhho......",
".....osssso.....",".....ososso.....","...oodddddoo....","..occcccccco....",
"..occdccdcco....","..occcccccco....","..odccccccdo....","..occcccccco....",
"..odccccccdo....","...occ..cco.....","...oo....oo.....","................"],
side:[
"................","................",".....ohhho......",".....ohhho......",
".....ossso......",".....oosso......","....occccoo.....","...occccccco....",
"...ocdccdcco....","...occccccco....","...odcccccdo....","...occccccco....",
"...odccccdo.....","....occ.cco.....","....oo...oo.....","................"],
up:["................","................",".....ohhho......",".....ohhho......",
".....ohhhho.....",".....ohhhho.....","...oocccccoo....","..occcccccco....",
"..occdccdcco....","..occcccccco....","..odccccccdo....","..occcccccco....",
"..odccccccdo....","...occ..cco.....","...oo....oo.....","................"]},
producer:{down:[
"................","................",".....oooo.......","....omhhmo......",
"....omssmo......",".....osso.......","....occcco......","...occcccco.....",
"...occcccco.....","...occcccco.....","....occcco......","....oo..oo......",
"................","................","................","................"]},
critic:{down:[
"................","................","......ohho......","......ohho......",
".....oomoo......","......osso......","......occo......","......occo......",
"....ppocco......","....ppocco......","......occo......","......o..o......",
"......o..o......","................","................","................"]},
listener:{down:[
"................","................","................","......ohho......",
".....ossso......",".....ososo......",".....occcco.....","....occcccco....",
"....occcccco....","....occcccco....",".....occcco.....",".....oo..oo.....",
"................","................","................","................"]},
muse:{down:[
"................","................",".....ohhho......","....ohhhhho.....",
"....ohsssho.....","....ohsssho.....",".....opppo......",".....opppo......",
".....opppo......",".....opppo......",".....opppo......",".....oo.oo......",
"................","................","................","................"]}
};

/** Colour dictionary for a character's map symbols (act accents never remap). */
export function dict(p, who) {
  const acc = { evers: [p.evers, p.eversD], roan: [p.roan, p.roanD], delta: [p.delta, p.deltaD] }[who] || [p.staff, p.staffD];
  return { o: p.ink, c: acc[0], d: acc[1], s: p.skin, h: p.hair, p: p.paper, m: p.metal };
}

export function drawMap(c, map, px, py, dk, flip) {
  for (let y = 0; y < 16; y++) {
    const row = map[y] || '';
    for (let x = 0; x < 16; x++) {
      const ch = row[flip ? 15 - x : x];
      const col = dk[ch];
      if (col) P(c, px + x, py + y, 1, 1, col);
    }
  }
}

/** idle / step L / step R — the step frames just alternate the foot row (row 14). */
export function frames(map) {
  const A = map;
  const B = map.map((r, y) => (y === 14 ? r.slice(0, 8) + '........' : r));
  const C = map.map((r, y) => (y === 14 ? '........' + r.slice(8) : r));
  return [A, B, C];
}

function sprite(c, who, tx, ty, dir, p) {
  const s = S[who];
  const flip = dir === 'right';
  const map = s[dir === 'right' ? 'side' : (dir || 'down')] || s.down;
  drawMap(c, map, Math.round(tx * T), Math.round(ty * T) - 6, dict(p, who), flip);
}

// ---- props
export function desk(c, tx, ty, w, p) { box(c, tx * T, ty * T, w * T, 22, p.wood, p.ink); P(c, tx * T + 2, ty * T + 2, w * T - 4, 4, p.woodD); }
export function consoleDesk(c, tx, ty, w, p, acc) {
  desk(c, tx, ty, w, p);
  for (let i = 0; i < w * 4 - 2; i++) P(c, tx * T + 4 + i * 4, ty * T + 10, 2, 2, i % 5 === 2 ? acc : p.metal);
  P(c, tx * T + 4, ty * T + 16, w * T - 8, 2, p.metalD);
}
export function reels(c, tx, ty, p) { box(c, tx * T, ty * T, 30, 14, p.metalD, p.ink); disc(c, tx * T + 8, ty * T + 7, 4, p.metal); disc(c, tx * T + 21, ty * T + 7, 4, p.metal); P(c, tx * T + 7, ty * T + 6, 2, 2, p.ink); P(c, tx * T + 20, ty * T + 6, 2, 2, p.ink); }
export function shelf(c, tx, ty, w, p) {
  box(c, tx * T, ty * T, w * T, 15, p.woodD, p.ink);
  const cols = [p.paperD, p.eversD, p.roanD, p.deltaD, p.metalD, p.paper];
  for (let i = 0; i < Math.floor((w * T - 6) / 3); i++) P(c, tx * T + 3 + i * 3, ty * T + 3, 2, 10, cols[(i * 7 + tx + ty) % 6]);
}
export function turntable(c, tx, ty, p, playing) {
  box(c, tx * T, ty * T, 32, 30, p.wood, p.ink);
  disc(c, tx * T + 15, ty * T + 14, 11, p.metalD); disc(c, tx * T + 15, ty * T + 14, 9, p.ink);
  disc(c, tx * T + 15, ty * T + 14, 3, playing ? p.lamp : p.paperD); P(c, tx * T + 15, ty * T + 14, 1, 1, p.ink);
  P(c, tx * T + 26, ty * T + 4, 2, 12, p.metal); P(c, tx * T + 22, ty * T + 14, 5, 2, p.metal);
}
export function chair(c, tx, ty, p) { box(c, tx * T + 3, ty * T + 3, 10, 10, p.wood, p.ink); P(c, tx * T + 4, ty * T + 4, 8, 2, p.woodD); }
export function armchair(c, tx, ty, p) { box(c, tx * T + 1, ty * T + 1, 22, 20, p.staffD, p.ink); P(c, tx * T + 4, ty * T + 5, 16, 12, p.staff); P(c, tx * T + 2, ty * T + 2, 20, 3, p.staffD); }
export function lampPool(c, tx, ty, p) {
  c.globalAlpha = 0.14; disc(c, tx * T + 8, ty * T + 8, 22, p.lamp);
  c.globalAlpha = 0.3; disc(c, tx * T + 8, ty * T + 8, 12, p.lamp);
  c.globalAlpha = 1;
  disc(c, tx * T + 8, ty * T + 8, 4, p.lamp); ring(c, tx * T + 8, ty * T + 8, 5, p.ink, 45);
}
export function crate(c, tx, ty, p) { box(c, tx * T + 2, ty * T + 3, 12, 11, p.wood, p.ink); P(c, tx * T + 3, ty * T + 8, 10, 1, p.woodD); P(c, tx * T + 7, ty * T + 4, 1, 9, p.woodD); }
export function ghost(c, tx, ty, w, h, p) {
  c.globalAlpha = 0.35;
  for (let x = 0; x < w * T; x += 4) { P(c, tx * T + x, ty * T, 2, 1, p.paperD); P(c, tx * T + x, ty * T + h * T - 1, 2, 1, p.paperD); }
  for (let y = 0; y < h * T; y += 4) { P(c, tx * T, ty * T + y, 1, 2, p.paperD); P(c, tx * T + w * T - 1, ty * T + y, 1, 2, p.paperD); }
  c.globalAlpha = 1;
}
export function puddle(c, tx, ty, p) { disc(c, tx * T + 7, ty * T + 9, 4, p.glass); disc(c, tx * T + 11, ty * T + 7, 2, p.glass); P(c, tx * T + 5, ty * T + 7, 3, 1, p.paperD); }
export function papers(c, tx, ty, p) { P(c, tx * T + 2, ty * T + 4, 7, 5, p.paperD); P(c, tx * T + 5, ty * T + 2, 7, 5, p.paper); P(c, tx * T + 6, ty * T + 3, 5, 1, p.paperD); }
export function windowV(c, tx, ty, p) { P(c, tx * T + 10, ty * T + 1, 5, 14, p.ink); P(c, tx * T + 11, ty * T + 2, 3, 12, p.glass); P(c, tx * T + 11, ty * T + 8, 3, 1, p.ink); }
export function cable(c, pts, p) {
  for (let i = 0; i < pts.length - 1; i++) {
    const [a, b] = [pts[i], pts[i + 1]];
    const n = Math.max(Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
    for (let k = 0; k <= n; k++) P(c, Math.round(a[0] + (b[0] - a[0]) * k / n), Math.round(a[1] + (b[1] - a[1]) * k / n), 1, 1, p.ink);
  }
}

// ---- world
/** Room rectangles as the handoff specifies them (inclusive tile coords). */
export const ROOMS = {
  studioA: [2, 3, 10, 10],
  studioB: [12, 3, 20, 10],
  studioC: [22, 3, 30, 10],
  corridor: [2, 12, 30, 14],
  office: [2, 16, 13, 31],
  archive: [15, 16, 30, 31],
  rug: [19, 21, 26, 27],
};
export const DOORS = [[6, 11], [16, 11], [26, 11], [7, 15], [22, 15]];

export function grid() {
  const g = Array.from({ length: H }, () => Array(W).fill('V'));
  const fill = (x1, y1, x2, y2, t) => { for (let y = y1; y <= y2; y++) for (let x = x1; x <= x2; x++) g[y][x] = t; };
  fill(1, 2, 31, 32, 'W');
  fill(...ROOMS.studioA, 'S'); fill(...ROOMS.studioB, 'S'); fill(...ROOMS.studioC, 'S');
  fill(...ROOMS.corridor, 'C'); fill(...ROOMS.office, 'O'); fill(...ROOMS.archive, 'A');
  fill(...ROOMS.rug, 'R');
  g[11][6] = 'C'; g[11][16] = 'C'; g[11][26] = 'C'; g[15][7] = 'O'; g[15][22] = 'A';
  return g;
}

/**
 * Paint the building. Identical to the design doc's paint() except the
 * people layer is optional (default OFF — the runtime places characters as
 * sprites) and the turntable's platter light is a flag.
 */
export function paintWorld(c, p, opts = {}) {
  const { era = 'A', playing = false, people = false, scene = 'normal' } = opts;
  const g = grid();
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const t = g[y][x], px = x * T, py = y * T;
    if (t === 'V') {
      P(c, px, py, T, T, p.void);
      if (era !== 'B' && (x * 13 + y * 29) % 31 < 2) { P(c, px + 3, py + 2, 1, 4, p.rain); P(c, px + 9, py + 9, 1, 4, p.rain); }
    } else if (t === 'W') {
      P(c, px, py, T, T, p.wallCap);
      const below = g[y + 1] && g[y + 1][x];
      if (below && below !== 'W' && below !== 'V') { P(c, px, py + 6, T, 10, p.wallFace); P(c, px, py + 15, T, 1, p.ink); P(c, px, py + 5, T, 1, p.ink); }
    } else if (t === 'S') {
      P(c, px, py, T, T, p.conc); if (y % 2 === 0) P(c, px, py, T, 1, p.concD); if ((x * 5 + y * 11) % 13 === 0) P(c, px + 3, py + 8, 5, 1, p.concD);
    } else if (t === 'R') {
      P(c, px, py, T, T, p.rug); if ((x + y) % 2) P(c, px + 4, py + 4, 2, 2, p.rugD);
      if (g[y][x - 1] !== 'R') P(c, px, py, 1, T, p.rugD); if (g[y][x + 1] !== 'R') P(c, px + 15, py, 1, T, p.rugD);
      if (g[y - 1][x] !== 'R') P(c, px, py, T, 1, p.rugD); if (g[y + 1][x] !== 'R') P(c, px, py + 15, T, 1, p.rugD);
    } else {
      P(c, px, py, T, T, p.floor); P(c, px, py + (y % 2 ? 7 : 15), T, 1, p.floorD); P(c, px + ((x * 7 + y * 3) % 3) * 5 + 2, py, 1, 7, p.floorD);
    }
  }
  // door thresholds
  DOORS.forEach(([x, y]) => { P(c, x * T, y * T + 1, T, 2, p.woodD); P(c, x * T, y * T + 13, T, 2, p.woodD); });
  // Studio A — Evers Lane: everything aligned
  shelf(c, 3, 3, 3, p); reels(c, 7, 3, p); consoleDesk(c, 3, 5, 4, p, p.evers); chair(c, 7, 6, p); crate(c, 9, 8, p); crate(c, 9, 9, p); papers(c, 4, 8, p);
  // Studio B — Roan Patina: sparse, dust ghosts where gear was removed
  desk(c, 15, 5, 2, p); ghost(c, 13, 8, 1, 1, p); ghost(c, 17, 8, 2, 1, p); papers(c, 15, 9, p);
  if (era === 'B') ghost(c, 18, 4, 1, 1, p); else crate(c, 18, 4, p);
  // Studio C — Delta Marlowe: crowded, stacked
  consoleDesk(c, 23, 4, 3, p, p.delta); desk(c, 27, 6, 2, p); crate(c, 23, 8, p); crate(c, 24, 8, p); crate(c, 23, 9, p); crate(c, 29, 3, p); crate(c, 29, 4, p); papers(c, 27, 9, p); papers(c, 26, 3, p);
  cable(c, [[23 * T + 8, 6 * T], [24 * T, 8 * T - 2], [27 * T + 4, 7 * T + 6]], p);
  // Office
  shelf(c, 8, 16, 4, p); desk(c, 4, 20, 3, p); papers(c, 5, 20, p); reels(c, 5, 20.4, p);
  desk(c, 9, 17, 2, p); papers(c, 9, 17, p);
  armchair(c, 4, 26, p); lampPool(c, 3, 25, p); windowV(c, 1, 23, p); windowV(c, 1, 24, p);
  // Archive / listening room
  shelf(c, 16, 16, 5, p); shelf(c, 24, 16, 6, p);
  turntable(c, 21, 22, p, playing || scene === 'listening'); lampPool(c, 19, 22, p);
  armchair(c, 25, 25, p); crate(c, 16, 29, p); crate(c, 17, 29, p);
  if (era === 'B') { crate(c, 18, 29, p); crate(c, 16, 28, p); }
  else { puddle(c, 10, 13, p); puddle(c, 24, 13, p); }
  // people (design-doc parity only; the runtime world places characters itself)
  if (people) {
    sprite(c, 'producer', 5, 22, 'up', p); sprite(c, 'critic', 10.4, 18.4, 'down', p);
    sprite(c, 'listener', 4.4, 26.2, 'down', p); sprite(c, 'muse', 2, 23.4, 'side', p);
    if (scene === 'listening') {
      sprite(c, 'roan', 15.5, 7, 'down', p); sprite(c, 'delta', 24.5, 7, 'down', p);
      sprite(c, 'evers', 21.4, 24.6, 'up', p);
    } else {
      sprite(c, 'evers', 5, 7, 'up', p); sprite(c, 'roan', 15.5, 7, 'down', p); sprite(c, 'delta', 24.5, 7, 'down', p);
    }
  }
}

/** Character order and frame layout shared with web/lib/world/sprites.ts — keep in sync. */
export const CHARACTERS = ['evers', 'roan', 'delta', 'producer', 'critic', 'listener', 'muse'];
export const DIRECTIONS = ['down', 'left', 'right', 'up'];

/** Default character placements (tile coords + facing) from the design's normal scene. */
export const DEFAULT_PLACEMENTS = {
  evers: { tx: 5, ty: 7, dir: 'up' },
  roan: { tx: 15.5, ty: 7, dir: 'down' },
  delta: { tx: 24.5, ty: 7, dir: 'down' },
  producer: { tx: 5, ty: 22, dir: 'up' },
  critic: { tx: 10.4, ty: 18.4, dir: 'down' },
  listener: { tx: 4.4, ty: 26.2, dir: 'down' },
  muse: { tx: 2, ty: 23.4, dir: 'left' },
};
