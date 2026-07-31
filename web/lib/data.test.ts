import { describe, expect, it } from "vitest";
import {
  AgentSchema,
  PLAYER_IDS,
  ReleaseSchema,
  STAFF_IDS,
  TapeSchema,
  TrackSchema,
  fixtureAgents,
  fixtureReleases,
  fixtureTracks,
  resolveSingle,
  resolveTapeForRelease,
  resolveTapesForAgent,
  rosterSections,
  tapeNumber,
  tapeStatusLine,
  type Release,
  type Tape,
  type Track,
} from "./data";

/** Fixtures are the zero-env data source; if they drift, every page drifts. */

describe("agents fixture", () => {
  it("contains exactly the eight stable public entity ids", () => {
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

describe("imported acts (the town)", () => {
  const importRow: Record<string, unknown> = {
    id: "hohlraum",
    kind: "player",
    name: "HOHLRAUM",
    displayName: "HOHLRAUM",
    role: "Act — the cold",
    stance: "What survives a cold room is true.",
    description: ["A recluse in a Berlin water tower."],
    bio: "A recluse in a Berlin water tower.",
    palette: {
      pristineLofi: 0.35,
      sparseDense: -0.3,
      coldWarm: -0.8,
      improvisedStructured: 0.4,
      loudQuiet: -0.1,
      organicSynthetic: 0.3,
      darkHopeful: -0.6,
    },
    imageUrl: "/api/media/abc",
    coverUrl: "/api/media/def",
    genreLine: "dub techno · 2020s",
    descriptor: "Cold, dark dub techno",
    resident: { origin: "tunz", building: "res-01" },
    album: { id: "T-hohlraum", title: "Standpipe", description: "A ten-chamber descent." },
  };

  it("parses the full import row shape the roster script writes", () => {
    const parsed = AgentSchema.parse(importRow);
    expect(parsed.resident).toEqual({ origin: "tunz", building: "res-01" });
    expect(parsed.coverUrl).toBe("/api/media/def");
    expect(parsed.album?.id).toBe("T-hohlraum");
    expect(parsed.genreLine).toBe("dub techno · 2020s");
  });

  it("keeps parsing rows without any of the new fields (house acts, staff)", () => {
    for (const agent of fixtureAgents) {
      const parsed = AgentSchema.parse(agent);
      expect(parsed.resident).toBeUndefined();
      expect(parsed.coverUrl).toBeNull();
    }
  });

  it("splits the roster into house / residents / in town by the resident block", () => {
    const inTownRow = AgentSchema.parse({
      ...importRow,
      id: "josie-ryland",
      resident: { origin: "tunz", building: null },
    });
    const agents = [...fixtureAgents, AgentSchema.parse(importRow), inTownRow];
    const { house, residents, inTown } = rosterSections(agents);
    expect(house.map((a) => a.id).sort()).toEqual([...PLAYER_IDS].sort());
    expect(residents.map((a) => a.id)).toEqual(["hohlraum"]);
    expect(inTown.map((a) => a.id)).toEqual(["josie-ryland"]);
    // staff never appear in any roster section
    for (const section of [house, residents, inTown]) {
      for (const a of section) expect(a.kind).toBe("player");
    }
  });

  it("parses import tracks (releaseId T-<slug>, no releases row required)", () => {
    const parsed = TrackSchema.parse({
      id: "T-hohlraum-1",
      releaseId: "T-hohlraum",
      agentId: "hohlraum",
      title: "Tank at Four AM",
      durationSec: 31,
      audioUrl: "/api/media/0ff",
    });
    expect(parsed.releaseId).toBe("T-hohlraum");
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

  it("parses the Listener's valence when present, tolerates its absence, refuses junk", () => {
    // Pre-Listener rows (all current fixtures) carry no reactionValence.
    const base: Record<string, unknown> = { ...fixtureReleases[0] };
    delete base.reactionValence;
    expect(ReleaseSchema.parse(base).reactionValence).toBeUndefined();
    // A Listener-enriched row carries the one-word verdict.
    expect(ReleaseSchema.parse({ ...base, reactionValence: "mixed" }).reactionValence).toBe("mixed");
    // The valence vocabulary is closed — anything else is a publish bug.
    expect(() => ReleaseSchema.parse({ ...base, reactionValence: "lukewarm" })).toThrow();
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

// --- the vault: session tapes (kind "tape", series TAPE-NNNN) -----------------

const tapeRow = {
  id: "0002",
  kind: "tape",
  title: "The Lab Session",
  runId: "20260731-191956-set-0002-parallel",
  releaseId: null,
  date: "2026-07-31",
  condition: "parallel",
  rounds: 8,
  status: "rejected",
  placement: "standalone",
  arc: "Eight rounds side by side; nothing converged, everything survived.",
  linerNotes: "Nothing was released from this session. The tape is all there is.",
  vetoNote: "No release from this set. Nothing cleared the panel.",
  takes: [
    {
      round: 0,
      agentId: "silt",
      title: null,
      audioUrl: "/api/media/abc",
      durationSec: 30,
      selected: false,
      line: "First coat down.",
    },
    {
      round: 0,
      agentId: "rust",
      audioUrl: "/api/media/def",
      durationSec: 30,
      selected: false,
      dissent: "the arc judge wanted this one on the release",
    },
  ],
};

describe("tapes (the vault)", () => {
  it("parses the full tape row the kernel publishes — the rejected session included", () => {
    const tape = TapeSchema.parse(tapeRow);
    expect(tape.kind).toBe("tape");
    expect(tape.releaseId).toBeNull();
    expect(tape.status).toBe("rejected");
    expect(tape.vetoNote).toContain("No release");
    expect(tape.takes).toHaveLength(2);
  });

  it("parses an unshelved tape (Archivist degraded: no placement, no notes)", () => {
    const unshelved: Record<string, unknown> = { ...tapeRow, status: "released", releaseId: "0006" };
    delete unshelved.placement;
    delete unshelved.arc;
    delete unshelved.linerNotes;
    const tape = TapeSchema.parse(unshelved);
    expect(tape.placement).toBeUndefined();
    expect(tape.linerNotes).toBeUndefined();
    expect(tape.releaseId).toBe("0006");
  });

  it("refuses a tape that claims to be something else", () => {
    expect(() => TapeSchema.parse({ ...tapeRow, kind: "release" })).toThrow();
    expect(() => TapeSchema.parse({ ...tapeRow, status: "great" })).toThrow();
  });

  it("wears the TAPE- series beside the releases' AFAR-", () => {
    expect(tapeNumber("0002")).toBe("TAPE-0002");
  });

  it("frames every status honestly, the veto most of all", () => {
    const tape = TapeSchema.parse(tapeRow);
    expect(tapeStatusLine(tape)).toContain("the Producer's veto stands");
    expect(tapeStatusLine(tape)).toContain("the tape survives");
    expect(
      tapeStatusLine(TapeSchema.parse({ ...tapeRow, status: "abandoned" })),
    ).toContain("What was played survives");
  });

  it("finds a release's companion tape and an act's shelf", () => {
    const companion = TapeSchema.parse({
      ...tapeRow,
      id: "0003",
      releaseId: "0005",
      status: "released",
      takes: [tapeRow.takes[0]], // silt only
    });
    const tapes: Tape[] = [TapeSchema.parse(tapeRow), companion];
    expect(resolveTapeForRelease(tapes, "0005")).toEqual(companion);
    expect(resolveTapeForRelease(tapes, "0001")).toBeNull();
    // Both tapes carry silt takes; only one carries rust.
    expect(resolveTapesForAgent(tapes, "rust").map((t) => t.id)).toEqual(["0002"]);
    expect(resolveTapesForAgent(tapes, "silt").map((t) => t.id)).toEqual(["0003", "0002"]);
  });

  it("keeps release rows back-compatible: linerNotes optional, unknown rows unchanged", () => {
    // Every deployed fixture release parses untouched (no linerNotes field).
    for (const release of fixtureReleases) {
      expect(release.linerNotes).toBeUndefined();
    }
    const withNotes = ReleaseSchema.parse({
      ...fixtureReleases[0],
      linerNotes: "What happened in the room, kept plain.",
    });
    expect(withNotes.linerNotes).toContain("kept plain");
  });
});
