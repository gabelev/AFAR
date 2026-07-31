/**
 * Sprite/tile pipeline: renders the world's PNG assets at 1x from the
 * ported pixel spec (scripts/lib/pixelspec.mjs — the design handoff's
 * pixel.js data). The Phaser world displays them at 2x with pixelArt on.
 *
 * Outputs (committed, under web/public/world/):
 *   bg-era-a.png / bg-era-b.png — the whole building, 528×544 (33×34 tiles
 *     of 16px), rooms + props, NO characters (era B = LUT + prop diff).
 *   characters.png — 7 characters × 12 frames of 16×16 (rows in
 *     pixelspec CHARACTERS order; cols = 4 directions × 3 frames, the
 *     handoff's frames() convention: idle / step L / step R).
 *   tiles.png — the 16×16 base tiles at 1x, one per column (reference +
 *     any future Tiled use).
 *   props.png — the 32×32 props at 1x, one per column.
 *
 * Deterministic: same spec in, byte-identical PNGs out (no timestamps, no
 * randomness; node-canvas PNG encode is stable for identical pixels).
 * Re-run whenever pixelspec.mjs changes:  node scripts/render_pixels.mjs
 */

import { createCanvas } from 'canvas';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  PAL, eraPal, T, W, H, S, dict, drawMap, frames, paintWorld,
  CHARACTERS, DIRECTIONS,
  consoleDesk, reels, shelf, turntable, chair, armchair, lampPool,
  crate, ghost, puddle, windowV,
} from './lib/pixelspec.mjs';

const OUT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'public', 'world');

const png = (canvas) => canvas.toBuffer('image/png', { compressionLevel: 9, filters: canvas.PNG_ALL_FILTERS });

function renderBackground(era) {
  const cv = createCanvas(W * T, H * T);
  const c = cv.getContext('2d');
  c.imageSmoothingEnabled = false;
  paintWorld(c, eraPal(era), { era, people: false, playing: false });
  return png(cv);
}

/** 7 rows × 12 cols of 16×16: [down,left,right,up] × [idle, step L, step R]. */
function renderCharacters() {
  const cv = createCanvas(12 * 16, CHARACTERS.length * 16);
  const c = cv.getContext('2d');
  c.imageSmoothingEnabled = false;
  CHARACTERS.forEach((who, row) => {
    const dk = dict(PAL, who);
    DIRECTIONS.forEach((dir, d) => {
      // side map serves left (as-is) and right (flipped); staff fall back to down.
      const base = S[who][dir === 'left' || dir === 'right' ? 'side' : dir] || S[who].down;
      const flip = dir === 'right';
      frames(base).forEach((m, f) => drawMap(c, m, (d * 3 + f) * 16, row * 16, dk, flip));
    });
  });
  return png(cv);
}

/** The 16×16 base tiles, mirroring the design doc's drawTile() registers. */
const TILE_PAINTERS = {
  floorboard: (c, p) => { fill(c, p.floor); c.fillStyle = p.floorD; c.fillRect(0, 7, 16, 1); c.fillRect(6, 0, 1, 7); c.fillRect(11, 8, 1, 8); },
  concrete: (c, p) => { fill(c, p.conc); c.fillStyle = p.concD; c.fillRect(0, 0, 16, 1); c.fillRect(3, 8, 5, 1); },
  rug: (c, p) => { fill(c, p.rug); c.fillStyle = p.rugD; c.fillRect(4, 4, 2, 2); c.fillRect(10, 10, 2, 2); c.fillRect(0, 0, 1, 16); },
  wall: (c, p) => { fill(c, p.wallCap); c.fillStyle = p.wallFace; c.fillRect(0, 6, 16, 10); c.fillStyle = p.ink; c.fillRect(0, 5, 16, 1); c.fillRect(0, 15, 16, 1); },
  'void-rain': (c, p) => { fill(c, p.void); c.fillStyle = p.rain; c.fillRect(3, 2, 1, 4); c.fillRect(9, 9, 1, 4); },
  window: (c, p) => { fill(c, p.wallCap); windowV(c, -0.3, 0, p); },
  chair: (c, p) => { fill(c, p.floor); chair(c, 0, 0, p); },
  crate: (c, p) => { fill(c, p.floor); crate(c, 0, 0, p); },
  puddle: (c, p) => { fill(c, p.floor); puddle(c, 0, 0, p); },
  'dust-ghost': (c, p) => { fill(c, p.conc); ghost(c, 0.1, 0.2, 0.85, 0.85, p); },
  lamp: (c, p) => { fill(c, p.floor); lampPool(c, 0, 0, p); },
};
const PROP_PAINTERS = {
  'console-desk': (c, p) => consoleDesk(c, 0, 0.3, 2, p, p.evers),
  'tape-rack': (c, p) => reels(c, 0, 0.5, p),
  'record-shelf': (c, p) => shelf(c, 0, 0.4, 2, p),
  turntable: (c, p) => turntable(c, 0, 0, p, true),
  armchair: (c, p) => armchair(c, 0.2, 0.3, p),
};
function fill(c, col) { c.fillStyle = col; c.fillRect(0, 0, c.canvas.width, c.canvas.height); }

function renderStrip(painters, size) {
  const names = Object.keys(painters);
  const cv = createCanvas(names.length * size, size);
  const c = cv.getContext('2d');
  c.imageSmoothingEnabled = false;
  names.forEach((name, i) => {
    c.save();
    c.translate(i * size, 0);
    // clip so a painter can't bleed into its neighbour's cell
    c.beginPath(); c.rect(0, 0, size, size); c.clip();
    painters[name](c, PAL);
    c.restore();
  });
  return png(cv);
}

/** All assets as name -> PNG buffer. Pure — the determinism test calls this twice. */
export function renderAll() {
  return new Map([
    ['bg-era-a.png', renderBackground('A')],
    ['bg-era-b.png', renderBackground('B')],
    ['characters.png', renderCharacters()],
    ['tiles.png', renderStrip(TILE_PAINTERS, 16)],
    ['props.png', renderStrip(PROP_PAINTERS, 32)],
  ]);
}

import { pathToFileURL } from 'node:url';
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  mkdirSync(OUT_DIR, { recursive: true });
  for (const [name, buf] of renderAll()) {
    writeFileSync(path.join(OUT_DIR, name), buf);
    console.log(`world/${name}  ${buf.length} bytes`);
  }
}
