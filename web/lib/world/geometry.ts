/**
 * The runtime face of the geometry registry (web/world-geometry.json) —
 * the single source of truth for every tile coordinate, label position,
 * walk waypoint and dim rect in the world. The build pipeline
 * (scripts/lib/pixelspec.mjs) reads the same file; world_parity.test.ts
 * holds the two consumers to the design spec, pixel for pixel.
 *
 * Nothing in the world may hand-code a coordinate that exists here.
 * The world canvas IS the street ("Archive Row", 78×118 tiles): the AFAR
 * house sits on the corner and the town's two avenues of resident
 * buildings run south of it (avenue 2 staggered so its walk-out rows
 * thread avenue 1's gaps), and every walk route — act → turntable, staff
 * office → studio, resident door → archive — derives from the registry's
 * doors, corridor rows and crossing spec.
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
/** The world canvas is the whole street block (Archive Row). */
export const WORLD_W = registry.street.canvas.w * TILE; // 1248
export const WORLD_H = registry.street.canvas.h * TILE; // 1888

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

/** Walk waypoints: door offsets, corridor row, turntable approach, staff spots. */
export const WALK = registry.house.walk as unknown as {
  doorOffset: number;
  corridorY: number;
  approach: [number, number][];
  /** Where a staff walker stands just inside a studio to deliver a line. */
  studioDeliveryY: number;
  /** The archive's listening armchair — the Listener's reaction seat. */
  archiveChairStand: [number, number];
};

/** The office door column (staff walks go through it to the corridor). */
export const OFFICE_DOOR_X = doorByRoom.get("office")![0];

/**
 * Registry-routed walk paths. Every route is assembled from the same
 * pieces — a start, a door column ± the door offset, the corridor row —
 * so nothing hand-codes a waypoint that the registry doesn't carry.
 */

/** An act's walk: studio console → studio door → corridor → the turntable. */
export function studioToTurntablePath(act: string): WorldTarget[] {
  const start = PLACEMENTS[act];
  const doorX = STUDIO_DOOR_X[act];
  return [
    { tx: start.tx, ty: start.ty },
    { tx: doorX + WALK.doorOffset, ty: start.ty },
    { tx: doorX + WALK.doorOffset, ty: WALK.corridorY },
    ...WALK.approach.map(([tx, ty]) => ({ tx, ty })),
    { tx: TURNTABLE_STAND.tx, ty: TURNTABLE_STAND.ty },
  ];
}

/** A staff walk: office → office door → corridor → just inside a studio. */
export function officeToStudioPath(from: WorldTarget, act: string): WorldTarget[] {
  const ox = OFFICE_DOOR_X + WALK.doorOffset;
  const doorX = STUDIO_DOOR_X[act];
  return [
    { tx: from.tx, ty: from.ty },
    { tx: ox, ty: from.ty },
    { tx: ox, ty: WALK.corridorY },
    { tx: doorX + WALK.doorOffset, ty: WALK.corridorY },
    { tx: doorX + WALK.doorOffset, ty: WALK.studioDeliveryY },
  ];
}

/** A staff walk between studios: out to the corridor, along, back in. */
export function studioToStudioPath(fromAct: string, toAct: string): WorldTarget[] {
  const a = STUDIO_DOOR_X[fromAct] + WALK.doorOffset;
  const b = STUDIO_DOOR_X[toAct] + WALK.doorOffset;
  return [
    { tx: a, ty: WALK.studioDeliveryY },
    { tx: a, ty: WALK.corridorY },
    { tx: b, ty: WALK.corridorY },
    { tx: b, ty: WALK.studioDeliveryY },
  ];
}

/** A staff walk: office → corridor → the archive's listening armchair. */
export function officeToArchiveChairPath(from: WorldTarget): WorldTarget[] {
  const ox = OFFICE_DOOR_X + WALK.doorOffset;
  return [
    { tx: from.tx, ty: from.ty },
    { tx: ox, ty: from.ty },
    { tx: ox, ty: WALK.corridorY },
    ...WALK.approach.map(([tx, ty]) => ({ tx, ty })),
    { tx: WALK.archiveChairStand[0], ty: WALK.archiveChairStand[1] },
  ];
}

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

// ——— the street: Archive Row ———

export interface StreetBuilding {
  id: string;
  /** The DESIGN's status (the registry scene); runtime status comes from data. */
  status: string;
  resident?: string;
  shell: [number, number, number, number];
  door: [number, number];
  windows: [number, number][];
  signPlate: [number, number];
  interior: Record<string, unknown>[];
}

export const STREET_BUILDINGS = registry.street.buildings as unknown as StreetBuilding[];

/** The AFAR house's street door — east wall, straight into the archive. */
export const HOUSE_STREET_DOOR = registry.street.houseStreetDoor as unknown as {
  at: [number, number];
  h: number;
};

const STREET_TENANT = registry.street.tenant as unknown as {
  occupied: {
    consoleDesk: [number, number, number];
    chair: [number, number];
    propSlot: [number, number];
    ghost: [number, number, number, number];
    crate: [number, number];
    papers: [number, number];
    stand: [number, number];
  };
  ready: { kind: string; dx: number; dy: number; w?: number; h?: number }[];
};

/** A resident's kind-of-gear prop slot; anything else renders the dashed ghost. */
export type TenantProp = "amp" | "reels";

export interface TenantState {
  /** The room's ONE accent (console trim); a palette key or a hex colour. */
  accent: string;
  accentD: string;
  prop: TenantProp | null;
}

/**
 * The street-scale tenant template applied to one building: the interior
 * prop list (absolute tile coords, registry-prop shape) for an occupied
 * room — console in the tenant's accent, chair, the character-prop slot
 * (dashed ghost when empty), arrival crate, papers.
 */
export function tenantInterior(
  building: StreetBuilding,
  state: TenantState,
): Record<string, unknown>[] {
  const [x1, y1] = building.shell;
  const o = STREET_TENANT.occupied;
  const prop: Record<string, unknown> = state.prop
    ? { kind: state.prop, tx: x1 + o.propSlot[0], ty: y1 + o.propSlot[1] }
    : { kind: "ghost", tx: x1 + o.ghost[0], ty: y1 + o.ghost[1], w: o.ghost[2], h: o.ghost[3] };
  return [
    { kind: "consoleDesk", tx: x1 + o.consoleDesk[0], ty: y1 + o.consoleDesk[1], w: o.consoleDesk[2], acc: state.accent },
    { kind: "chair", tx: x1 + o.chair[0], ty: y1 + o.chair[1] },
    prop,
    { kind: "crate", tx: x1 + o.crate[0], ty: y1 + o.crate[1] },
    { kind: "papers", tx: x1 + o.papers[0], ty: y1 + o.papers[1] },
  ];
}

/** A move-in-ready interior: the template's dust ghosts, nothing claimed. */
export function readyInterior(building: StreetBuilding): Record<string, unknown>[] {
  const [x1, y1] = building.shell;
  return STREET_TENANT.ready.map(({ kind, dx, dy, ...rest }) => ({
    kind,
    tx: x1 + dx,
    ty: y1 + dy,
    ...rest,
  }));
}

/** Where a resident idles in their room (the template's stand offset). */
export function tenantStand(building: StreetBuilding): WorldTarget {
  const [x1, y1] = building.shell;
  return { tx: x1 + STREET_TENANT.occupied.stand[0], ty: y1 + STREET_TENANT.occupied.stand[1] };
}

const STREET_WALK = registry.street.walk as unknown as {
  path: [number, number][];
  crossing: { roadX: number; crossingY: number; tail: [number, number][] };
};

/**
 * A resident's listening walk (design 2b): out their own door, across the
 * road at the lamp, along the crossing row, through the AFAR street door
 * into the archive. Derived for ANY building; res-03's derivation equals
 * the registry's authored `street.walk.path` (street.test.ts pins it).
 */
export function streetWalkPath(building: StreetBuilding): WorldTarget[] {
  const c = STREET_WALK.crossing;
  const [dx, dy] = building.door;
  return [
    { tx: dx + 0.5, ty: dy + 1 },
    { tx: c.roadX, ty: dy + 1 },
    { tx: c.roadX, ty: c.crossingY },
    ...c.tail.map(([tx, ty]) => ({ tx, ty })),
  ];
}

const STREET_DIM = registry.street.dim as unknown as {
  rects: [number, number, number, number][];
  crossingStrip: [number, number, number, number];
};

/**
 * A street listening event's lit rects (tiles: x, y, w, h): the archive,
 * the crossing strip, and the resident's own building. Everything else on
 * the block dims. res-03's derivation equals the registry's authored
 * `street.dim.rects` (street.test.ts pins it).
 */
export function streetDimRects(building: StreetBuilding): [number, number, number, number][] {
  const [x1, y1, x2, y2] = building.shell;
  return [DIM.archive, STREET_DIM.crossingStrip, [x1, y1, x2 - x1 + 1, y2 - y1 + 1]];
}

const streetProp = (kind: string) =>
  (registry.street.props as { kind: string; tx: number; ty: number }[]).find((p) => p.kind === kind)!;

/** Fly-to targets for the street's landmarks and each resident building. */
export const STREET_TARGETS: Record<string, WorldTarget> = {
  mailbox: { tx: streetProp("mailbox").tx + 0.5, ty: streetProp("mailbox").ty + 0.5 },
  subway: { tx: streetProp("subway").tx + 1, ty: streetProp("subway").ty + 1.5 },
  ...Object.fromEntries(
    STREET_BUILDINGS.map((b) => [
      b.id,
      { tx: (b.shell[0] + b.shell[2] + 1) / 2, ty: (b.shell[1] + b.shell[3] + 1) / 2 },
    ]),
  ),
};

/**
 * A building's name-plate label anchor (2× px), on its top wall cap — the
 * same register as the house's room labels (6px in, 20px above the shell).
 */
export function buildingLabelPx(building: StreetBuilding): [number, number] {
  const [x1, y1] = building.shell;
  return [x1 * TILE * 2 + 6, y1 * TILE * 2 - 20];
}
