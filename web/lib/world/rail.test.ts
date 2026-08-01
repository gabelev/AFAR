import { describe, expect, it } from "vitest";
import { defaultRail, loadRail, RAIL_STORAGE_KEY, saveRail, toggleRail } from "@/lib/world/rail";

function fakeStorage(initial: Record<string, string> = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
  };
}

describe("rail store", () => {
  it("defaults open on every viewport", () => {
    expect(defaultRail()).toBe("open");
    expect(loadRail(fakeStorage())).toBe("open");
    expect(loadRail(null)).toBe("open");
  });

  it("a stored state wins over the default", () => {
    expect(loadRail(fakeStorage({ [RAIL_STORAGE_KEY]: "closed" }))).toBe("closed");
    expect(loadRail(fakeStorage({ [RAIL_STORAGE_KEY]: "open" }))).toBe("open");
  });

  it("junk in storage falls back to the default", () => {
    expect(loadRail(fakeStorage({ [RAIL_STORAGE_KEY]: "sideways" }))).toBe("open");
  });

  it("a stale v1 key is ignored — the v2 default (open) wins", () => {
    // The pre-bump key: a mobile visitor's stored "closed" must not leak
    // into the new default. (rail.ts bumped the key for exactly this.)
    expect(RAIL_STORAGE_KEY).not.toBe("afar.rail");
    expect(loadRail(fakeStorage({ "afar.rail": "closed" }))).toBe("open");
  });

  it("toggle persists across a reload round-trip", () => {
    const storage = fakeStorage();
    const next = toggleRail(loadRail(storage)); // open → closed
    saveRail(storage, next);
    expect(loadRail(storage)).toBe("closed");
    saveRail(storage, toggleRail(loadRail(storage)));
    expect(loadRail(storage)).toBe("open");
  });

  it("survives a throwing storage (private mode)", () => {
    const broken = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    };
    expect(loadRail(broken)).toBe("open");
    expect(() => saveRail(broken, "closed")).not.toThrow();
  });
});
