/**
 * One resolve map: stable entity id → { right-pane route, world target }.
 * The world target is where the left camera flies when the entity is
 * selected on the right (tile coords; the scene multiplies by tile size).
 *
 * Everything here derives from the geometry registry
 * (web/world-geometry.json via lib/world/geometry.ts): a character's
 * camera anchor is its placement, centred on the sprite (+half a tile).
 */

import { ARCHIVE_TARGET, PLACEMENTS } from "@/lib/world/geometry";
import type { WorldTarget } from "@/lib/world/geometry";

export type { WorldTarget };
export { ARCHIVE_TARGET };

export interface ResolveEntry {
  route: string;
  target: WorldTarget;
  /** Which sprite this id wears in the world, if it is a character. */
  sprite?: string;
}

/** All seven characters, by stable entity id (CLAUDE.md: ids never rename). */
export const CHARACTER_RESOLVE: Record<string, ResolveEntry> = Object.fromEntries(
  Object.entries(PLACEMENTS).map(([id, p]) => [
    id,
    {
      route: `/${p.kind === "act" ? "act" : "staff"}/${id}`,
      target: { tx: p.tx + 0.5, ty: p.ty + 0.5 },
      sprite: p.sprite,
    },
  ]),
);

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
