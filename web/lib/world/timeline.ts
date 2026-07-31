/**
 * The world's timeline: the First Contact set (release 0002) compiled into
 * a loop of world behaviour. NOTHING here is invented — every speech bubble
 * is a line an act actually wrote during the logged session, and every
 * listening event mirrors a logged perception: in a "contact" set each act
 * heard the others' previous-round takes, and the kernel wrote an
 * influence edge for it. The world just acts that record out.
 *
 * Source data: the release row's provenance metadata (Neon release 0002 —
 * artifactsByRound, lines, influenceRawByRound) plus the per-round lines
 * from the run's release record, compiled into fixtures/timeline-source.json
 * by scripts/compile_timeline.mjs. The compile itself is pure and tested.
 */

export const PLAYERS = ["silt", "rust", "keep"] as const;
export type WorldActId = (typeof PLAYERS)[number];

const INITIALS: Record<WorldActId, string> = { silt: "DM", rust: "RP", keep: "EL" };

/** The release-row-shaped input the compiler reads (fixture or Neon). */
export interface TimelineSource {
  releaseId: string;
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

export type WorldEvent = RoundEvent | ListeningEvent;

export interface WorldTimeline {
  releaseId: string;
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

/** Time compression: a logged round plays as ~22s of ambience, a listen as ~26s. */
export const ROUND_SECONDS = 22;
export const LISTEN_SECONDS = 26;

/**
 * Between round r and r+1 one act is staged walking to the archive (they
 * all listened, per the log; the stage shows one at a time). Rotation keeps
 * it deterministic and gives everyone the walk; the source they play is
 * their strongest logged pull for the next round.
 */
export function compileTimeline(src: TimelineSource): WorldTimeline {
  const events: WorldEvent[] = [];
  const rotation: WorldActId[] = ["keep", "rust", "silt"];
  let t = 0;

  for (let r = 0; r < src.rounds; r++) {
    const lines = src.linesByRound[r];
    if (!lines) throw new Error(`timeline source is missing lines for round ${r}`);
    events.push({ kind: "round", t, duration: ROUND_SECONDS, round: r, lines });
    t += ROUND_SECONDS;

    if (r === src.rounds - 1) break;
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

/** "MM:SS" for the world's loop clock (the design's event-log clock format). */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
