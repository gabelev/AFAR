import { describe, expect, it } from "vitest";
import {
  AgentSchema,
  PLAYER_IDS,
  STAFF_IDS,
  fixtureAgents,
  fixtureReleases,
  fixtureTracks,
  resolveSingle,
  type Release,
  type Track,
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

  it("gives every agent a bio — the story under the name on their page", () => {
    for (const agent of fixtureAgents) {
      expect(agent.bio, `${agent.id} is missing a bio`).toBeTruthy();
      expect(agent.bio!.length).toBeGreaterThan(40);
    }
  });

  it("parses rows without a bio, so pre-bio DB rows still render", () => {
    const agent = fixtureAgents[0];
    const withoutBio: Record<string, unknown> = { ...agent };
    delete withoutBio.bio;
    expect(AgentSchema.parse(withoutBio).bio).toBeUndefined();
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

describe("resolveSingle", () => {
  const track = (id: string, agentId: string): Track => ({
    id,
    releaseId: id.slice(0, 4),
    agentId,
    title: id,
    durationSec: 30,
    audioUrl: null,
  });
  const release = (id: string, selections?: Record<string, string>): Release => ({
    id,
    title: id,
    era: "2020s",
    set: Number(id),
    condition: "contact",
    date: "2026-07-31",
    brief: "b",
    selection: "s",
    review: "r",
    reaction: "x",
    takeIds: [`${id}-silt`],
    selections: selections ?? {},
    influence: [],
    rationales: {},
    reviews: {},
    coverUrl: null,
  });
  const tracks = [track("0001-silt", "silt"), track("0002-silt", "silt"), track("0002-rust", "rust")];

  it("features the Producer's pick from the newest release that has one", () => {
    const releases = [release("0001"), release("0002", { silt: "0002-silt" })];
    const single = resolveSingle(releases, tracks, "silt");
    expect(single?.track.id).toBe("0002-silt");
    expect(single?.release.id).toBe("0002");
  });

  it("prefers a newer selection over an older one, regardless of input order", () => {
    const releases = [
      release("0002", { silt: "0002-silt" }),
      release("0001", { silt: "0001-silt" }),
    ];
    expect(resolveSingle(releases, tracks, "silt")?.track.id).toBe("0002-silt");
  });

  it("returns null when the Producer has never picked for this act", () => {
    const releases = [release("0001"), release("0002", { rust: "0002-rust" })];
    expect(resolveSingle(releases, tracks, "silt")).toBeNull();
  });

  it("skips a selection whose take is not in the archive", () => {
    const releases = [release("0002", { silt: "0002-missing" })];
    expect(resolveSingle(releases, tracks, "silt")).toBeNull();
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
