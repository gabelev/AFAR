/**
 * The catalogue rail's open/closed state: a tiny persisted store. Pure
 * functions over an injected Storage so the defaults and persistence are
 * unit-testable; SplitShell wires them to localStorage.
 */

export type RailState = "open" | "closed";

/**
 * v2: the rail now defaults OPEN on every viewport (it used to default
 * closed on mobile). The key bump retires stored v1 states once, so every
 * visitor actually starts open; closing it is persisted again from there.
 */
export const RAIL_STORAGE_KEY = "afar.rail.v2";

/** The rail starts open everywhere; closing it is a stored choice. */
export function defaultRail(): RailState {
  return "open";
}

export function toggleRail(state: RailState): RailState {
  return state === "open" ? "closed" : "open";
}

type StorageLike = Pick<Storage, "getItem" | "setItem">;

/** Stored state wins; junk or absence falls back to the default. */
export function loadRail(storage: StorageLike | null): RailState {
  try {
    const v = storage?.getItem(RAIL_STORAGE_KEY);
    if (v === "open" || v === "closed") return v;
  } catch {
    /* private mode etc. — the default carries it */
  }
  return defaultRail();
}

export function saveRail(storage: StorageLike | null, state: RailState): void {
  try {
    storage?.setItem(RAIL_STORAGE_KEY, state);
  } catch {
    /* nothing to do; the session keeps its in-memory state */
  }
}
