import { describe, expect, it } from "vitest";
import {
  AgentSchema,
  PLAYER_IDS,
  STAFF_IDS,
  fixtureAgents,
  fixtureReleases,
  fixtureTracks,
} from "./data";

/** Fixtures are the zero-env data source; if they drift, every page drifts. */

describe("agents fixture", () => {
  it("contains exactly the seven stable public entity ids", () => {
    expect(fixtureAgents.map((a) => a.id).sort()).toEqual(
      [...PLAYER_IDS, ...STAFF_IDS].sort(),
    );
  });

  it("gives every player a palette and every staff member none", () => {
    for (const agent of fixtureAgents) {
      if (agent.kind === "player") expect(agent.palette).not.toBeNull();
      else expect(agent.palette).toBeNull();
    }
  });

  it("gives every act a stage name over the stable id, and staff their title", () => {
    for (const agent of fixtureAgents) {
      expect(agent.displayName.length).toBeGreaterThan(0);
      if (agent.kind === "player") {
        // Stage name is display-only; the mineral sub-identity stays in `name`.
        expect(agent.displayName).not.toBe(agent.name);
        expect(agent.displayName).not.toBe(agent.id);
      } else {
        // Staff titles ARE the roles — no stage persona.
        expect(agent.displayName).toBe(agent.name);
      }
    }
  });

  it("falls back displayName to name, so pre-rename DB rows still parse", () => {
    const staff = fixtureAgents.find((a) => a.kind === "staff")!;
    const withoutDisplayName: Record<string, unknown> = { ...staff };
    delete withoutDisplayName.displayName;
    const parsed = AgentSchema.parse(withoutDisplayName);
    expect(parsed.displayName).toBe(staff.name);
  });

  it("keeps player palettes distinct — the silhouettes are the identities", () => {
    const players = fixtureAgents.filter((a) => a.kind === "player");
    const signatures = players.map((a) => JSON.stringify(a.palette));
    expect(new Set(signatures).size).toBe(players.length);
  });
});

describe("releases fixture", () => {
  it("references only tracks that exist", () => {
    const trackIds = new Set(fixtureTracks.map((t) => t.id));
    for (const release of fixtureReleases) {
      for (const takeId of release.takeIds) expect(trackIds.has(takeId)).toBe(true);
    }
  });

  it("has one directed influence edge per ordered player pair", () => {
    for (const release of fixtureReleases) {
      const edges = release.influence.map((e) => `${e.from}->${e.to}`);
      expect(new Set(edges).size).toBe(edges.length);
      expect(edges).toHaveLength(PLAYER_IDS.length * (PLAYER_IDS.length - 1));
      for (const e of release.influence) expect(e.from).not.toBe(e.to);
    }
  });

  it("carries a rationale from every player", () => {
    for (const release of fixtureReleases) {
      for (const id of PLAYER_IDS) {
        expect(typeof release.rationales[id]).toBe("string");
      }
    }
  });
});

describe("tracks fixture", () => {
  it("attributes every take to a player on a real release", () => {
    const releaseIds = new Set(fixtureReleases.map((r) => r.id));
    for (const track of fixtureTracks) {
      expect(PLAYER_IDS).toContain(track.agentId);
      expect(releaseIds.has(track.releaseId)).toBe(true);
    }
  });
});
