/**
 * The catalogue rail's open/closed state: a tiny persisted store. Pure
 * functions over an injected Storage so the defaults and persistence are
 * unit-testable; SplitShell wires them to localStorage + matchMedia.
 */

export type RailState = "open" | "closed";

export const RAIL_STORAGE_KEY = "afar.rail";

/** First visit: open on desktop, closed on mobile (world goes full-bleed). */
export function defaultRail(isMobile: boolean): RailState {
  return isMobile ? "closed" : "open";
}

export function toggleRail(state: RailState): RailState {
  return state === "open" ? "closed" : "open";
}

type StorageLike = Pick<Storage, "getItem" | "setItem">;

/** Stored state wins; junk or absence falls back to the viewport default. */
export function loadRail(storage: StorageLike | null, isMobile: boolean): RailState {
  try {
    const v = storage?.getItem(RAIL_STORAGE_KEY);
    if (v === "open" || v === "closed") return v;
  } catch {
    /* private mode etc. — the default carries it */
  }
  return defaultRail(isMobile);
}

export function saveRail(storage: StorageLike | null, state: RailState): void {
  try {
    storage?.setItem(RAIL_STORAGE_KEY, state);
  } catch {
    /* nothing to do; the session keeps its in-memory state */
  }
}
