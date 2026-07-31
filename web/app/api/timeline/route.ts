import { NextResponse } from "next/server";
import timelineSource from "@/fixtures/timeline-source.json";
import {
  compileCatalogue,
  preferTimelineBlocks,
  type TimelineSource,
} from "@/lib/world/timeline";

/**
 * The world's compiled timeline: the WHOLE published catalogue as an
 * ordered sequence of set-blocks (oldest release first). When Neon is
 * reachable the route PREFERS the `timeline_source` row (id 'current') the
 * kernel's publish path writes — the same compiled shape as the committed
 * fixture, but fresh at publish time, so a new release reaches the world
 * WITHOUT a rebuild. The fixture answers whenever the row is missing,
 * malformed, or Neon is down. Each block's release row then overlays its
 * live display facts (the Critic's title, era, condition) and provenance
 * metadata (artifactsByRound, influenceRawByRound) — guarded per block by
 * that block's runId, so a row re-published from a different run leaves
 * the block authoritative. Nothing is invented: fixture, timeline row, and
 * release rows all derive from the same append-only log.
 */
export async function GET() {
  const fixture = timelineSource as unknown as {
    blocks: (TimelineSource & { runId?: string })[];
  };
  let blocks = fixture.blocks.map((b) => ({ ...b }));

  if (process.env.DATABASE_URL) {
    try {
      const { sql } = await import("@/lib/db");
      // The publish-time timeline, preferred over the build-time fixture.
      try {
        const tl = (await sql().query(
          "SELECT data FROM timeline_source WHERE id = 'current'",
        )) as { rows?: { data: unknown }[] } | { data: unknown }[];
        const tlRows = Array.isArray(tl) ? tl : (tl.rows ?? []);
        blocks = preferTimelineBlocks(fixture.blocks, tlRows[0]?.data).map((b) => ({
          ...b,
        })) as (TimelineSource & { runId?: string })[];
      } catch {
        // Table missing (pre-conductor DB) — the fixture answers.
      }
      const result = (await sql().query("SELECT id, data FROM releases WHERE id = ANY($1)", [
        blocks.map((b) => b.releaseId),
      ])) as { rows?: { id: string; data: RowData }[] } | { id: string; data: RowData }[];
      const rows = Array.isArray(result) ? result : (result.rows ?? []);
      const byId = new Map(rows.map((r) => [r.id, r.data]));
      for (const block of blocks) {
        const row = byId.get(block.releaseId);
        // Same run only — a row published from a different run would not
        // match this block's per-round lines.
        if (!row || row.metadata?.runId !== block.runId) continue;
        if (typeof row.title === "string") block.title = row.title;
        if (typeof row.era === "string") block.era = row.era;
        if (typeof row.condition === "string") block.condition = row.condition;
        if (typeof row.set === "number") block.set = row.set;
        if (Array.isArray(row.metadata?.artifactsByRound)) {
          block.artifactsByRound = row.metadata.artifactsByRound;
        }
        if (row.metadata?.influenceRawByRound?.intent) {
          block.intentEdgesByRound = row.metadata.influenceRawByRound.intent;
        }
      }
    } catch {
      // Table missing or Neon down — the fixture answers.
    }
  }

  return NextResponse.json(compileCatalogue({ blocks }), {
    headers: {
      // The timeline is dynamic now — the conductor publishes straight to
      // Neon's timeline_source row — so the world should feel current within
      // a minute of a publish. The payload is small; keep the cache short.
      "cache-control": "public, max-age=60, stale-while-revalidate=300",
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
