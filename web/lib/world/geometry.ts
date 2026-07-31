/**
 * The runtime face of the geometry registry (web/world-geometry.json) —
 * the single source of truth for every tile coordinate, label position,
 * walk waypoint and dim rect in the world. The build pipeline
 * (scripts/lib/pixelspec.mjs) reads the same file; world_parity.test.ts
 * holds the two consumers to the design spec, pixel for pixel.
 *
 * Nothing in the world may hand-code a coordinate that exists here.
 * The registry's `street` section is staged data for the street build —
 * the world still renders the house-only canvas until it lands.
 */

import registry from "@/world-geometry.json";

export type Dir = "down" | "left" | "right" | "up";

export interface Placement {
  sprite: string;
  kind: "act" | "staff";
  room: string;
  tx: number;
  ty: number;
  dir: Dir;
}

export interface WorldTarget {
  /** Tile coords of the camera destination (fractional tiles allowed). */
  tx: number;
  ty: number;
}

export const GEO = registry;

export const TILE = registry.tile;
export const WORLD_W = registry.house.canvas.w * TILE; // 528
export const WORLD_H = registry.house.canvas.h * TILE; // 544

/** Night-void margin around the building, in world px (6 tiles). */
export const CAMERA_MARGIN = registry.cameraMarginTiles * TILE;

/** Spritesheet rows (render_pixels.mjs renders in this same order). */
export const SHEET_ROW: Record<string, number> = Object.fromEntries(
  registry.spriteOrder.map((sprite, row) => [sprite, row]),
);

/** Character placements by stable entity id (sprite drawn at tx*T, ty*T - 6). */
export const PLACEMENTS = registry.house.placements as unknown as Record<string, Placement>;

const doorByRoom = new Map(registry.house.doors.map((d) => [d.room, d.at]));

/** Studio door column per act (single-tile door gaps in the corridor wall). */
export const STUDIO_DOOR_X: Record<string, number> = Object.fromEntries(
  Object.entries(PLACEMENTS)
    .filter(([, p]) => p.kind === "act")
    .map(([id, p]) => [id, doorByRoom.get(p.room)![0]]),
);

/** "studioA" -> "a": the studio letter each act records in. */
export const STUDIO_NAME: Record<string, string> = Object.fromEntries(
  Object.entries(PLACEMENTS)
    .filter(([, p]) => p.kind === "act")
    .map(([id, p]) => [id, p.room.replace(/^studio/, "").toLowerCase()]),
);

/** Where a listening act stands at the turntable (design 1b register). */
export const TURNTABLE_STAND: WorldTarget = {
  tx: registry.house.turntable.stand[0],
  ty: registry.house.turntable.stand[1],
};

/** The platter centre in world px (rings + shelf zone + arrival beat). */
export const PLATTER = {
  x: registry.house.turntable.tx * TILE + registry.house.turntable.platterOffset[0],
  y: registry.house.turntable.ty * TILE + registry.house.turntable.platterOffset[1],
};

/** Camera home for the whole-building view. */
export const HOME_CENTER: WorldTarget = {
  tx: registry.house.homeCenter[0],
  ty: registry.house.homeCenter[1],
};

/** Releases live in the archive: the camera target for every release id. */
export const ARCHIVE_TARGET: WorldTarget = {
  tx: registry.house.archiveTarget[0],
  ty: registry.house.archiveTarget[1],
};

/** Room labels on the wall caps: overlay key -> text + position (2x px). */
export const ROOM_LABELS: Record<string, { text: string; px: [number, number] }> =
  Object.fromEntries(
    registry.house.rooms
      .filter((r) => "label" in r && r.label)
      .map((r) => [
        r.id.startsWith("studio") ? r.id.replace(/^studio/, "").toLowerCase() : r.id,
        { text: r.label!.text, px: r.label!.px as [number, number] },
      ]),
  );

/** Speech-bubble anchors (2x px) per act + the turntable log line. */
export const BUBBLES = registry.house.bubbles as unknown as Record<
  string,
  { px: [number, number]; maxWidth: number }
>;

/** Walk waypoints: studio door offset, corridor row, approach to the turntable. */
export const WALK = registry.house.walk as unknown as {
  doorOffset: number;
  corridorY: number;
  approach: [number, number][];
};

/** The paper-dash path register (tile-centre dashes every 6px). */
export const DASHES = registry.house.dashes as unknown as {
  doorOffset: number;
  startY: number;
  cornerY: number;
  tail: [number, number][];
};

/** Listening-event dim: the lit rects (tiles: x, y, w, h / corridor spec). */
export const DIM = registry.house.dim as unknown as {
  archive: [number, number, number, number];
  corridor: { y: number; h: number; span: [number, number]; halfWidth: number };
};
