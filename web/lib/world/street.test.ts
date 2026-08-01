import { describe, expect, it } from "vitest";
import registry from "@/world-geometry.json";
import {
  buildingLabelPx,
  readyInterior,
  STREET_BUILDINGS,
  STREET_TARGETS,
  streetDimRects,
  streetWalkPath,
  tenantInterior,
  tenantStand,
} from "@/lib/world/geometry";

/**
 * The street's derivations are pinned to the registry's AUTHORED data: the
 * generalized walk/dim/tenant machinery, applied to the buildings the
 * design authored (RES 02 ready, RES 03 occupied by Vess), must reproduce
 * the design's own numbers exactly. If a derivation drifts, the street
 * moved and this says so.
 */

const byId = Object.fromEntries(STREET_BUILDINGS.map((b) => [b.id, b]));

describe("street derivations match the authored design data", () => {
  it("resident walk path: res-03's derivation IS the design's 2b path", () => {
    expect(streetWalkPath(byId["res-03"])).toEqual(
      registry.street.walk.path.map(([tx, ty]) => ({ tx, ty })),
    );
  });

  it("walk paths from other doors cross at the same lamp row", () => {
    const path = streetWalkPath(byId["res-01"]);
    expect(path[0]).toEqual({ tx: 40.5, ty: 6 }); // out res-01's door
    expect(path[1]).toEqual({ tx: 36, ty: 6 }); // across the road
    expect(path[2]).toEqual({ tx: 36, ty: 23.2 }); // down to the crossing row
    // then the shared tail through the AFAR street door into the archive
    expect(path.slice(3)).toEqual(
      registry.street.walk.crossing.tail.map(([tx, ty]) => ({ tx, ty })),
    );
  });

  it("street dim: res-03's lit rects ARE the design's authored rects", () => {
    expect(streetDimRects(byId["res-03"])).toEqual(registry.street.dim.rects);
  });

  it("street dim: any building's own shell stays lit", () => {
    expect(streetDimRects(byId["res-01"])[2]).toEqual([40, 2, 14, 7]);
    expect(streetDimRects(byId["res-04"])[2]).toEqual([40, 26, 14, 7]);
  });

  it("tenant template: occupied (guest accent + amp) reproduces RES 03's interior", () => {
    expect(
      tenantInterior(byId["res-03"], { accent: "guest", accentD: "guestD", prop: "amp" }),
    ).toEqual(byId["res-03"].interior);
  });

  it("tenant template: ready reproduces RES 02's dust ghosts", () => {
    expect(readyInterior(byId["res-02"])).toEqual(byId["res-02"].interior);
  });

  it("tenant template: an empty prop slot renders the dashed ghost", () => {
    const interior = tenantInterior(byId["res-01"], {
      accent: "#8a6f9e",
      accentD: "#5e4a6c",
      prop: null,
    });
    expect(interior.find((e) => e.kind === "ghost")).toEqual({
      kind: "ghost",
      tx: 49,
      ty: 3,
      w: 1,
      h: 1,
    });
    expect(interior.find((e) => e.kind === "consoleDesk")).toMatchObject({ acc: "#8a6f9e" });
  });

  it("tenant stand: res-03's derivation IS the design's vess placement", () => {
    const vess = registry.street.placements.vess;
    expect(tenantStand(byId["res-03"])).toEqual({ tx: vess.tx, ty: vess.ty });
  });

  it("fly-to targets cover the landmarks and every resident building", () => {
    expect(STREET_TARGETS.mailbox).toEqual({ tx: 32.5, ty: 20.5 });
    expect(STREET_TARGETS.subway).toEqual({ tx: 39, ty: 5.5 });
    expect(STREET_TARGETS["res-01"]).toEqual({ tx: 47, ty: 5.5 });
    expect(STREET_TARGETS["res-03"]).toEqual({ tx: 47, ty: 21.5 });
    for (const b of STREET_BUILDINGS) expect(STREET_TARGETS[b.id]).toBeDefined();
  });

  it("building name plates sit on the shell's top wall (room-label register)", () => {
    expect(buildingLabelPx(byId["res-01"])).toEqual([40 * 32 + 6, 2 * 32 - 20]);
    expect(buildingLabelPx(byId["res-04"])).toEqual([40 * 32 + 6, 26 * 32 - 20]);
  });
});

describe("the town of 25: two avenues, 28 shells, headroom", () => {
  it("28 shells: res-01..res-28, the authored four untouched", () => {
    expect(STREET_BUILDINGS.map((b) => b.id)).toEqual(
      Array.from({ length: 28 }, (_, i) => `res-${String(i + 1).padStart(2, "0")}`),
    );
    expect(byId["res-01"]).toMatchObject({ status: "lease", shell: [40, 2, 53, 8] });
    expect(byId["res-02"]).toMatchObject({ status: "ready", shell: [40, 10, 53, 16] });
    expect(byId["res-03"]).toMatchObject({ status: "occupied", resident: "vess", shell: [40, 18, 53, 24] });
    expect(byId["res-04"]).toMatchObject({ status: "lease", shell: [40, 26, 53, 32] });
  });

  it("every shell repeats the authored grammar (14×7, door y1+3, windows y1+1/y1+5, plate y1+2)", () => {
    for (const b of STREET_BUILDINGS) {
      const [x1, y1, x2, y2] = b.shell;
      expect([x2 - x1, y2 - y1], b.id).toEqual([13, 6]);
      expect(b.door, b.id).toEqual([x1, y1 + 3]);
      expect(b.windows, b.id).toEqual([
        [x1, y1 + 1],
        [x1, y1 + 5],
      ]);
      expect(b.signPlate, b.id).toEqual([x1, y1 + 2]);
    }
  });

  it("avenue 2 is staggered so every walk-out row threads avenue 1's gaps", () => {
    // a resident leaves at row door.y + 1; that horizontal leg runs west to
    // the crossing road and must never cut through another building's shell
    for (const b of STREET_BUILDINGS) {
      const exitY = b.door[1] + 1;
      for (const other of STREET_BUILDINGS) {
        if (other.id === b.id) continue;
        const [x1, y1, , y2] = other.shell;
        if (x1 >= b.shell[0]) continue; // only shells west of this one are crossed
        expect(exitY < y1 || exitY > y2, `${b.id} walks through ${other.id}`).toBe(true);
      }
    }
  });

  it("res-23..res-28 are the for-lease headroom for future arrivals", () => {
    for (let i = 23; i <= 28; i++) {
      const b = byId[`res-${i}`];
      expect(b.status, b.id).toBe("lease");
      expect(b.interior, b.id).toEqual([]);
    }
  });

  it("occupied-designed shells outside the core carry the ready dust ghosts", () => {
    for (const b of STREET_BUILDINGS) {
      if (b.status !== "ready" || b.id === "res-02") continue;
      expect(readyInterior(b), b.id).toEqual(b.interior);
    }
  });
});
