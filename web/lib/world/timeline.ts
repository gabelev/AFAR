/**
 * The world's timeline: the WHOLE published catalogue compiled into one
 * loop of world behaviour, played chronologically (0002 → 0003 → 0004 →
 * repeat). NOTHING here is invented — every speech bubble is a line an act
 * actually wrote during its logged session, and every listening event
 * mirrors a logged perception: in a "contact" set each act heard the
 * others' previous-round takes, and the kernel wrote an influence edge for
 * it. In an "isolation" set nobody heard anybody — so the world stages NO
 * listening events for those sets; the acts stay in their studios, doors
 * closed. The world just acts the record out.
 *
 * Source data: one set-block per published release with run data, compiled
 * into fixtures/timeline-source.json by scripts/compile_timeline.mjs from
 * the authoritative run logs (runs/<id>/release-*.json) plus the Neon
 * release rows' display facts. The compile itself is pure and tested.
 */

export const PLAYERS = ["silt", "rust", "keep"] as const;
export type WorldActId = (typeof PLAYERS)[number];

const INITIALS: Record<WorldActId, string> = { silt: "DM", rust: "RP", keep: "EL" };

/** The release-row-shaped input for ONE set-block (fixture or Neon). */
export interface TimelineSource {
  releaseId: string;
  /** The run that produced this block's lines — with releaseId, its identity. */
  runId?: string;
  title: string;
  era: string;
  set: number;
  condition: string;
  rounds: number;
  /** Display-only stage names, keyed by stable act id. */
  names: Record<WorldActId, string>;
  /** One line per act per round — what each act said going into its take. */
  linesByRound: Record<WorldActId, string>[];
  /** Content hash of each act's take, per round (release metadata.artifactsByRound). */
  artifactsByRound: Record<WorldActId, string>[];
  /**
   * Signed intent-space influence edges per round, keyed "to<-from"
   * (release metadata.influenceRawByRound.intent). Higher = stronger pull.
   */
  intentEdgesByRound: Record<string, Record<string, number>>;
}

/** The whole catalogue: set-blocks in chronological order (oldest first). */
export interface TimelineCatalogueSource {
  blocks: TimelineSource[];
}

/**
 * Prefer the DB-published timeline over the build-time fixture. The kernel's
 * publish path (kernel/afar/publish.py, run by the conductor on the droplet)
 * writes the compiled catalogue to Neon (`timeline_source`, id 'current') —
 * the same shape compile_timeline.mjs writes to the fixture — so a publish
 * reaches production WITHOUT a rebuild. The row is validated structurally
 * before it is trusted: a malformed or empty payload (a half-written row, an
 * old schema) falls back to the committed fixture, which always works.
 */
export function preferTimelineBlocks(
  fixtureBlocks: TimelineSource[],
  dbData: unknown,
): TimelineSource[] {
  if (typeof dbData !== "object" || dbData === null) return fixtureBlocks;
  const blocks = (dbData as { blocks?: unknown }).blocks;
  if (!Array.isArray(blocks) || blocks.length === 0) return fixtureBlocks;
  const ok = blocks.every((b: unknown) => {
    if (typeof b !== "object" || b === null) return false;
    const block = b as Record<string, unknown>;
    return (
      typeof block.releaseId === "string" &&
      typeof block.title === "string" &&
      typeof block.era === "string" &&
      typeof block.set === "number" &&
      typeof block.condition === "string" &&
      typeof block.rounds === "number" &&
      typeof block.names === "object" &&
      block.names !== null &&
      Array.isArray(block.linesByRound) &&
      block.linesByRound.length === block.rounds &&
      Array.isArray(block.artifactsByRound) &&
      typeof block.intentEdgesByRound === "object" &&
      block.intentEdgesByRound !== null
    );
  });
  return ok ? (blocks as TimelineSource[]) : fixtureBlocks;
}

export interface RoundEvent {
  kind: "round";
  /** Loop-clock seconds at which the event starts. */
  t: number;
  duration: number;
  round: number;
  /** Each act's logged line for this round — their speech bubble. */
  lines: Record<WorldActId, string>;
}

export interface ListeningEvent {
  kind: "listening";
  t: number;
  duration: number;
  /** Who walks to the archive to listen. */
  actor: WorldActId;
  /** Whose take is on the turntable. */
  source: WorldActId;
  /** The round the played take was recorded in (0-based, as logged). */
  playedRound: number;
  /** Bubble at the turntable, e.g. `EL  playing AFAR-0002 — <title> · Roan Patina's take · round 2`. */
  logLine: string;
  /** Written on needle-up, e.g. `AFAR-0002 → Evers Lane · round 3`. */
  edgeLine: string;
}

/** The beat between set-blocks: the world announces the next record. */
export interface TransitionEvent {
  kind: "transition";
  t: number;
  duration: number;
  /** e.g. `NEXT: AFAR-0004 · THREE ROOMS, NO DOORS`. */
  caption: string;
  /** The rail's NOW line for the beat, e.g. `next: AFAR-0004 · Three Rooms, No Doors`. */
  nowLine: string;
}

export type WorldEvent = RoundEvent | ListeningEvent | TransitionEvent;

/** A catalogue event knows which set-block it belongs to. */
export type CatalogueEvent = WorldEvent & { block: number };

export interface WorldTimeline {
  releaseId: string;
  runId?: string;
  catalogueNo: string;
  title: string;
  era: string;
  set: number;
  condition: string;
  names: Record<WorldActId, string>;
  events: WorldEvent[];
  /** Total loop length in seconds; the world wraps its clock modulo this. */
  loopDuration: number;
}

/** Per-block display facts the world reads while a block is playing. */
export interface SetBlockMeta {
  releaseId: string;
  /** Block identity for the live diff is releaseId + runId (see live.ts). */
  runId?: string;
  catalogueNo: string;
  title: string;
  era: string;
  set: number;
  condition: string;
  /** Plain-language condition caption, e.g. `RECORDED ALONE — NO ONE HEARS ANYONE`. */
  conditionLine: string;
  names: Record<WorldActId, string>;
}

/** The compiled catalogue: one flat event stream over one continuous clock. */
export interface WorldCatalogue {
  blocks: SetBlockMeta[];
  events: CatalogueEvent[];
  /** Total loop length in seconds; the world wraps its clock modulo this. */
  loopDuration: number;
}

/** Time compression: a logged round plays as ~22s of ambience, a listen as ~26s. */
export const ROUND_SECONDS = 22;
export const LISTEN_SECONDS = 26;
/** The between-sets beat: long enough to read the announcement, no longer. */
export const TRANSITION_SECONDS = 8;

/**
 * Plain-language rule (DECISIONS.md): condition codes get a caption a
 * reader with no background can parse.
 */
export function conditionLine(condition: string): string {
  if (condition === "contact") return "RECORDED TOGETHER — EACH ACT COULD HEAR THE OTHERS";
  if (condition === "isolation") return "RECORDED ALONE — NO ONE HEARS ANYONE";
  if (condition === "parallel") return "RECORDED SIDE BY SIDE — NO ONE COULD HEAR ANYONE";
  return condition.toUpperCase();
}

/**
 * Compile ONE set-block. Contact sets: between round r and r+1 one act is
 * staged walking to the archive (they all listened, per the log; the stage
 * shows one at a time). Rotation keeps it deterministic and gives everyone
 * the walk; the source they play is their strongest logged pull for the
 * next round. Isolation sets: doors closed — nobody heard anybody, so no
 * listening events are staged at all; the rounds play back to back.
 */
export function compileTimeline(src: TimelineSource): WorldTimeline {
  const events: WorldEvent[] = [];
  const rotation: WorldActId[] = ["keep", "rust", "silt"];
  const heardEachOther = src.condition === "contact";
  let t = 0;

  for (let r = 0; r < src.rounds; r++) {
    const lines = src.linesByRound[r];
    if (!lines) throw new Error(`timeline source is missing lines for round ${r}`);
    events.push({ kind: "round", t, duration: ROUND_SECONDS, round: r, lines });
    t += ROUND_SECONDS;

    if (!heardEachOther || r === src.rounds - 1) continue;
    const actor = rotation[r % rotation.length];
    const edges = src.intentEdgesByRound[String(r + 1)];
    if (!edges) throw new Error(`timeline source is missing edges for round ${r + 1}`);
    // The strongest logged pull INTO the actor next round = whose take they play.
    const incoming = (Object.entries(edges) as [string, number][])
      .filter(([key]) => key.startsWith(`${actor}<-`))
      .sort((a, b) => b[1] - a[1]);
    if (incoming.length === 0) throw new Error(`no incoming edges for ${actor} in round ${r + 1}`);
    const source = incoming[0][0].split("<-")[1] as WorldActId;
    if (!src.artifactsByRound[r]?.[source]) {
      throw new Error(`no logged take for ${source} in round ${r}`);
    }
    events.push({
      kind: "listening",
      t,
      duration: LISTEN_SECONDS,
      actor,
      source,
      playedRound: r,
      logLine:
        `${INITIALS[actor]}  playing AFAR-${src.releaseId} — ` +
        `${src.title.toUpperCase()} · ${src.names[source]}'s take · round ${r + 1}`,
      edgeLine: `AFAR-${src.releaseId} → ${src.names[actor]} · round ${r + 2}`,
    });
    t += LISTEN_SECONDS;
  }

  return {
    releaseId: src.releaseId,
    runId: src.runId,
    catalogueNo: `AFAR-${src.releaseId}`,
    title: src.title,
    era: src.era,
    set: src.set,
    condition: src.condition,
    names: src.names,
    events,
    loopDuration: t,
  };
}

/**
 * Compile the whole catalogue: blocks play in the given (chronological)
 * order, each preceded by a transition beat announcing it — including the
 * first, which doubles as the wrap-around beat when the loop repeats. One
 * continuous clock runs across all blocks.
 */
export function compileCatalogue(src: TimelineCatalogueSource): WorldCatalogue {
  if (src.blocks.length === 0) throw new Error("timeline catalogue has no set-blocks");
  const blocks: SetBlockMeta[] = [];
  const events: CatalogueEvent[] = [];
  let t = 0;

  src.blocks.forEach((blockSrc, i) => {
    const tl = compileTimeline(blockSrc);
    blocks.push({
      releaseId: tl.releaseId,
      runId: tl.runId,
      catalogueNo: tl.catalogueNo,
      title: tl.title,
      era: tl.era,
      set: tl.set,
      condition: tl.condition,
      conditionLine: conditionLine(tl.condition),
      names: tl.names,
    });
    events.push({
      kind: "transition",
      t,
      duration: TRANSITION_SECONDS,
      caption: `NEXT: ${tl.catalogueNo} · ${tl.title.toUpperCase()}`,
      nowLine: `next: ${tl.catalogueNo} · ${tl.title}`,
      block: i,
    });
    t += TRANSITION_SECONDS;
    for (const ev of tl.events) {
      events.push({ ...ev, t: t + ev.t, block: i });
    }
    t += tl.loopDuration;
  });

  return { blocks, events, loopDuration: t };
}

/** "MM:SS" for the world's loop clock (the design's event-log clock format). */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
