import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import registry from "@/world-geometry.json";
import spritesJson from "@/world-sprites.json";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — plain .mjs build modules, no type declarations
import { residentLook, hslToHex, fnv1a } from "./lib/dna.mjs";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — plain .mjs build modules, no type declarations
import { residentMaps, residentDict, CHEST_DOWN, CHEST_SIDE } from "./lib/spritegen.mjs";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — plain .mjs build modules, no type declarations
import { S, PAL } from "../lib/world/pixelpaint.mjs";

/**
 * The procedural residents are DERIVED, never invented: one deterministic
 * function (scripts/lib/dna.mjs) turns a roster slug + its Creative DNA
 * into a look, and the committed spec (web/world-sprites.json) plus the
 * registry's spriteOrder must both agree with that derivation exactly.
 * The sprite maps are pure transforms of the authored vess silhouette —
 * same anatomy, same outline — so the family can never drift.
 */

const ROSTER_DIR = path.resolve(__dirname, "..", "..", "kernel", "afar", "agents", "roster");
const HEX = /^#[0-9a-f]{6}$/;

interface RosterEntry {
  player_id: string;
  origin: string;
  palette: Record<string, number>;
}

const roster: RosterEntry[] = readdirSync(ROSTER_DIR)
  .filter((f) => f.endsWith(".json"))
  .sort()
  .map((f) => JSON.parse(readFileSync(path.join(ROSTER_DIR, f), "utf8")));
const imports = roster.filter((e) => e.origin === "tunz");

describe("world-sprites.json — the committed looks are the derivation", () => {
  it("covers exactly the import residents (vess is authored, not derived)", () => {
    expect(Object.keys(spritesJson).sort()).toEqual(imports.map((e) => e.player_id).sort());
    expect(Object.keys(spritesJson)).not.toContain("vess");
  });

  it("every committed look equals residentLook(slug, DNA) — rerun the generator if this splits", () => {
    for (const entry of imports) {
      const look = residentLook(entry.player_id, entry.palette);
      expect(
        (spritesJson as Record<string, unknown>)[entry.player_id],
        entry.player_id,
      ).toEqual(look);
    }
  });

  it("looks are palette-law abiding: hex accents, known variants, tenant props", () => {
    for (const [slug, look] of Object.entries(spritesJson) as [string, Record<string, unknown>][]) {
      expect(look.accent, slug).toMatch(HEX);
      expect(look.accentD, slug).toMatch(HEX);
      expect(look.hair, slug).toMatch(HEX);
      expect(["cap", "hair"], slug).toContain(look.head);
      expect(Object.keys(CHEST_DOWN), slug).toContain(look.chest);
      expect(["amp", "reels", null], slug).toContain(look.prop);
    }
  });

  it("derivation is deterministic and hash-stable (no run-to-run drift)", () => {
    const a = residentLook("assembly-ghost", imports[0].palette);
    const b = residentLook("assembly-ghost", imports[0].palette);
    expect(a).toEqual(b);
    expect(fnv1a("assembly-ghost")).toBe(fnv1a("assembly-ghost"));
    expect(hslToHex(200, 0.3, 0.5)).toMatch(HEX);
  });
});

describe("spriteOrder — the sheet knows the whole town", () => {
  it("rows 0–7 are the designed cast, then every import slug, sorted", () => {
    expect(registry.spriteOrder.slice(0, 8)).toEqual([
      "evers", "roan", "delta", "producer", "critic", "listener", "muse", "vess",
    ]);
    expect(registry.spriteOrder.slice(8)).toEqual(Object.keys(spritesJson).sort());
  });
});

describe("residentMaps — the vess silhouette family, varied not redrawn", () => {
  const outline = (rows: string[]) => rows.map((r) => r.replace(/[^o.]/g, "x"));

  it("keeps vess's exact outline for every look variant", () => {
    for (const look of Object.values(spritesJson) as Record<string, string>[]) {
      const maps = residentMaps(look);
      for (const dir of ["down", "side", "up"] as const) {
        expect(outline(maps[dir])).toEqual(outline(S.vess[dir]));
      }
    }
  });

  it("chest + head variants land in the authored registers", () => {
    const badge = residentMaps({ head: "cap", chest: "badge" });
    expect(badge.down[9]).toBe(CHEST_DOWN.badge);
    expect(badge.side[9]).toBe(CHEST_SIDE.badge);
    expect(badge.down[2]).toBe(S.vess.down[2]); // cap keeps the coat-dark head
    const haired = residentMaps({ head: "hair", chest: "plain" });
    expect(haired.down[2]).toBe(S.vess.down[2].replace(/d/g, "h"));
    expect(haired.up[5]).toBe(S.vess.up[5].replace(/d/g, "h"));
    expect(haired.down[11]).toBe(S.vess.down[11]); // coat shading untouched
  });

  it("the dict keeps the world's constants and takes only the artist's colours", () => {
    const dk = residentDict({ accent: "#4b5598", accentD: "#2d345f", hair: "#8a7a52" });
    expect(dk).toEqual({
      o: PAL.ink, c: "#4b5598", d: "#2d345f", s: PAL.skin, h: "#8a7a52", p: PAL.paper, m: PAL.metal,
    });
  });
});
