/**
 * The PAINT half of the design handoff's pixel.js — palette, era LUT,
 * sprite maps, prop painters, and the per-building street-state painter —
 * with NO node imports and NO geometry: every function takes a 2d context
 * (node-canvas at build time, the browser canvas at runtime) and tile
 * coordinates supplied by the caller from the geometry registry.
 *
 * Two consumers, one implementation:
 *   - scripts/lib/pixelspec.mjs (asset render) re-exports everything here
 *     and composes it with the registry; world_parity.test.ts holds that
 *     composition hash-identical to design/handoff/pixel.js itself.
 *   - lib/world/buildings.ts (the runtime) paints the street's per-building
 *     occupancy layer — lease / move-in ready / occupied — onto a Phaser
 *     canvas texture from live agents data, with the SAME painters, so a
 *     runtime building is pixel-identical to a rendered one.
 *
 * T is the tile size the sprite maps are authored at; pixelspec asserts it
 * equals the registry's `tile` so the two cannot drift.
 */

export const T = 16;

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
  asph: '#2b2e34', asphD: '#262a2f',
  pave: '#4a463d', paveD: '#403c34', curb: '#5a5449',
  guest: '#8a6f9e', guestD: '#5e4a6c',
};

/** The dark unfitted-interior base of a FOR LEASE shell (design drawStreet). */
export const LEASE_FLOOR = '#191b1f';

/** Era B = the same world through a LUT: entries remapped, everything else untouched. */
export function eraPal(era) {
  if (era !== 'B') return PAL;
  return Object.assign({}, PAL, {
    void: '#13100b', rain: '#13100b', glass: '#4d4026',
    floor: '#4b4033', floorD: '#403629', conc: '#3d3a33', concD: '#37342d',
    wallFace: '#55503f', lamp: '#d8a248',
    asph: '#302d27', asphD: '#2a2722',
    pave: '#4d4536', paveD: '#423b2e', curb: '#5c5240',
  });
}

export function P(c, x, y, w, h, col) { c.fillStyle = col; c.fillRect(x, y, w, h); }
export function box(c, x, y, w, h, fill, edge) { P(c, x, y, w, h, edge); P(c, x + 1, y + 1, w - 2, h - 2, fill); }
export function disc(c, cx, cy, r, col) {
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
"................","......oooo......",".....ommmmo.....","....omhhhhmo....",
"....omssssmo....","....omsossmo....",".....osssso.....","....occccco.....",
"...occccccco....","...occcmccco....","...occccccco....","...odcccccdo....",
"....occccco.....","....occccco.....","....oo...oo.....","................"],
side:[
"................","......oooo......",".....ommmmo.....","....omhhhho.....",
"....omsssso.....","....omsosso.....",".....ossso......","....occcco......",
"....occccco.....","....ocmccco.....","....occccco.....","....odcccdo.....",
"....occcco......","....occcco......",".....oo.oo......","................"],
up:[
"................","......oooo......",".....ommmmo.....","....omhhhhmo....",
"....omhhhhmo....","....omhhhhmo....",".....ohhhho.....","....occccco.....",
"...occccccco....","...occccccco....","...occccccco....","...odcccccdo....",
"....occccco.....","....occccco.....","....oo...oo.....","................"]},
critic:{down:[
"................","................","......ohho......",".....ohhhho.....",
".....ommmmo.....","......osso......",".....occcco.....",".....occcco.....",
"...ppocccco.....","...ppocccco.....",".....occcco.....",".....occcco.....",
".....occcco.....",".....occcco.....",".....oo..oo.....","................"],
side:[
"................","................","......ohho......",".....ohhho......",
".....ommo.......",".....osso.......",".....occco......",".....occco......",
"...ppoccco......","...ppoccco......",".....occco......",".....occco......",
".....occco......",".....occco......",".....oo.oo......","................"],
up:[
"................","................","......ohho......",".....ohhhho.....",
".....ohhhho.....","......ohho......",".....occcco.....",".....occcco.....",
".....occcco.....",".....occcco.....",".....occcco.....",".....occcco.....",
".....occcco.....",".....occcco.....",".....oo..oo.....","................"]},
listener:{down:[
"................","................","......ohho......",".....ossso......",
".....ososo......","....occccco.....","...occccccco....","...occccccco....",
"...occccccco....","...occccccco....","...occccccco....","....occccco.....",
"....occccco.....","....occccco.....","....oo...oo.....","................"],
side:[
"................","................","......ohho......",".....ossso......",
".....oosso......","....occcco......","...occcccco.....","...occcccco.....",
"...occcccco.....","...occcccco.....","...occcccco.....","....occcco......",
"....occcco......","....occcco......","....oo..oo......","................"],
up:[
"................","................","......ohho......",".....ohhho......",
".....ohhho......","....occccco.....","...occccccco....","...occccccco....",
"...occccccco....","...occccccco....","...occccccco....","....occccco.....",
"....occccco.....","....occccco.....","....oo...oo.....","................"]},
muse:{down:[
"................",".....ohhho......","....ohhhhho.....","....ohsssho.....",
"....ohsosho.....","....ohsssho.....","....ohpppho.....","....ohpppho.....",
"....ohpppho.....",".....opppo......",".....opppo......",".....opppo......",
".....opppo......",".....opppo......",".....oo.oo......","................"],
side:[
"................",".....ohhho......","....ohhhho......","....ohssso......",
"....ohsoso......","....ohssso......","....ohpppo......","....ohpppo......",
"....ohpppo......",".....oppo.......",".....oppo.......",".....oppo.......",
".....oppo.......",".....oppo.......",".....oo.oo......","................"],
up:[
"................",".....ohhho......","....ohhhhho.....","....ohhhhho.....",
"....ohhhhho.....","....ohhhhho.....","....ohpppho.....","....ohpppho.....",
"....ohpppho.....",".....opppo......",".....opppo......",".....ohhho......",
".....opppo......",".....opppo......",".....oo.oo......","................"]},
vess:{down:[
"................","......oooo......",".....oddddo.....","....oddddddo....",
"....osssssso....","....osossoso....",".....osssso.....","....occccco.....",
"...occccccco....","...ocpcccpco....","...occccccco....","...odcccccdo....",
"...odcccccdo....","...odcccccdo....","....oo...oo.....","................"],
side:[
"................","......oooo......",".....oddddo.....","....odddddo.....",
"....osssso......","....ososso......",".....ossso......","....occcco......",
"....occccco.....","....ocpccco.....","....occccco.....","....odcccdo.....",
"....occccco.....","....odcccdo.....",".....oo.oo......","................"],
up:[
"................","......oooo......",".....oddddo.....","....oddddddo....",
"....oddddddo....","....oddddddo....",".....odddo......","....occccco.....",
"...occccccco....","...occccccco....","...occccccco....","...odcccccdo....",
"...odcccccdo....","...odcccccdo....","....oo...oo.....","................"]}
};

/** Colour dictionary for a character's map symbols (act/guest accents never remap). */
export function dict(p, who) {
  const acc = {
    evers: [p.evers, p.eversD], roan: [p.roan, p.roanD], delta: [p.delta, p.deltaD],
    vess: [p.guest, p.guestD],
  }[who] || [p.staff, p.staffD];
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

/** dir: down/up as-is; 'side' or 'left' = the side map; 'right' = side flipped. */
export function spriteAt(c, who, tx, ty, dir, p) {
  const s = S[who];
  const flip = dir === 'right';
  const map = s[dir === 'right' || dir === 'left' ? 'side' : (dir || 'down')] || s.down;
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

// ---- street props (the "expanded street" handoff)
export function windowW(c, tx, ty, p) { P(c, tx * T + 1, ty * T + 1, 5, 14, p.ink); P(c, tx * T + 2, ty * T + 2, 3, 12, p.glass); P(c, tx * T + 2, ty * T + 8, 3, 1, p.ink); }
export function paperWin(c, tx, ty, p) { P(c, tx * T + 1, ty * T + 1, 5, 14, p.ink); P(c, tx * T + 2, ty * T + 2, 3, 12, p.paperD); P(c, tx * T + 2, ty * T + 5, 3, 1, p.ink); P(c, tx * T + 2, ty * T + 10, 3, 1, p.ink); }
export function signPlate(c, tx, ty, p, col) { P(c, tx * T + 5, ty * T + 4, 7, 9, p.ink); P(c, tx * T + 6, ty * T + 5, 5, 7, col); P(c, tx * T + 7, ty * T + 7, 3, 1, p.ink); P(c, tx * T + 7, ty * T + 9, 3, 1, p.ink); }
export function amp(c, tx, ty, p) { box(c, tx * T, ty * T, 15, 14, p.metalD, p.ink); disc(c, tx * T + 7, ty * T + 8, 3, p.metal); P(c, tx * T + 2, ty * T + 2, 11, 2, p.metal); }
export function bench(c, tx, ty, p) { box(c, tx * T + 1, ty * T + 4, 26, 8, p.wood, p.ink); P(c, tx * T + 2, ty * T + 7, 24, 1, p.woodD); P(c, tx * T + 3, ty * T + 12, 2, 3, p.ink); P(c, tx * T + 23, ty * T + 12, 2, 3, p.ink); }
export function mailbox(c, tx, ty, p) { P(c, tx * T + 7, ty * T + 8, 2, 7, p.metalD); box(c, tx * T + 4, ty * T + 2, 9, 7, p.metal, p.ink); P(c, tx * T + 5, ty * T + 4, 7, 1, p.ink); P(c, tx * T + 12, ty * T + 1, 1, 4, p.evers); }
export function dustPatch(c, tx, ty, p) { c.globalAlpha = 0.5; P(c, tx * T + 3, ty * T + 6, 6, 2, p.paperD); P(c, tx * T + 8, ty * T + 9, 4, 2, p.paperD); c.globalAlpha = 1; }
export function tree(c, tx, ty, p) {
  P(c, tx * T + 6, ty * T + 10, 4, 8, '#3a2e1f'); P(c, tx * T + 5, ty * T + 16, 6, 2, p.paveD); // trunk + pit
  const lv = '#3f4a38', lvD = '#333d2e', lvL = '#4a5741';
  disc(c, tx * T + 8, ty * T + 2, 8, lvD); disc(c, tx * T + 8, ty * T + 1, 7, lv);
  disc(c, tx * T + 5, ty * T - 1, 4, lvL); disc(c, tx * T + 11, ty * T + 3, 3, lvD);
  P(c, tx * T + 4, ty * T, 2, 2, lvL); P(c, tx * T + 10, ty * T - 3, 2, 2, lvL);
}
export function shade2(hex, f) {
  const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
  const t = f < 0 ? 0 : 255, a = Math.abs(f);
  return 'rgb(' + Math.round(r + (t - r) * a) + ',' + Math.round(g + (t - g) * a) + ',' + Math.round(b + (t - b) * a) + ')';
}
export function car(c, tx, ty, p, col) {
  // parked car, top-down, nose north, 2 tiles long
  box(c, tx * T + 2, ty * T + 1, 12, 30, col, p.ink);
  P(c, tx * T + 4, ty * T + 7, 8, 5, p.glass); P(c, tx * T + 4, ty * T + 21, 8, 4, p.glass); // windshield + rear
  P(c, tx * T + 4, ty * T + 13, 8, 7, shade2(col, 0.12)); // roof
  P(c, tx * T + 3, ty * T + 2, 2, 2, p.paperD); P(c, tx * T + 11, ty * T + 2, 2, 2, p.paperD); // headlights
  P(c, tx * T + 3, ty * T + 28, 2, 2, p.eversD); P(c, tx * T + 11, ty * T + 28, 2, 2, p.eversD); // taillights
  P(c, tx * T + 2, ty * T + 5, 1, 4, p.ink); P(c, tx * T + 13, ty * T + 5, 1, 4, p.ink); P(c, tx * T + 2, ty * T + 23, 1, 4, p.ink); P(c, tx * T + 13, ty * T + 23, 1, 4, p.ink); // wheels
}
export function subway(c, tx, ty, p) {
  // NY subway stair entrance, 2x3 tiles: railed stairwell descending south
  P(c, tx * T, ty * T, 2 * T, 3 * T, p.pave);
  P(c, tx * T + 2, ty * T + 8, 28, 38, p.ink); // stair void
  for (let i = 0; i < 5; i++) P(c, tx * T + 4, ty * T + 10 + i * 7, 24, 3, shade2(p.asph, -(0.1 + i * 0.12))); // steps darkening down
  P(c, tx * T, ty * T + 6, 2, 42, p.metalD); P(c, tx * T + 30, ty * T + 6, 2, 42, p.metalD); // railings
  P(c, tx * T, ty * T + 6, 32, 2, p.metalD);
  // globe lamp on post (green = entrance)
  P(c, tx * T + 30, ty * T - 6, 2, 12, p.metalD); disc(c, tx * T + 31, ty * T - 8, 3, '#3f4a38'); P(c, tx * T + 30, ty * T - 9, 1, 1, '#4a5741');
  // R bullet sign on the rail head
  disc(c, tx * T + 8, ty * T + 3, 5, '#e0b25a'); ring(c, tx * T + 8, ty * T + 3, 5, p.ink, 30);
  P(c, tx * T + 7, ty * T + 1, 1, 5, p.ink); P(c, tx * T + 8, ty * T + 1, 2, 1, p.ink); P(c, tx * T + 8, ty * T + 3, 2, 1, p.ink); P(c, tx * T + 10, ty * T + 2, 1, 1, p.ink); P(c, tx * T + 9, ty * T + 4, 1, 2, p.ink); // pixel R
}
export function deerhound(c, tx, ty, p, dir) {
  // scottish deerhound: tall, wiry grey, long muzzle + tail. ~20x14 px
  const g1 = '#6a6f78', g2 = '#43474e', x = tx * T, y = ty * T, f = dir === 'right';
  const X = (dx, dy, w, h, col) => P(c, x + (f ? 20 - dx - w : dx), y + dy, w, h, col);
  X(3, 4, 13, 5, g1); // body
  X(3, 3, 13, 1, g2); // wiry back
  X(14, 1, 4, 4, g1); X(18, 2, 3, 2, g1); // neck+head raised, long muzzle
  X(15, 0, 2, 2, g2); // ear
  X(20, 3, 1, 1, p.ink); // nose
  X(0, 2, 4, 2, g2); // long tail low
  X(4, 9, 2, 5, g1); X(8, 9, 2, 5, g2); X(11, 9, 2, 5, g1); X(14, 9, 2, 5, g2); // long legs
  X(4, 13, 2, 1, g2); X(14, 13, 2, 1, g2);
  X(16, 3, 1, 1, p.ink); // eye
}
export function cat(c, tx, ty, p) {
  // small ink cat, curled ~8x6
  const x = tx * T, y = ty * T;
  disc(c, x + 4, y + 4, 3, p.ink); P(c, x + 6, y + 1, 3, 3, p.ink); // body + head
  P(c, x + 6, y, 1, 1, p.ink); P(c, x + 8, y, 1, 1, p.ink); // ears
  P(c, x + 0, y + 4, 2, 1, p.ink); P(c, x + 1, y + 3, 1, 1, p.ink); // tail wrap
  P(c, x + 7, y + 2, 1, 1, p.lamp); // one open eye
}
export function lampPost(c, tx, ty, p) {
  c.globalAlpha = 0.12; disc(c, tx * T + 8, ty * T + 4, 20, p.lamp);
  c.globalAlpha = 0.25; disc(c, tx * T + 8, ty * T + 4, 11, p.lamp);
  c.globalAlpha = 1;
  P(c, tx * T + 7, ty * T - 8, 2, 12, p.metalD); P(c, tx * T + 5, ty * T - 11, 6, 4, p.ink); P(c, tx * T + 6, ty * T - 10, 4, 2, p.lamp);
}

/** One dispatch table: registry prop entry -> painter call. A consoleDesk's
 * `acc` may be a palette key ("evers", "guest") or a literal hex accent (the
 * street tenant system's ONE accent parameter). */
export const PROP_KINDS = {
  shelf: (c, e, p) => shelf(c, e.tx, e.ty, e.w, p),
  reels: (c, e, p) => reels(c, e.tx, e.ty, p),
  consoleDesk: (c, e, p) => consoleDesk(c, e.tx, e.ty, e.w, p, p[e.acc] ?? e.acc),
  desk: (c, e, p) => desk(c, e.tx, e.ty, e.w, p),
  chair: (c, e, p) => chair(c, e.tx, e.ty, p),
  crate: (c, e, p) => crate(c, e.tx, e.ty, p),
  papers: (c, e, p) => papers(c, e.tx, e.ty, p),
  ghost: (c, e, p) => ghost(c, e.tx, e.ty, e.w, e.h, p),
  cable: (c, e, p) => cable(c, e.pts, p),
  armchair: (c, e, p) => armchair(c, e.tx, e.ty, p),
  lampPool: (c, e, p) => lampPool(c, e.tx, e.ty, p),
  windowV: (c, e, p) => windowV(c, e.tx, e.ty, p),
  turntable: (c, e, p, o) => turntable(c, e.tx, e.ty, p, !!(o && o.playing)),
  puddle: (c, e, p) => puddle(c, e.tx, e.ty, p),
  amp: (c, e, p) => amp(c, e.tx, e.ty, p),
  bench: (c, e, p) => bench(c, e.tx, e.ty, p),
  mailbox: (c, e, p) => mailbox(c, e.tx, e.ty, p),
  dustPatch: (c, e, p) => dustPatch(c, e.tx, e.ty, p),
  tree: (c, e, p) => tree(c, e.tx, e.ty, p),
  subway: (c, e, p) => subway(c, e.tx, e.ty, p),
  car: (c, e, p) => car(c, e.tx, e.ty, p, e.col),
  cat: (c, e, p) => cat(c, e.tx, e.ty, p),
  deerhound: (c, e, p) => deerhound(c, e.tx, e.ty, p, e.dir),
};
export function paintProps(c, list, p, era, opts) {
  for (const e of list) {
    if (e.eras && !e.eras.includes(era)) continue;
    PROP_KINDS[e.kind](c, e, p, opts);
  }
}

/** One floorboard tile at WORLD tile (x, y) — the pattern seeds use the
 * world coords, so a runtime-painted interior matches a rendered one. */
export function floorTile(c, x, y, p) {
  P(c, x * T, y * T, T, T, p.floor);
  P(c, x * T, y * T + (y % 2 ? 7 : 15), T, 1, p.floorD);
  P(c, x * T + ((x * 7 + y * 3) % 3) * 5 + 2, y * T, 1, 7, p.floorD);
}

/** One dark unfitted-interior tile (the FOR LEASE base) at world tile (x, y). */
export function leaseTile(c, x, y, p) {
  P(c, x * T, y * T, T, T, LEASE_FLOOR);
  if ((x * 7 + y * 3) % 9 === 0) P(c, x * T + 5, y * T + 8, 5, 1, p.concD);
}

/**
 * ONE building's occupancy dressing — the layer between the street shell
 * and the characters. `b` is a registry street building ({shell, door,
 * windows, signPlate}); `state` is `{ status, interior }` where status is
 * 'lease' | 'ready' | 'occupied' and `interior` is a registry-style prop
 * list in absolute tile coords (ignored for lease). Paints:
 *   lease    — papered-over door + papered windows + FOR LEASE plate (the
 *              dark unfitted interior underneath is the shell's own base);
 *   ready /  — floorboard interior + door threshold + street windows +
 *   occupied   name plate + the interior props (dust ghosts, or the tenant
 *              system's console/prop/crates).
 * Both the asset pipeline (paintStreet) and the runtime occupancy layer
 * (lib/world/buildings.ts) call THIS function, so they cannot drift.
 */
export function paintBuildingState(c, b, p, state, era = 'A') {
  const [x1, y1, x2, y2] = b.shell;
  const [dx, dy] = b.door;
  if (state.status === 'lease') {
    P(c, dx * T + 3, dy * T + 2, 10, 12, p.paperD);
    P(c, dx * T + 4, dy * T + 4, 8, 1, p.ink);
    P(c, dx * T + 4, dy * T + 7, 8, 1, p.ink);
    for (const [wx, wy] of b.windows) paperWin(c, wx, wy, p);
    signPlate(c, b.signPlate[0], b.signPlate[1], p, p.paperD);
    return;
  }
  // fitted interior: floorboards over the dark base, plus the door tile
  for (let y = y1 + 1; y <= y2 - 1; y++) {
    for (let x = x1 + 1; x <= x2 - 1; x++) floorTile(c, x, y, p);
  }
  floorTile(c, dx, dy, p);
  P(c, dx * T + 1, dy * T, 2, T, p.woodD);
  P(c, dx * T + 13, dy * T, 2, T, p.woodD);
  for (const [wx, wy] of b.windows) windowW(c, wx, wy, p);
  signPlate(c, b.signPlate[0], b.signPlate[1], p, p.paper);
  paintProps(c, state.interior || [], p, era);
}
