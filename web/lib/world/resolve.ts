/**
 * One resolve map: stable entity id → { right-pane route, world target }.
 * The world target is where the left camera flies when the entity is
 * selected on the right (tile coords; the scene multiplies by tile size).
 *
 * Character positions mirror scripts/lib/pixelspec.mjs DEFAULT_PLACEMENTS
 * (the design's normal scene) — keep the numbers in sync.
 */

export interface WorldTarget {
  /** Tile coords of the camera destination (fractional tiles allowed). */
  tx: number;
  ty: number;
}

export interface ResolveEntry {
  route: string;
  target: WorldTarget;
  /** Which sprite this id wears in the world, if it is a character. */
  sprite?: "evers" | "roan" | "delta" | "producer" | "critic" | "listener" | "muse";
}

/** All seven characters, by stable entity id (CLAUDE.md: ids never rename). */
export const CHARACTER_RESOLVE: Record<string, ResolveEntry> = {
  keep: { route: "/act/keep", target: { tx: 5.5, ty: 7.5 }, sprite: "evers" },
  rust: { route: "/act/rust", target: { tx: 16, ty: 7.5 }, sprite: "roan" },
  silt: { route: "/act/silt", target: { tx: 25, ty: 7.5 }, sprite: "delta" },
  producer: { route: "/staff/producer", target: { tx: 5.5, ty: 22.5 }, sprite: "producer" },
  critic: { route: "/staff/critic", target: { tx: 10.9, ty: 18.9 }, sprite: "critic" },
  listener: { route: "/staff/listener", target: { tx: 4.9, ty: 26.7 }, sprite: "listener" },
  muse: { route: "/staff/muse", target: { tx: 2.5, ty: 23.9 }, sprite: "muse" },
};

/** Releases live in the archive: every release id resolves to the turntable. */
export const ARCHIVE_TARGET: WorldTarget = { tx: 22, ty: 23 };

/** id → route + world target; release ids ("0001", "0002", …) hit the archive. */
export function resolveWorld(id: string): ResolveEntry | null {
  if (id in CHARACTER_RESOLVE) return CHARACTER_RESOLVE[id];
  if (/^\d{4}$/.test(id)) return { route: `/release/${id}`, target: ARCHIVE_TARGET };
  return null;
}

/** Right-pane pathname → world target (camera centring on route change). */
export function routeTarget(pathname: string): WorldTarget | null {
  const act = pathname.match(/^\/(?:act|staff)\/([^/]+)/);
  if (act) return CHARACTER_RESOLVE[act[1]]?.target ?? null;
  if (/^\/release\/[^/]+/.test(pathname)) return ARCHIVE_TARGET;
  return null;
}
