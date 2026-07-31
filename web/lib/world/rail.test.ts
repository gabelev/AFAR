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
  it("defaults open on desktop, closed on mobile", () => {
    expect(defaultRail(false)).toBe("open");
    expect(defaultRail(true)).toBe("closed");
    expect(loadRail(fakeStorage(), false)).toBe("open");
    expect(loadRail(fakeStorage(), true)).toBe("closed");
  });

  it("a stored state wins over the viewport default", () => {
    expect(loadRail(fakeStorage({ [RAIL_STORAGE_KEY]: "closed" }), false)).toBe("closed");
    expect(loadRail(fakeStorage({ [RAIL_STORAGE_KEY]: "open" }), true)).toBe("open");
  });

  it("junk in storage falls back to the default", () => {
    expect(loadRail(fakeStorage({ [RAIL_STORAGE_KEY]: "sideways" }), false)).toBe("open");
    expect(loadRail(null, true)).toBe("closed");
  });

  it("toggle persists across a reload round-trip", () => {
    const storage = fakeStorage();
    const next = toggleRail(loadRail(storage, false)); // open → closed
    saveRail(storage, next);
    expect(loadRail(storage, false)).toBe("closed");
    saveRail(storage, toggleRail(loadRail(storage, false)));
    expect(loadRail(storage, false)).toBe("open");
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
    expect(loadRail(broken, false)).toBe("open");
    expect(() => saveRail(broken, "closed")).not.toThrow();
  });
});
