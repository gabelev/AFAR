import { describe, expect, it } from "vitest";
import committedSource from "@/fixtures/timeline-source.json";
import {
  clock,
  compileTimeline,
  LISTEN_SECONDS,
  ROUND_SECONDS,
  type ListeningEvent,
  type RoundEvent,
  type TimelineSource,
} from "@/lib/world/timeline";

/** A minimal release-row-shaped fixture: two rounds of a contact set. */
const fixtureRow: TimelineSource = {
  releaseId: "0002",
  title: "First Contact",
  era: "2020s",
  set: 2,
  condition: "contact",
  rounds: 2,
  names: { silt: "Delta Marlowe", rust: "Roan Patina", keep: "Evers Lane" },
  linesByRound: [
    { silt: "laying the floor", rust: "finding what is true", keep: "leaving the song where you can reach it" },
    { silt: "everything lands on my floor now", rust: "the missing half is mine", keep: "playing it again, plainly" },
  ],
  artifactsByRound: [
    { silt: "hash-s0", rust: "hash-r0", keep: "hash-k0" },
    { silt: "hash-s1", rust: "hash-r1", keep: "hash-k1" },
  ],
  intentEdgesByRound: {
    "1": {
      "silt<-rust": -0.8, "silt<-keep": -0.6,
      "rust<-silt": -0.9, "rust<-keep": -1.3,
      "keep<-silt": -0.4, "keep<-rust": -1.2,
    },
  },
};

describe("compileTimeline", () => {
  const tl = compileTimeline(fixtureRow);

  it("alternates rounds and listening events, ending on the final round", () => {
    expect(tl.events.map((e) => e.kind)).toEqual(["round", "listening", "round"]);
    expect(tl.loopDuration).toBe(2 * ROUND_SECONDS + LISTEN_SECONDS);
  });

  it("keeps the loop clock cumulative", () => {
    expect(tl.events.map((e) => e.t)).toEqual([0, ROUND_SECONDS, ROUND_SECONDS + LISTEN_SECONDS]);
  });

  it("carries each act's logged line as its bubble", () => {
    const round0 = tl.events[0] as RoundEvent;
    expect(round0.lines.rust).toBe("finding what is true");
  });

  it("stages the listening event from the logged data, inventing nothing", () => {
    const listen = tl.events[1] as ListeningEvent;
    expect(listen.actor).toBe("keep"); // rotation starts with Evers (the design's money shot)
    expect(listen.source).toBe("silt"); // keep's strongest logged pull in round 1 (-0.4)
    expect(listen.playedRound).toBe(0);
    expect(listen.logLine).toBe(
      "EL  playing AFAR-0002 — FIRST CONTACT · Delta Marlowe's take · round 1",
    );
    expect(listen.edgeLine).toBe("AFAR-0002 → Evers Lane · round 2");
  });

  it("refuses to invent a missing line", () => {
    const broken = { ...fixtureRow, rounds: 3 };
    expect(() => compileTimeline(broken)).toThrow(/missing (lines|edges) for round 2/);
  });

  it("compiles the committed fixture (the real First Contact set)", () => {
    const real = compileTimeline(committedSource as unknown as TimelineSource);
    const rounds = real.events.filter((e) => e.kind === "round");
    const listens = real.events.filter((e) => e.kind === "listening") as ListeningEvent[];
    expect(rounds).toHaveLength(6);
    expect(listens).toHaveLength(5);
    for (const r of rounds as RoundEvent[]) {
      for (const line of Object.values(r.lines)) expect(line.length).toBeGreaterThan(0);
    }
    // every staged listen plays a take that exists in the log
    const src = committedSource as unknown as TimelineSource;
    for (const l of listens) {
      expect(src.artifactsByRound[l.playedRound][l.source]).toBeTruthy();
    }
    // all three acts get a walk across the loop
    expect(new Set(listens.map((l) => l.actor)).size).toBe(3);
  });
});

describe("clock", () => {
  it("formats the design's event-log clock", () => {
    expect(clock(0)).toBe("00:00");
    expect(clock(195)).toBe("03:15");
  });
});
