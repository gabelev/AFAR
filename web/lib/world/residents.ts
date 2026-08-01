/**
 * Archive Row occupancy, resolved from data — never invented. The agents
 * table (Neon when reachable, the committed fixture otherwise) is the only
 * source of WHO lives WHERE: an agent row that names a street building
 * (`building: "res-03"`, top level or under `metadata`) makes that room
 * OCCUPIED, wearing the tenant system's one accent + one prop from the
 * same row. Rows are read tolerantly — the resident roster is imported by
 * the kernel side and its rows may carry kinds/keys this layer has never
 * seen; anything unusable simply doesn't assign a room.
 *
 * A building nobody claims renders as the registry drew it — FOR LEASE
 * stays papered over — EXCEPT a designed-occupied room whose resident
 * hasn't arrived in the data (vess before the roster import): that renders
 * MOVE-IN READY per the tenant template. Nothing invented: no resident row,
 * no resident.
 */

import type { StreetBuilding, TenantProp } from "@/lib/world/geometry";

/** One resolved building for the world: what the street actually shows. */
export interface BuildingState {
  id: string;
  status: "lease" | "ready" | "occupied";
  resident: { id: string; name: string } | null;
  /** Tenant accent (hex) — meaningful only when occupied. */
  accent: string;
  accentD: string;
  prop: TenantProp | null;
}

/** The guest accent pair (the design's tenant default — Vess Camber's violet). */
export const GUEST_ACCENT = "#8a6f9e";
export const GUEST_ACCENT_DARK = "#5e4a6c";

const HEX = /^#[0-9a-f]{6}$/i;
const BUILDING_ID = /^res-\d{2}$/;

interface ResidentRow {
  id: string;
  name: string;
  building: string;
  accent: string;
  accentD: string;
  prop: TenantProp | null;
}

/** Tolerant read of one agent row; null unless it names a street building. */
function residentFromRow(row: unknown): ResidentRow | null {
  if (typeof row !== "object" || row === null) return null;
  const r = row as Record<string, unknown>;
  const meta = (typeof r.metadata === "object" && r.metadata !== null ? r.metadata : {}) as Record<
    string,
    unknown
  >;
  // the kernel-side roster import nests its address as resident.building
  const nested = (typeof r.resident === "object" && r.resident !== null ? r.resident : {}) as Record<
    string,
    unknown
  >;
  const building = [r.building, meta.building, nested.building].find(
    (b): b is string => typeof b === "string" && BUILDING_ID.test(b),
  );
  if (!building) return null;
  const id = typeof r.id === "string" && r.id ? r.id : null;
  if (!id) return null;
  const name =
    [r.displayName, r.name, meta.displayName].find(
      (n): n is string => typeof n === "string" && n.length > 0,
    ) ?? id;
  const accent = [r.accent, meta.accent].find(
    (a): a is string => typeof a === "string" && HEX.test(a),
  );
  const accentD = [r.accentDark, meta.accentDark].find(
    (a): a is string => typeof a === "string" && HEX.test(a),
  );
  const propRaw = [r.prop, meta.prop].find((p) => p === "amp" || p === "reels") as
    | TenantProp
    | undefined;
  return {
    id,
    name,
    building,
    accent: accent ?? GUEST_ACCENT,
    accentD: accentD ?? GUEST_ACCENT_DARK,
    prop: propRaw ?? null,
  };
}

/**
 * Resolve every registry building against the agent rows. First claimant
 * wins a contested room (rows arrive in table order — stable, logged).
 */
export function resolveBuildings(
  buildings: readonly Pick<StreetBuilding, "id" | "status">[],
  agentRows: readonly unknown[],
): BuildingState[] {
  const byBuilding = new Map<string, ResidentRow>();
  for (const row of agentRows) {
    const resident = residentFromRow(row);
    if (resident && !byBuilding.has(resident.building)) {
      byBuilding.set(resident.building, resident);
    }
  }
  return buildings.map((b) => {
    const resident = byBuilding.get(b.id);
    if (resident) {
      return {
        id: b.id,
        status: "occupied",
        resident: { id: resident.id, name: resident.name },
        accent: resident.accent,
        accentD: resident.accentD,
        prop: resident.prop,
      };
    }
    return {
      id: b.id,
      // a designed-occupied room with no resident in the data is move-in
      // ready — the tenant hasn't arrived, so nothing claims otherwise
      status: b.status === "lease" ? "lease" : "ready",
      resident: null,
      accent: GUEST_ACCENT,
      accentD: GUEST_ACCENT_DARK,
      prop: null,
    };
  });
}

/** The building's DOM name plate, in the room-label register. */
export function buildingLabelText(state: BuildingState): string {
  const number = state.id.replace(/^res-0?/, "").padStart(2, "0");
  if (state.status === "occupied" && state.resident) {
    return `RES ${number} · ${state.resident.name.toUpperCase()}`;
  }
  return state.status === "lease" ? `RES ${number} · FOR LEASE` : `RES ${number} · MOVE-IN READY`;
}
