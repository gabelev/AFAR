import { NextResponse } from "next/server";
import timelineSource from "@/fixtures/timeline-source.json";
import { compileCatalogue, type TimelineSource } from "@/lib/world/timeline";

/**
 * The world's compiled timeline: the WHOLE published catalogue as an
 * ordered sequence of set-blocks (oldest release first). The committed
 * fixture carries each block's per-round lines from the authoritative run
 * logs; when Neon is reachable, each block's release row overlays its live
 * display facts (the Critic's title, era, condition) and provenance
 * metadata (artifactsByRound, influenceRawByRound) — guarded per block by
 * that block's runId, so a row re-published from a different run leaves
 * the fixture block authoritative. Nothing is invented: fixture and rows
 * both derive from the same append-only log.
 */
export async function GET() {
  const fixture = timelineSource as unknown as {
    blocks: (TimelineSource & { runId?: string })[];
  };
  const blocks = fixture.blocks.map((b) => ({ ...b }));

  if (process.env.DATABASE_URL) {
    try {
      const { sql } = await import("@/lib/db");
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
