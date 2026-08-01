/**
 * Procedural resident sprites — the same 16×16 grammar as the designed
 * cast (design/handoff/pixel.js: '.' none / o ink / c coat / d coat-dark /
 * s skin / h hair / p paper / m metal), built from Vess Camber's silhouette
 * (the street-resident family: capped head, coat, chest detail) with three
 * DNA-picked variations:
 *   head  — 'cap' keeps the vess coat-dark cap; 'hair' recolours the head
 *           pixels to the hair symbol (a bare head in the artist's tone);
 *   chest — row 9's detail: two pockets (vess), one pocket (evers), a
 *           metal badge, or plain coat;
 *   colours — coat/coat-dark are the artist's DNA accent pair, hair its
 *           swatch tone; ink/skin/paper/metal stay the world's.
 * Everything is a pure map transform of the authored vess maps, so the
 * anatomy (and the shared frames()/flip conventions) can never drift from
 * the designed sprites. The designed 8 + vess are untouched — this module
 * only ever ADDS rows to the sheet.
 */

import { S, PAL } from "../../lib/world/pixelpaint.mjs";

/** Row 9 (chest) variants, front and side, in the vess registers. */
export const CHEST_DOWN = {
  pockets: "...ocpcccpco....",
  pocket: "...occcpccco....",
  badge: "...occcmccco....",
  plain: "...occccccco....",
};
export const CHEST_SIDE = {
  pockets: "....ocpccco.....",
  pocket: "....ocpccco.....",
  badge: "....ocmccco.....",
  plain: "....occccco.....",
};

/** The head rows a 'hair' variant recolours (coat-dark cap → hair). */
const HEAD_LIMIT = { down: 4, side: 4, up: 7 };

/** Build one resident's {down, side, up} maps from a look. */
export function residentMaps(look) {
  const build = (dir) =>
    S.vess[dir].map((row, y) => {
      let r = row;
      if (look.head === "hair" && y < HEAD_LIMIT[dir]) r = r.replace(/d/g, "h");
      if (y === 9 && dir !== "up") {
        r = (dir === "down" ? CHEST_DOWN : CHEST_SIDE)[look.chest] ?? r;
      }
      return r;
    });
  return { down: build("down"), side: build("side"), up: build("up") };
}

/** The symbol → colour dictionary for one resident (drawMap contract). */
export function residentDict(look) {
  return {
    o: PAL.ink,
    c: look.accent,
    d: look.accentD,
    s: PAL.skin,
    h: look.hair,
    p: PAL.paper,
    m: PAL.metal,
  };
}
