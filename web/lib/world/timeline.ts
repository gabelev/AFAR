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

/**
 * The staff's logged rows for one set, as the release record carries them
 * (selections/reviews/briefs/reactions JSONL → the record's staff block →
 * the release row's metadata). Optional throughout: a stage that degraded
 * or predates the staff simply has no entry, and the world stages nothing
 * for it — logged rows only, nothing invented.
 */
export interface TimelineStaff {
  producer?: { note?: string };
  critic?: { releaseReview?: string; actReviews?: Partial<Record<WorldActId, string>> };
  muse?: { theme?: string; text?: string };
  listener?: { valence?: string; text?: string };
}

/**
 * A LOGGED resident listening moment (a guest session's perception row):
 * a street resident crossed to the archive and played the record. No such
 * rows exist yet — the staging machinery is built and fixture-tested, and
 * activates the day guest sessions log real ones.
 */
export interface ResidentListenSource {
  /** Stable resident agent id. */
  resident: string;
  residentName: string;
  /** The street building they live in ("res-03"). */
  building: string;
  /** The logged line shown at the turntable while they listen. */
  logLine: string;
}

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
  /** The staff's logged rows for this set, when the record carries them. */
  staff?: TimelineStaff;
  /** Logged resident listening moments (guest sessions; none exist yet). */
  residentListens?: ResidentListenSource[];
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

/**
 * Set start: the Producer walks office → each studio and delivers the
 * session's direction — the previous boundary's logged Muse brief, which
 * is exactly what ProducerAgent.direct passes through as the direction.
 * Staged only when that brief was actually logged.
 */
export interface DirectionDeliveredEvent {
  kind: "direction_delivered";
  t: number;
  duration: number;
  /** The logged brief theme (the direction's headline). */
  theme: string;
  /** The bubble line shown at each studio (the theme, excerpted if long). */
  line: string;
}

/**
 * Post-set: the Critic walks to each act's studio and delivers their
 * verdict to their face — an excerpt of the logged per-act review.
 */
export interface VerdictDeliveredEvent {
  kind: "verdict_delivered";
  t: number;
  duration: number;
  /** Excerpted logged review per act; only reviewed acts get a visit. */
  reviews: Partial<Record<WorldActId, string>>;
}

/** Post-set: the Listener takes the archive armchair with the reaction. */
export interface ReactionEvent {
  kind: "reaction";
  t: number;
  duration: number;
  /** Excerpt of the Listener's logged reaction. */
  line: string;
  valence?: string;
}

/** Post-set: the Muse at the office window with the next brief's theme. */
export interface BriefEvent {
  kind: "brief";
  t: number;
  duration: number;
  theme: string;
  /** The bubble line (the theme, excerpted if long). */
  line: string;
}

/**
 * A street resident's listening event (design frame 2b): out their door,
 * across at the lamp, through the AFAR street door into the archive; the
 * block dims except the archive, the crossing, and their own building.
 * Compiled ONLY from logged resident perceptions — none exist yet.
 */
export interface StreetListeningEvent {
  kind: "street_listening";
  t: number;
  duration: number;
  resident: string;
  residentName: string;
  building: string;
  /** The logged line at the turntable. */
  logLine: string;
}

export type WorldEvent =
  | RoundEvent
  | ListeningEvent
  | TransitionEvent
  | DirectionDeliveredEvent
  | VerdictDeliveredEvent
  | ReactionEvent
  | BriefEvent
  | StreetListeningEvent;

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
/** The Producer's set-start delivery round of the studios. */
export const DIRECTION_SECONDS = 24;
/** The Critic's post-set verdict walk, per reviewed act. */
export const VERDICT_PER_ACT_SECONDS = 9;
/** The Listener's reaction in the archive armchair. */
export const REACTION_SECONDS = 14;
/** The Muse's brief at the window. */
export const BRIEF_SECONDS = 10;
/** A resident's street listening walk (door → lamp → archive → back). */
export const STREET_LISTEN_SECONDS = 30;

/**
 * A logged text as ONE bubble line: the first sentence when it fits,
 * otherwise a word-boundary clip with an ellipsis. Excerpting, never
 * rewriting — every shown word is a logged word.
 */
export function excerptLine(text: string, max = 140): string {
  const clean = text.trim().replace(/\s+/g, " ");
  const sentence = clean.match(/^.*?[.!?](?=\s|$)/)?.[0];
  if (sentence && sentence.length <= max) return sentence;
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max + 1);
  const atWord = cut.slice(0, cut.lastIndexOf(" "));
  return `${atWord.length > 0 ? atWord : clean.slice(0, max)} …`;
}

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

/** What compileCatalogue passes forward: the previous block's logged brief
 * IS this set's direction (ProducerAgent.direct passes it through). */
export interface CompileTimelineOptions {
  direction?: { theme?: string; text?: string };
}

/**
 * Compile ONE set-block. Contact sets: between round r and r+1 one act is
 * staged walking to the archive (they all listened, per the log; the stage
 * shows one at a time). Rotation keeps it deterministic and gives everyone
 * the walk; the source they play is their strongest logged pull for the
 * next round. Isolation sets: doors closed — nobody heard anybody, so no
 * listening events are staged at all; the rounds play back to back.
 *
 * Staff rows stage around the rounds, each ONLY when its row was logged:
 * the Producer's direction delivery opens the set (when the previous
 * boundary's brief exists — `opts.direction`); after the last round the
 * Critic delivers the per-act verdicts, the Listener reacts from the
 * archive armchair, and the Muse posts the next theme at the window.
 * Logged resident listening moments (none exist yet) stage last.
 */
export function compileTimeline(
  src: TimelineSource,
  opts: CompileTimelineOptions = {},
): WorldTimeline {
  const events: WorldEvent[] = [];
  const rotation: WorldActId[] = ["keep", "rust", "silt"];
  const heardEachOther = src.condition === "contact";
  let t = 0;

  const directionLine = opts.direction?.theme?.trim() || opts.direction?.text?.trim();
  if (directionLine) {
    events.push({
      kind: "direction_delivered",
      t,
      duration: DIRECTION_SECONDS,
      theme: opts.direction?.theme?.trim() || excerptLine(directionLine),
      line: excerptLine(directionLine),
    });
    t += DIRECTION_SECONDS;
  }

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

  // Post-set staff rows, in the log's own order: the Critic's verdicts,
  // the Listener's reaction, the Muse's carried-forward brief.
  const reviews = src.staff?.critic?.actReviews;
  if (reviews) {
    const excerpted: Partial<Record<WorldActId, string>> = {};
    for (const act of rotation) {
      const text = reviews[act];
      if (typeof text === "string" && text.trim().length > 0) {
        excerpted[act] = excerptLine(text);
      }
    }
    const visited = Object.keys(excerpted).length;
    if (visited > 0) {
      events.push({
        kind: "verdict_delivered",
        t,
        duration: VERDICT_PER_ACT_SECONDS * visited,
        reviews: excerpted,
      });
      t += VERDICT_PER_ACT_SECONDS * visited;
    }
  }
  const reactionText = src.staff?.listener?.text?.trim();
  if (reactionText) {
    events.push({
      kind: "reaction",
      t,
      duration: REACTION_SECONDS,
      line: excerptLine(reactionText),
      ...(src.staff?.listener?.valence ? { valence: src.staff.listener.valence } : {}),
    });
    t += REACTION_SECONDS;
  }
  const briefTheme = src.staff?.muse?.theme?.trim() || src.staff?.muse?.text?.trim();
  if (briefTheme) {
    events.push({
      kind: "brief",
      t,
      duration: BRIEF_SECONDS,
      theme: src.staff?.muse?.theme?.trim() || excerptLine(briefTheme),
      line: excerptLine(briefTheme),
    });
    t += BRIEF_SECONDS;
  }

  for (const listen of src.residentListens ?? []) {
    if (!listen.resident || !listen.building || !listen.logLine?.trim()) {
      throw new Error("resident listen row is missing its logged fields");
    }
    events.push({
      kind: "street_listening",
      t,
      duration: STREET_LISTEN_SECONDS,
      resident: listen.resident,
      residentName: listen.residentName || listen.resident,
      building: listen.building,
      logLine: listen.logLine,
    });
    t += STREET_LISTEN_SECONDS;
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
    // The previous block's logged brief is this set's direction (composed
    // at that boundary, consumed by the Producer at this set's start).
    const tl = compileTimeline(blockSrc, { direction: src.blocks[i - 1]?.staff?.muse });
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
