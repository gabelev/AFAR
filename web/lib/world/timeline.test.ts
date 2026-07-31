import { describe, expect, it } from "vitest";
import committedSource from "@/fixtures/timeline-source.json";
import {
  clock,
  compileCatalogue,
  compileTimeline,
  conditionLine,
  LISTEN_SECONDS,
  preferTimelineBlocks,
  ROUND_SECONDS,
  TRANSITION_SECONDS,
  type ListeningEvent,
  type RoundEvent,
  type TimelineCatalogueSource,
  type TimelineSource,
  type TransitionEvent,
} from "@/lib/world/timeline";

const NAMES = { silt: "Delta Marlowe", rust: "Roan Patina", keep: "Evers Lane" };

/** A minimal release-row-shaped fixture: two rounds of a contact set. */
const contactBlock: TimelineSource = {
  releaseId: "0002",
  title: "First Contact",
  era: "2020s",
  set: 2,
  condition: "contact",
  rounds: 2,
  names: NAMES,
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

/** Two rounds of an isolation set: doors closed, nobody heard anybody. */
const isolationBlock: TimelineSource = {
  releaseId: "0004",
  title: "Three Rooms, No Doors",
  era: "2010s",
  set: 4,
  condition: "isolation",
  rounds: 2,
  names: NAMES,
  linesByRound: [
    { silt: "alone with the floor", rust: "alone with the tape", keep: "alone with the chord" },
    { silt: "still layering", rust: "still stripping", keep: "still holding" },
  ],
  artifactsByRound: [
    { silt: "hash-s0i", rust: "hash-r0i", keep: "hash-k0i" },
    { silt: "hash-s1i", rust: "hash-r1i", keep: "hash-k1i" },
  ],
  // The kernel still measures drift edges in isolation runs, but nobody
  // PERCEIVED anybody — the compiler must not stage listening from these.
  intentEdgesByRound: {
    "1": {
      "silt<-rust": -0.1, "silt<-keep": -0.2,
      "rust<-silt": -0.3, "rust<-keep": -0.4,
      "keep<-silt": -0.5, "keep<-rust": -0.6,
    },
  },
};

describe("compileTimeline", () => {
  const tl = compileTimeline(contactBlock);

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
    const broken = { ...contactBlock, rounds: 3 };
    expect(() => compileTimeline(broken)).toThrow(/missing (lines|edges) for round 2/);
  });

  it("isolation: doors closed — rounds only, no listening events staged", () => {
    const iso = compileTimeline(isolationBlock);
    expect(iso.events.map((e) => e.kind)).toEqual(["round", "round"]);
    expect(iso.loopDuration).toBe(2 * ROUND_SECONDS);
    // the logged lines still show; that is all that happened
    expect((iso.events[1] as RoundEvent).lines.keep).toBe("still holding");
  });
});

describe("conditionLine", () => {
  it("renders every condition in plain language", () => {
    expect(conditionLine("contact")).toBe("RECORDED TOGETHER — EACH ACT COULD HEAR THE OTHERS");
    expect(conditionLine("isolation")).toBe("RECORDED ALONE — NO ONE HEARS ANYONE");
    expect(conditionLine("parallel")).toBe("RECORDED SIDE BY SIDE — NO ONE COULD HEAR ANYONE");
  });
});

describe("compileCatalogue", () => {
  const cat = compileCatalogue({ blocks: [contactBlock, isolationBlock] });

  it("plays the blocks in order, each announced by a transition beat", () => {
    expect(cat.events.map((e) => e.kind)).toEqual([
      "transition", "round", "listening", "round", // contact block
      "transition", "round", "round", // isolation block: no listening
    ]);
    expect(cat.events.map((e) => e.block)).toEqual([0, 0, 0, 0, 1, 1, 1]);
  });

  it("announces each record with its catalogue number and title", () => {
    const transitions = cat.events.filter((e) => e.kind === "transition") as (TransitionEvent & {
      block: number;
    })[];
    expect(transitions.map((e) => e.caption)).toEqual([
      "NEXT: AFAR-0002 · FIRST CONTACT",
      "NEXT: AFAR-0004 · THREE ROOMS, NO DOORS",
    ]);
    expect(transitions[1].nowLine).toBe("next: AFAR-0004 · Three Rooms, No Doors");
  });

  it("runs one continuous clock across the blocks", () => {
    const contactLen = 2 * ROUND_SECONDS + LISTEN_SECONDS;
    expect(cat.events.map((e) => e.t)).toEqual([
      0,
      TRANSITION_SECONDS,
      TRANSITION_SECONDS + ROUND_SECONDS,
      TRANSITION_SECONDS + ROUND_SECONDS + LISTEN_SECONDS,
      TRANSITION_SECONDS + contactLen,
      2 * TRANSITION_SECONDS + contactLen,
      2 * TRANSITION_SECONDS + contactLen + ROUND_SECONDS,
    ]);
    expect(cat.loopDuration).toBe(2 * TRANSITION_SECONDS + contactLen + 2 * ROUND_SECONDS);
  });

  it("carries per-block display facts, condition in plain language", () => {
    expect(cat.blocks.map((b) => b.catalogueNo)).toEqual(["AFAR-0002", "AFAR-0004"]);
    expect(cat.blocks[0].conditionLine).toBe("RECORDED TOGETHER — EACH ACT COULD HEAR THE OTHERS");
    expect(cat.blocks[1].conditionLine).toBe("RECORDED ALONE — NO ONE HEARS ANYONE");
  });

  it("refuses an empty catalogue", () => {
    expect(() => compileCatalogue({ blocks: [] })).toThrow(/no set-blocks/);
  });

  it("compiles the committed fixture (the real catalogue, oldest first)", () => {
    const src = committedSource as unknown as TimelineCatalogueSource;
    expect(src.blocks.length).toBeGreaterThanOrEqual(2);
    const ids = src.blocks.map((b) => b.releaseId);
    expect([...ids].sort()).toEqual(ids); // chronological: catalogue order

    const real = compileCatalogue(src);
    expect(real.events.filter((e) => e.kind === "transition")).toHaveLength(src.blocks.length);
    for (const [i, blockSrc] of src.blocks.entries()) {
      const events = real.events.filter((e) => e.block === i);
      const rounds = events.filter((e) => e.kind === "round") as (RoundEvent & { block: number })[];
      const listens = events.filter((e) => e.kind === "listening") as (ListeningEvent & {
        block: number;
      })[];
      expect(rounds).toHaveLength(blockSrc.rounds);
      for (const r of rounds) {
        for (const line of Object.values(r.lines)) expect(line.length).toBeGreaterThan(0);
      }
      if (blockSrc.condition === "contact") {
        // every staged listen plays a take that exists in THIS block's log
        expect(listens).toHaveLength(blockSrc.rounds - 1);
        for (const l of listens) {
          expect(blockSrc.artifactsByRound[l.playedRound][l.source]).toBeTruthy();
          expect(l.logLine).toContain(`AFAR-${blockSrc.releaseId}`);
        }
      } else {
        expect(listens).toHaveLength(0); // doors closed
      }
    }
    // the clock never runs backwards across the whole catalogue
    for (let i = 1; i < real.events.length; i++) {
      expect(real.events[i].t).toBeGreaterThan(real.events[i - 1].t);
    }
  });
});

describe("clock", () => {
  it("formats the design's event-log clock", () => {
    expect(clock(0)).toBe("00:00");
    expect(clock(195)).toBe("03:15");
  });
});

describe("preferTimelineBlocks", () => {
  const fixture = [contactBlock];

  it("prefers a valid DB-published timeline over the fixture", () => {
    const db = { blocks: [contactBlock, isolationBlock] };
    const chosen = preferTimelineBlocks(fixture, db);
    expect(chosen).toHaveLength(2);
    expect(chosen.map((b) => b.releaseId)).toEqual(["0002", "0004"]);
  });

  it("falls back to the fixture when the row is missing or empty", () => {
    expect(preferTimelineBlocks(fixture, undefined)).toBe(fixture);
    expect(preferTimelineBlocks(fixture, null)).toBe(fixture);
    expect(preferTimelineBlocks(fixture, {})).toBe(fixture);
    expect(preferTimelineBlocks(fixture, { blocks: [] })).toBe(fixture);
    expect(preferTimelineBlocks(fixture, "not json")).toBe(fixture);
  });

  it("falls back when any block is structurally broken", () => {
    // linesByRound shorter than rounds — a half-written or mis-shaped row.
    const broken = { ...contactBlock, linesByRound: contactBlock.linesByRound.slice(0, 1) };
    expect(preferTimelineBlocks(fixture, { blocks: [broken] })).toBe(fixture);
    expect(preferTimelineBlocks(fixture, { blocks: [{ releaseId: "0009" }] })).toBe(fixture);
    // One bad block poisons the payload — all or nothing, the fixture answers.
    expect(preferTimelineBlocks(fixture, { blocks: [isolationBlock, broken] })).toBe(fixture);
  });

  it("accepts the committed fixture's own shape (the contract is shared)", () => {
    const committed = committedSource as unknown as { blocks: TimelineSource[] };
    expect(preferTimelineBlocks(fixture, committed)).toBe(committed.blocks);
  });
});
