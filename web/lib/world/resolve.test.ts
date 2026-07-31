import { describe, expect, it } from "vitest";
import { ARCHIVE_TARGET, CHARACTER_RESOLVE, resolveWorld, routeTarget } from "@/lib/world/resolve";
import { fixtureAgents, fixtureReleases } from "@/lib/data";

describe("resolve map", () => {
  it("covers all seven characters (three acts + four staff)", () => {
    expect(Object.keys(CHARACTER_RESOLVE).sort()).toEqual(
      ["critic", "keep", "listener", "muse", "producer", "rust", "silt"],
    );
    for (const [id, entry] of Object.entries(CHARACTER_RESOLVE)) {
      expect(entry.route).toMatch(/^\/(artist|staff)\//);
      expect(entry.sprite).toBeTruthy();
      expect(entry.target.tx).toBeGreaterThan(0);
      expect(entry.target.ty).toBeGreaterThan(0);
      expect(entry.route.endsWith(`/${id}`)).toBe(true);
    }
  });

  it("covers every agent in the fixtures (the Archivist has no world body yet)", () => {
    for (const agent of fixtureAgents) {
      const entry = resolveWorld(agent.id);
      if (agent.id === "archivist") {
        // Deliberate: the Archivist's sprite/press art is flagged for the
        // next design round (DECISIONS.md) — page exists, world presence
        // later. WorldLink falls back to a plain navigation on null.
        expect(entry).toBeNull();
        continue;
      }
      expect(entry, `no resolve entry for agent ${agent.id}`).toBeTruthy();
      expect(entry!.route).toBe(`/${agent.kind === "player" ? "artist" : "staff"}/${agent.id}`);
    }
  });

  it("resolves every release to the archive turntable", () => {
    for (const release of fixtureReleases) {
      const entry = resolveWorld(release.id);
      expect(entry).toEqual({ route: `/album/afar-${release.id}`, target: ARCHIVE_TARGET });
    }
    expect(resolveWorld("0002")).toEqual({ route: "/album/afar-0002", target: ARCHIVE_TARGET });
  });

  it("maps right-pane routes back to world targets", () => {
    expect(routeTarget("/artist/keep")).toEqual(CHARACTER_RESOLVE.keep.target);
    expect(routeTarget("/staff/muse")).toEqual(CHARACTER_RESOLVE.muse.target);
    expect(routeTarget("/album/afar-0002")).toEqual(ARCHIVE_TARGET);
    expect(routeTarget("/album/t-lolgorithm")).toEqual(ARCHIVE_TARGET);
    expect(routeTarget("/")).toBeNull();
    expect(routeTarget("/artist/nobody")).toBeNull();
  });
});
