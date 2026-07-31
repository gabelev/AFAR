import { NextResponse } from "next/server";
import timelineSource from "@/fixtures/timeline-source.json";
import { compileTimeline, type TimelineSource } from "@/lib/world/timeline";

/**
 * The world's compiled timeline for release 0002 (the First Contact set).
 * The committed fixture carries the per-round lines from the authoritative
 * run log; when Neon is reachable, the release row's live display facts
 * (the Critic's title, era, condition) and its provenance metadata
 * (artifactsByRound, lines, influenceRawByRound) overlay the fixture, so a
 * re-published row shows through without a redeploy. Nothing is invented:
 * fixture and row both derive from the same append-only log.
 */
export async function GET() {
  const source = { ...(timelineSource as unknown as TimelineSource) };

  if (process.env.DATABASE_URL) {
    try {
      const { sql } = await import("@/lib/db");
      const result = (await sql().query("SELECT data FROM releases WHERE id = $1", [
        source.releaseId,
      ])) as { rows?: { data: RowData }[] } | { data: RowData }[];
      const rows = Array.isArray(result) ? result : (result.rows ?? []);
      const row = rows[0]?.data;
      // Same run only — a row published from a different run would not match
      // the fixture's per-round lines, so the fixture stays authoritative.
      if (row && row.metadata?.runId === (timelineSource as { runId?: string }).runId) {
        if (typeof row.title === "string") source.title = row.title;
        if (typeof row.era === "string") source.era = row.era;
        if (typeof row.condition === "string") source.condition = row.condition;
        if (typeof row.set === "number") source.set = row.set;
        if (Array.isArray(row.metadata?.artifactsByRound)) {
          source.artifactsByRound = row.metadata.artifactsByRound;
        }
        if (row.metadata?.influenceRawByRound?.intent) {
          source.intentEdgesByRound = row.metadata.influenceRawByRound.intent;
        }
      }
    } catch {
      // Table missing or Neon down — the fixture answers.
    }
  }

  return NextResponse.json(compileTimeline(source), {
    headers: {
      // Derived from an immutable log; the mutable bits (title) can lag an hour.
      "cache-control": "public, max-age=3600, stale-while-revalidate=86400",
    },
  });
}

interface RowData {
  title?: string;
  era?: string;
  condition?: string;
  set?: number;
  metadata?: {
    runId?: string;
    artifactsByRound?: TimelineSource["artifactsByRound"];
    influenceRawByRound?: { intent?: TimelineSource["intentEdgesByRound"] };
  };
}
