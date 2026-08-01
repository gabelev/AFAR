import { describe, expect, it } from "vitest";
import agentsFixture from "@/fixtures/agents.json";
import registry from "@/world-geometry.json";
import {
  buildingLabelText,
  GUEST_ACCENT,
  GUEST_ACCENT_DARK,
  resolveBuildings,
} from "@/lib/world/residents";

/**
 * Occupancy is data, never invention: the render matrix. A building is
 * occupied ONLY when an agent row claims it; a designed-occupied room with
 * no resident in the data (vess before the roster import) renders
 * move-in ready; FOR LEASE stays papered over until someone moves in.
 */

const BUILDINGS = registry.street.buildings;

describe("resolveBuildings: the occupancy matrix", () => {
  it("no rows claim rooms: lease stays lease, designed-occupied is move-in ready", () => {
    const states = resolveBuildings(BUILDINGS, []);
    // the whole 28-shell town, from the designed statuses alone
    expect(states.map((s) => [s.id, s.status])).toEqual(
      BUILDINGS.map((b) => [b.id, b.status === "lease" ? "lease" : "ready"]),
    );
    // vess hasn't arrived in the data — nothing invented
    expect(states.find((s) => s.id === "res-03")!.status).toBe("ready");
    for (const s of states) expect(s.resident).toBeNull();
  });

  it("the committed agents fixture houses the whole roster: 22 occupied, 6 for lease", () => {
    const states = resolveBuildings(BUILDINGS, agentsFixture);
    const occupied = states.filter((s) => s.status === "occupied");
    expect(occupied).toHaveLength(22);
    // vess keeps the authored room, with the design's tenant fields
    expect(states.find((s) => s.id === "res-03")).toMatchObject({
      status: "occupied",
      resident: { id: "vess", name: "Vess Camber" },
      accent: GUEST_ACCENT,
      accentD: GUEST_ACCENT_DARK,
      prop: "amp",
    });
    // res-01..res-22 are all lived in; the headroom shells stay papered
    for (let i = 1; i <= 22; i++) {
      expect(states.find((s) => s.id === `res-${String(i).padStart(2, "0")}`)!.status).toBe(
        "occupied",
      );
    }
    for (let i = 23; i <= 28; i++) {
      expect(states.find((s) => s.id === `res-${String(i).padStart(2, "0")}`)!.status).toBe(
        "lease",
      );
    }
    // every resident carries a real accent pair (their DNA colours, not the
    // guest fallback — vess's authored guest violet is the one exception)
    for (const s of occupied) {
      expect(s.accent).toMatch(/^#[0-9a-f]{6}$/);
      expect(s.resident!.id).toBeTruthy();
    }
  });

  it("a row with building metadata occupies its room, tenant fields honoured", () => {
    const states = resolveBuildings(BUILDINGS, [
      {
        id: "vess",
        kind: "resident",
        displayName: "Vess Camber",
        building: "res-03",
        accent: "#8a6f9e",
        accentDark: "#5e4a6c",
        prop: "amp",
      },
    ]);
    const res03 = states.find((s) => s.id === "res-03")!;
    expect(res03).toMatchObject({
      status: "occupied",
      resident: { id: "vess", name: "Vess Camber" },
      accent: "#8a6f9e",
      accentD: "#5e4a6c",
      prop: "amp",
    });
    // the rest of the row is untouched
    expect(states.find((s) => s.id === "res-01")!.status).toBe("lease");
  });

  it("building under metadata, unknown kind, missing accent: still occupies with defaults", () => {
    const states = resolveBuildings(BUILDINGS, [
      { id: "tunz-01", kind: "whatever", name: "tunz", metadata: { building: "res-01" } },
    ]);
    const res01 = states.find((s) => s.id === "res-01")!;
    expect(res01.status).toBe("occupied");
    expect(res01.resident).toEqual({ id: "tunz-01", name: "tunz" });
    expect(res01.accent).toBe(GUEST_ACCENT);
    expect(res01.accentD).toBe(GUEST_ACCENT_DARK);
    expect(res01.prop).toBeNull();
  });

  it("junk rows never claim a room", () => {
    const states = resolveBuildings(BUILDINGS, [
      null,
      42,
      { id: "x", building: "not-a-building" },
      { building: "res-02" }, // no id
      { id: "y", accent: "#8a6f9e" }, // no building
      { id: "z", building: "res-02", accent: "purple", prop: "tuba" }, // bad accent/prop
    ]);
    expect(states.find((s) => s.id === "res-02")!).toMatchObject({
      status: "occupied", // the z row's building IS valid — only its accent/prop fall back
      accent: GUEST_ACCENT,
      prop: null,
    });
    expect(states.filter((s) => s.status === "occupied")).toHaveLength(1);
  });

  it("first claimant wins a contested room", () => {
    const states = resolveBuildings(BUILDINGS, [
      { id: "first", name: "First", building: "res-04" },
      { id: "second", name: "Second", building: "res-04" },
    ]);
    expect(states.find((s) => s.id === "res-04")!.resident!.id).toBe("first");
  });
});

describe("buildingLabelText: name plates in the room-label register", () => {
  it("renders occupied / lease / ready plates", () => {
    const [lease, ready, occupied] = [
      { id: "res-01", status: "lease" as const, resident: null, accent: "", accentD: "", prop: null },
      { id: "res-03", status: "ready" as const, resident: null, accent: "", accentD: "", prop: null },
      {
        id: "res-03",
        status: "occupied" as const,
        resident: { id: "vess", name: "Vess Camber" },
        accent: "",
        accentD: "",
        prop: null,
      },
    ];
    expect(buildingLabelText(lease)).toBe("RES 01 · FOR LEASE");
    expect(buildingLabelText(ready)).toBe("RES 03 · MOVE-IN READY");
    expect(buildingLabelText(occupied)).toBe("RES 03 · VESS CAMBER");
  });
});
