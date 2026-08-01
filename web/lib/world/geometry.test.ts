import { describe, expect, it } from "vitest";
import {
  ARCHIVE_TARGET,
  BUBBLES,
  CAMERA_MARGIN,
  DASHES,
  DIM,
  HOME_CENTER,
  officeToArchiveChairPath,
  officeToStudioPath,
  PLACEMENTS,
  PLATTER,
  ROOM_LABELS,
  SHEET_ROW,
  STUDIO_DOOR_X,
  STUDIO_NAME,
  studioToStudioPath,
  TILE,
  TURNTABLE_STAND,
  WALK,
  WORLD_H,
  WORLD_W,
} from "@/lib/world/geometry";

/**
 * Regression pin for the registry refactor: every value the world runtime
 * used to hand-code (createWorld.ts / resolve.ts / camera.ts before the
 * registry) must come out of the registry EXACTLY as it was. If a registry
 * edit moves the world, this is the test that says so — walks, dim rects,
 * fly-to anchors, labels and bubbles all read from these numbers.
 */

describe("geometry registry: derived values match the world as shipped", () => {
  it("canvas + camera (the world canvas is the 78×118 two-avenue town)", () => {
    expect(TILE).toBe(16);
    expect(WORLD_W).toBe(1248);
    expect(WORLD_H).toBe(1888);
    expect(CAMERA_MARGIN).toBe(96);
    expect(HOME_CENTER).toEqual({ tx: 16.5, ty: 17 });
  });

  it("spritesheet rows: the designed 8 keep their rows; every import resident has one", () => {
    // rows 0–7 are the handoff's designed cast — these NEVER move
    expect(SHEET_ROW).toMatchObject({
      evers: 0, roan: 1, delta: 2, producer: 3, critic: 4, listener: 5, muse: 6, vess: 7,
    });
    // then one row per import resident (world-sprites.json), slug-sorted
    const importRows = Object.entries(SHEET_ROW).filter(([, row]) => row >= 8);
    expect(importRows.length).toBe(21);
    const slugs = importRows.sort((a, b) => a[1] - b[1]).map(([slug]) => slug);
    expect(slugs).toEqual([...slugs].sort());
    expect(slugs).toContain("assembly-ghost");
    expect(slugs).toContain("velvet-nadia");
  });

  it("character placements (design normal scene)", () => {
    expect(PLACEMENTS.keep).toMatchObject({ sprite: "evers", tx: 5, ty: 7, dir: "up" });
    expect(PLACEMENTS.rust).toMatchObject({ sprite: "roan", tx: 15.5, ty: 7, dir: "down" });
    expect(PLACEMENTS.silt).toMatchObject({ sprite: "delta", tx: 24.5, ty: 7, dir: "down" });
    expect(PLACEMENTS.producer).toMatchObject({ tx: 5, ty: 22, dir: "up" });
    expect(PLACEMENTS.critic).toMatchObject({ tx: 10.4, ty: 18.4, dir: "down" });
    expect(PLACEMENTS.listener).toMatchObject({ tx: 4.4, ty: 26.2, dir: "down" });
    expect(PLACEMENTS.muse).toMatchObject({ tx: 2, ty: 23.4, dir: "left" });
  });

  it("studio doors + names per act", () => {
    expect(STUDIO_DOOR_X).toEqual({ keep: 6, rust: 16, silt: 26 });
    expect(STUDIO_NAME).toEqual({ keep: "a", rust: "b", silt: "c" });
  });

  it("the turntable station", () => {
    expect(TURNTABLE_STAND).toEqual({ tx: 21.4, ty: 24.6 });
    expect(PLATTER).toEqual({ x: 21 * 16 + 15, y: 22 * 16 + 14 });
    expect(ARCHIVE_TARGET).toEqual({ tx: 22, ty: 23 });
  });

  it("room labels at the design frame 1a pixel positions", () => {
    expect(ROOM_LABELS).toEqual({
      a: { text: "STUDIO A · EVERS LANE", px: [70, 70] },
      b: { text: "STUDIO B · ROAN PATINA", px: [390, 70] },
      c: { text: "STUDIO C · DELTA MARLOWE", px: [710, 70] },
      office: { text: "THE OFFICE", px: [70, 492] },
      archive: { text: "THE ARCHIVE — LISTENING ROOM", px: [486, 492] },
    });
  });

  it("speech-bubble anchors (acts + turntable + the staff's two spots)", () => {
    expect(BUBBLES).toEqual({
      keep: { px: [120, 296], maxWidth: 230 },
      rust: { px: [420, 296], maxWidth: 230 },
      silt: { px: [706, 296], maxWidth: 260 },
      turntable: { px: [500, 846], maxWidth: 300 },
      archiveChair: { px: [620, 776], maxWidth: 260 },
      window: { px: [70, 690], maxWidth: 240 },
    });
  });

  it("staff walk routes derive from the registry's doors + corridor", () => {
    // office → studio A (the Producer's direction delivery), verbatim pieces:
    expect(officeToStudioPath({ tx: 5, ty: 22 }, "keep")).toEqual([
      { tx: 5, ty: 22 },
      { tx: 6.6, ty: 22 }, // office door column 7 − 0.4
      { tx: 6.6, ty: 13 }, // down the office, through the door, to the corridor
      { tx: 5.6, ty: 13 }, // along the corridor to studio A's door column
      { tx: 5.6, ty: 9.4 }, // just inside the studio: the delivery spot
    ]);
    // studio → studio: out to the corridor, along, back in
    expect(studioToStudioPath("keep", "rust")).toEqual([
      { tx: 5.6, ty: 9.4 },
      { tx: 5.6, ty: 13 },
      { tx: 15.6, ty: 13 },
      { tx: 15.6, ty: 9.4 },
    ]);
    // office → the archive armchair (the Listener's reaction seat)
    expect(officeToArchiveChairPath({ tx: 4.4, ty: 26.2 })).toEqual([
      { tx: 4.4, ty: 26.2 },
      { tx: 6.6, ty: 26.2 },
      { tx: 6.6, ty: 13 },
      { tx: 21.9, ty: 13 },
      { tx: 21.9, ty: 16.2 },
      { tx: 25.2, ty: 24.9 },
    ]);
  });

  it("walk waypoints assemble to the shipped listening-event path", () => {
    // createWorld.walkPath("keep") before the registry, verbatim:
    const start = PLACEMENTS.keep;
    const doorX = STUDIO_DOOR_X.keep;
    const path = [
      { tx: start.tx, ty: start.ty },
      { tx: doorX + WALK.doorOffset, ty: start.ty },
      { tx: doorX + WALK.doorOffset, ty: WALK.corridorY },
      ...WALK.approach.map(([tx, ty]) => ({ tx, ty })),
      { tx: TURNTABLE_STAND.tx, ty: TURNTABLE_STAND.ty },
    ];
    expect(path).toEqual([
      { tx: 5, ty: 7 },
      { tx: 5.6, ty: 7 },
      { tx: 5.6, ty: 13 },
      { tx: 21.9, ty: 13 },
      { tx: 21.9, ty: 16.2 },
      { tx: 21.4, ty: 24.6 },
    ]);
  });

  it("dash path matches the design 1b register", () => {
    const doorX = STUDIO_DOOR_X.silt;
    const pts = [
      [doorX + DASHES.doorOffset, DASHES.startY],
      [doorX + DASHES.doorOffset, DASHES.cornerY],
      ...DASHES.tail,
    ];
    expect(pts).toEqual([
      [26.5, 12],
      [26.5, 13.5],
      [22.5, 13.5],
      [22.5, 16],
      [22.2, 21.5],
    ]);
  });

  it("dim keeps the archive + walked corridor lit (per-act corridor span)", () => {
    expect(DIM.archive).toEqual([14, 15, 18, 18]);
    for (const [act, want] of [
      ["keep", { x1: 4.5, x2: 24 }],
      ["rust", { x1: 14.5, x2: 24 }],
      ["silt", { x1: 20.5, x2: 27.5 }],
    ] as const) {
      const doorX = STUDIO_DOOR_X[act];
      const x1 = Math.min(doorX - DIM.corridor.halfWidth, DIM.corridor.span[0]);
      const x2 = Math.max(doorX + DIM.corridor.halfWidth, DIM.corridor.span[1]);
      expect({ x1, x2 }, act).toEqual(want);
    }
    expect(DIM.corridor.y).toBe(11);
    expect(DIM.corridor.h).toBe(5);
  });
});
