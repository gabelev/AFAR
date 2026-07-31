import { describe, expect, it } from "vitest";
import { ARCHIVE_TARGET, CHARACTER_RESOLVE, resolveWorld, routeTarget } from "@/lib/world/resolve";
import { fixtureAgents, fixtureReleases } from "@/lib/data";

describe("resolve map", () => {
  it("covers all seven characters (three acts + four staff)", () => {
    expect(Object.keys(CHARACTER_RESOLVE).sort()).toEqual(
      ["critic", "keep", "listener", "muse", "producer", "rust", "silt"],
    );
    for (const [id, entry] of Object.entries(CHARACTER_RESOLVE)) {
      expect(entry.route).toMatch(/^\/(act|staff)\//);
      expect(entry.sprite).toBeTruthy();
      expect(entry.target.tx).toBeGreaterThan(0);
      expect(entry.target.ty).toBeGreaterThan(0);
      expect(entry.route.endsWith(`/${id}`)).toBe(true);
    }
  });

  it("covers every agent in the fixtures", () => {
    for (const agent of fixtureAgents) {
      const entry = resolveWorld(agent.id);
      expect(entry, `no resolve entry for agent ${agent.id}`).toBeTruthy();
      expect(entry!.route).toBe(`/${agent.kind === "player" ? "act" : "staff"}/${agent.id}`);
    }
  });

  it("resolves every release to the archive turntable", () => {
    for (const release of fixtureReleases) {
      const entry = resolveWorld(release.id);
      expect(entry).toEqual({ route: `/release/${release.id}`, target: ARCHIVE_TARGET });
    }
    expect(resolveWorld("0002")).toEqual({ route: "/release/0002", target: ARCHIVE_TARGET });
  });

  it("maps right-pane routes back to world targets", () => {
    expect(routeTarget("/act/keep")).toEqual(CHARACTER_RESOLVE.keep.target);
    expect(routeTarget("/staff/muse")).toEqual(CHARACTER_RESOLVE.muse.target);
    expect(routeTarget("/release/0002")).toEqual(ARCHIVE_TARGET);
    expect(routeTarget("/")).toBeNull();
    expect(routeTarget("/act/nobody")).toBeNull();
  });
});
