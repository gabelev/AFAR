/**
 * Creative-DNA → resident look, deterministically. One derivation, three
 * consumers: generate_resident_sprites.mjs (the committed sprite spec,
 * web/world-sprites.json), assign_residents.mjs (the Neon agent rows'
 * tenant fields), and the tests that pin both against this function.
 *
 * The inputs are the roster's 7-axis palette (kernel/afar/agents/roster/
 * <slug>.json) plus the slug itself; there is NO randomness — the only
 * "noise" is an FNV-1a hash of the slug, so a re-run always produces the
 * same look and a new artist never reshuffles an existing one.
 *
 * The colour language is the world's: muted mid-tone accents (the acts'
 * oxide/verdigris/ochre register, Vess's guest violet), never neon.
 *   hue        — organicSynthetic picks the family (synthetic → the
 *                slate/violet arc, organic → the oxide/ochre/verdigris
 *                earth arc, in-between → the teal middle), coldWarm slides
 *                along it, and the slug hash adds a stable ±14° of variety.
 *   saturation — 0.20..0.42 (denser, more synthetic DNA reads brighter).
 *   lightness  — 0.38..0.56 (darkHopeful; the dark trim is l×0.62).
 * Hair picks from a fixed swatch of plausible tones by slug hash. The
 * silhouette variants and the tenant prop read the DNA directly (quiet →
 * flat cap; synthetic → badge/amp; organic → reels; sparse ↔ dense →
 * plain ↔ pockets).
 */

/** FNV-1a 32-bit — tiny, stable, dependency-free. */
export function fnv1a(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** HSL → #rrggbb with plain Math.round — bit-for-bit reproducible. */
export function hslToHex(h, s, l) {
  const hue = ((h % 360) + 360) % 360;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
  const m = l - c / 2;
  const seg = Math.floor(hue / 60) % 6;
  const rgb = [
    [c, x, 0], [x, c, 0], [0, c, x], [0, x, c], [x, 0, c], [c, 0, x],
  ][seg];
  return (
    "#" +
    rgb
      .map((v) => Math.round((v + m) * 255).toString(16).padStart(2, "0"))
      .join("")
  );
}

/** Fixed hair swatch — the world's ink/wood/metal register. */
export const HAIR_TONES = ["#292319", "#4a3120", "#16140f", "#6a6f78", "#8a7a52", "#9a978c"];

const AXES = [
  "pristineLofi",
  "sparseDense",
  "coldWarm",
  "improvisedStructured",
  "loudQuiet",
  "organicSynthetic",
  "darkHopeful",
];

/**
 * The whole look for one import resident:
 *   { accent, accentD, hair, head: 'cap'|'hair', chest: 'pocket'|'pockets'|
 *     'badge'|'plain', prop: 'amp'|'reels'|null }
 * accent/accentD/prop are ALSO what assign_residents.mjs writes onto the
 * agent row (the residents.ts tenant contract); head/chest/hair drive the
 * sprite maps.
 */
export function residentLook(slug, palette) {
  const d = Object.fromEntries(AXES.map((a) => [a, Number(palette?.[a]) || 0]));
  const jitter = (fnv1a(slug) % 29) - 14; // stable ±14°
  const w = d.coldWarm;
  const os = d.organicSynthetic;
  const hue =
    os >= 0.25
      ? 200 + 60 * os - 40 * w + jitter // synthetic: slate → violet
      : os <= -0.25
        ? 65 - 50 * w - 25 * os + jitter // organic: oxide → ochre → verdigris
        : 130 - 80 * w + jitter; // in-between: the teal middle
  const sat = clamp(
    0.26 + 0.1 * Math.abs(d.sparseDense) + 0.06 * Math.max(0, d.organicSynthetic),
    0.2,
    0.42,
  );
  const lig = clamp(0.48 + 0.07 * d.darkHopeful, 0.38, 0.56);
  return {
    accent: hslToHex(hue, sat, lig),
    accentD: hslToHex(hue, Math.min(0.5, sat * 1.05), lig * 0.62),
    hair: HAIR_TONES[fnv1a(`${slug}/hair`) % HAIR_TONES.length],
    head: d.loudQuiet >= 0.3 ? "cap" : "hair",
    chest:
      d.organicSynthetic >= 0.5
        ? "badge"
        : d.sparseDense >= 0.3
          ? "pockets"
          : d.sparseDense <= -0.3
            ? "plain"
            : "pocket",
    prop: d.organicSynthetic >= 0.15 ? "amp" : d.organicSynthetic <= -0.15 ? "reels" : null,
  };
}
