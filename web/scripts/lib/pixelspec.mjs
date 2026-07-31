/**
 * Port of design/handoff/pixel.js — the AUTHORITATIVE tile/sprite/palette
 * spec (the "expanded street" handoff) — for the build-time pipeline
 * (render_pixels.mjs, press photos).
 *
 * The handoff says: port the data (palette, era LUT, sprite maps, room
 * grid/paint, street layout, era prop diffs) into real PNG assets; never
 * ship pixel.js to the client. This module is that port, structured in two
 * layers:
 *   - lib/world/pixelpaint.mjs keeps the PAINT (palette + sprite maps +
 *     prop painters + the per-building street-state painter), browser-safe,
 *     because the runtime paints the street's occupancy layer live;
 *   - this file keeps the COMPOSITION over the geometry registry
 *     (web/world-geometry.json) — the single source of truth for every
 *     tile coordinate, shared with lib/world/geometry.ts. The registry
 *     keeps the WHERE; pixelpaint keeps the HOW.
 *
 * Adaptations for build use:
 *   - painters take a 2d context (node-canvas), not a <canvas> element
 *     (drawResidentRoom, which sizes its canvas, is the exception);
 *   - paintWorld()/paintStreet() can skip the people layer (characters ship
 *     as their own spritesheet and are placed by the Phaser scene at
 *     runtime) and paintStreet() can skip the building-state layer (the
 *     runtime paints occupancy from live agents data); office pets are
 *     background and always paint.
 *
 * When the design's pixel.js changes, re-sync pixelpaint + the registry and
 * re-run scripts/render_pixels.mjs. Two gates guard the port: the
 * determinism test (double render) and world_parity.test.ts, which renders
 * design/handoff/pixel.js itself against these registry-driven painters
 * and requires hash-identical pixels.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  T, PAL, P, spriteAt,
  consoleDesk, chair, lampPool, ghost, crate, papers, reels, amp, signPlate,
  windowW, lampPost, leaseTile, paintProps, paintBuildingState, PROP_KINDS,
} from '../../lib/world/pixelpaint.mjs';

export * from '../../lib/world/pixelpaint.mjs';

/** The geometry registry — web/world-geometry.json, the single source of truth. */
export const GEO = JSON.parse(
  readFileSync(
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'world-geometry.json'),
    'utf8',
  ),
);

if (GEO.tile !== T) {
  throw new Error(`registry tile ${GEO.tile} != pixelpaint tile ${T} — the spec drifted`);
}

export const W = GEO.house.canvas.w, H = GEO.house.canvas.h;
export const SW = GEO.street.canvas.w, SH = GEO.street.canvas.h;

// ---- world
/** Room rectangles from the registry (inclusive tile coords), kept for consumers. */
export const ROOMS = Object.fromEntries(GEO.house.rooms.map((r) => [r.id, r.rect]));
export const DOORS = GEO.house.doors.map((d) => d.at);

export function grid() {
  const g = Array.from({ length: H }, () => Array(W).fill('V'));
  const fill = (x1, y1, x2, y2, t) => { for (let y = y1; y <= y2; y++) for (let x = x1; x <= x2; x++) g[y][x] = t; };
  fill(...GEO.house.shell, 'W');
  for (const room of GEO.house.rooms) fill(...room.rect, room.tile);
  for (const door of GEO.house.doors) g[door.at[1]][door.at[0]] = door.tile;
  return g;
}

/**
 * Paint the building — geometry from the registry, paint from pixelpaint.
 * Identical to the design doc's paint() except the people layer is optional
 * (default OFF — the runtime places characters as sprites; the office pets
 * are background and always paint) and the turntable's platter light is a
 * flag.
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
  for (const [x, y] of DOORS) { P(c, x * T, y * T + 1, T, 2, p.woodD); P(c, x * T, y * T + 13, T, 2, p.woodD); }
  // props, in the registry's (= the design doc's) paint order
  paintProps(c, GEO.house.props, p, era, { playing: playing || scene === 'listening' });
  // people (design-doc parity only; the runtime world places characters itself)
  const places = GEO.house.placements;
  if (people) {
    for (const pl of Object.values(places)) {
      if (pl.kind === 'staff') spriteAt(c, pl.sprite, pl.tx, pl.ty, pl.dir, p);
    }
  }
  // office pets: background, always painted (drawn between staff and acts,
  // exactly the design paint order)
  for (const pet of GEO.house.pets) PROP_KINDS[pet.kind](c, pet, p);
  if (people) {
    const stand = GEO.house.turntable.stand;
    if (scene === 'listening') {
      for (const [id, pl] of Object.entries(places)) {
        if (pl.kind === 'act' && id !== 'keep') spriteAt(c, pl.sprite, pl.tx, pl.ty, pl.dir, p);
      }
      spriteAt(c, places.keep.sprite, stand[0], stand[1], 'up', p);
    } else {
      for (const pl of Object.values(places)) {
        if (pl.kind === 'act') spriteAt(c, pl.sprite, pl.tx, pl.ty, pl.dir, p);
      }
    }
  }
}

// ---- THE STREET: AFAR house on the corner + Archive Row ----
// Registry-driven and parity-gated against the handoff's drawStreet; the
// world's shipped backgrounds render from here (people + building states
// OFF — the runtime supplies both from live data).

export function streetGrid() {
  const st = GEO.street;
  const g = Array.from({ length: SH }, () => Array(SW).fill('V'));
  const fill = (x1, y1, x2, y2, t) => { for (let y = y1; y <= y2; y++) for (let x = x1; x <= x2; x++) g[y][x] = t; };
  fill(...st.houseRegion, 'H'); // AFAR house region, painted by paintWorld()
  for (const r of st.sidewalks) fill(...r, 'P');
  fill(...st.road, 'D');
  for (const b of st.buildings) {
    const [x1, y1, x2, y2] = b.shell;
    fill(x1, y1, x2, y2, 'W');
    fill(x1 + 1, y1 + 1, x2 - 1, y2 - 1, b.status === 'lease' ? 'L' : 'F');
    g[b.door[1]][b.door[0]] = b.status === 'lease' ? 'L' : 'F'; // door onto the sidewalk
  }
  return g;
}

/**
 * The street scene: the house + Archive Row. Every building interior
 * paints as the dark unfitted base first; `buildingStates` (default on)
 * then lays each building's occupancy dressing per the REGISTRY's statuses
 * via paintBuildingState — the same function the runtime calls with LIVE
 * statuses. `people` (default on) additionally paints the house cast and
 * the design's placed resident; the shipped backgrounds turn both off.
 */
export function paintStreet(c, p, era, scene, opts = {}) {
  const { people = true, buildingStates = true } = opts;
  const st = GEO.street;
  paintWorld(c, p, { era, people, scene: 'normal' });
  const g = streetGrid();
  const x0 = st.houseRegion[2] + 1; // street tiles start east of the house region
  for (let y = 0; y < SH; y++) for (let x = x0; x < SW; x++) {
    const t = g[y][x], px = x * T, py = y * T;
    if (t === 'V') {
      P(c, px, py, T, T, p.void);
      if (era !== 'B' && (x * 13 + y * 29) % 31 < 2) { P(c, px + 3, py + 2, 1, 4, p.rain); P(c, px + 9, py + 9, 1, 4, p.rain); }
    } else if (t === 'P') {
      P(c, px, py, T, T, p.pave); if (y % 2 === 0) P(c, px, py, T, 1, p.paveD);
      if ((x * 5 + y * 7) % 11 === 0) P(c, px + 4, py + 9, 4, 1, p.paveD);
      if (g[y][x + 1] === 'D') P(c, px + 14, py, 2, T, p.curb);
      if (g[y][x - 1] === 'D') P(c, px, py, 2, T, p.curb);
    } else if (t === 'D') {
      P(c, px, py, T, T, p.asph);
      if ((x * 11 + y * 5) % 13 === 0) P(c, px + 3, py + 6, 6, 1, p.asphD);
      if (x === st.laneLineX && y % 3 !== 2) { c.globalAlpha = 0.3; P(c, px + 15, py + 3, 2, 9, p.paperD); c.globalAlpha = 1; }
    } else if (t === 'W') {
      P(c, px, py, T, T, p.wallCap);
      const below = g[y + 1] && g[y + 1][x];
      if (below && below !== 'W' && below !== 'V' && below !== 'H') { P(c, px, py + 6, T, 10, p.wallFace); P(c, px, py + 15, T, 1, p.ink); P(c, px, py + 5, T, 1, p.ink); }
    } else if (t === 'L' || t === 'F') {
      // every building interior starts as the dark unfitted base; the
      // building-state layer (build-time or runtime) fits it out
      leaseTile(c, x, y, p);
    }
  }
  // AFAR street door: east wall, straight into the archive
  const [sdx, sdy] = st.houseStreetDoor.at;
  const sdh = st.houseStreetDoor.h;
  P(c, sdx * T, sdy * T, T, sdh * T, p.floor); P(c, sdx * T, sdy * T, 2, sdh * T, p.woodD); P(c, sdx * T + 14, sdy * T, 2, sdh * T, p.woodD);
  // per-building occupancy dressing (registry statuses = the design scene)
  if (buildingStates) {
    for (const b of st.buildings) {
      paintBuildingState(c, b, p, { status: b.status, interior: b.interior }, era);
    }
  }
  // street furniture (registry paint order = the design doc's)
  paintProps(c, st.props, p, era);
  for (const [x, y] of st.lampPosts) lampPost(c, x, y, p);
  // the resident (design parity; the runtime places residents from live data)
  if (people) {
    const vess = st.placements.vess;
    if (scene === 'listening') spriteAt(c, vess.sprite, vess.listening.tx, vess.listening.ty, vess.listening.dir, p);
    else spriteAt(c, vess.sprite, vess.tx, vess.ty, vess.dir, p);
  }
}

/**
 * A resident room interior, parameterized by ONE accent + ONE prop slot
 * (the handoff's tenant system). Takes a canvas: it sizes it.
 */
export function drawResidentRoom(cv, opts = {}) {
  const acc = opts.acc || PAL.guest, accD = opts.accD || PAL.guestD, prop = opts.prop || 'none', occ = !!opts.occupied;
  const R = GEO.street.residentRoom;
  const W2 = R.canvas.w, H2 = R.canvas.h;
  cv.width = W2 * T; cv.height = H2 * T;
  const c = cv.getContext('2d'); c.imageSmoothingEnabled = false; const p = PAL;
  for (let y = 0; y < H2; y++) for (let x = 0; x < W2; x++) {
    const px = x * T, py = y * T, wall = x === 0 || x === W2 - 1 || y === 0 || y === H2 - 1;
    if (wall) { P(c, px, py, T, T, p.wallCap); if (y === 0) { P(c, px, py + 6, T, 10, p.wallFace); P(c, px, py + 5, T, 1, p.ink); P(c, px, py + 15, T, 1, p.ink); } }
    else { P(c, px, py, T, T, p.floor); P(c, px, py + (y % 2 ? 7 : 15), T, 1, p.floorD); P(c, px + ((x * 7 + y * 3) % 3) * 5 + 2, py, 1, 7, p.floorD); }
  }
  for (const [x, y] of R.windows) windowW(c, x, y, p); // windows to the street — sightline to the corner
  P(c, R.door.x * T, (H2 - 1) * T, R.door.w * T, T, p.floor);
  P(c, R.door.x * T, (H2 - 1) * T, 2, T, p.woodD); P(c, (R.door.x + R.door.w) * T - 2, (H2 - 1) * T, 2, T, p.woodD);
  consoleDesk(c, R.consoleDesk[0], R.consoleDesk[1], R.consoleDesk[2], p, acc);
  chair(c, R.chair[0], R.chair[1], p); lampPool(c, R.lampPool[0], R.lampPool[1], p);
  ghost(c, R.propSlot.ghost[0], R.propSlot.ghost[1], R.propSlot.ghost[2], R.propSlot.ghost[3], p); // the character prop slot
  if (prop === 'amp') amp(c, R.propSlot.amp[0], R.propSlot.amp[1], p);
  if (prop === 'reels') reels(c, R.propSlot.reels[0], R.propSlot.reels[1], p);
  signPlate(c, R.signPlate[0], R.signPlate[1], p, occ ? p.paper : p.paperD);
  if (occ) {
    crate(c, R.crate[0], R.crate[1], p); papers(c, R.papers[0], R.papers[1], p);
    spriteAt(c, 'vess', R.stand[0], R.stand[1], 'down', Object.assign({}, p, { guest: acc, guestD: accD }));
  }
}

/** Character order and frame layout for the spritesheet — the registry's spriteOrder. */
export const CHARACTERS = GEO.spriteOrder;
export const DIRECTIONS = ['down', 'left', 'right', 'up'];
