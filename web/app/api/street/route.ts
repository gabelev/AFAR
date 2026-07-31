import { NextResponse } from "next/server";
import agentsJson from "@/fixtures/agents.json";
import registry from "@/world-geometry.json";
import { resolveBuildings } from "@/lib/world/residents";

/**
 * Archive Row occupancy for the world: which resident buildings are
 * occupied (and by whom, with the tenant system's accent + prop), which
 * are for lease, which are move-in ready. Resolved from the agents table
 * when Neon is reachable — the resident roster is imported there by the
 * kernel side — and from the committed agents fixture otherwise. Rows are
 * read RAW (not through AgentSchema): resident rows may carry kinds and
 * keys the catalogue schema doesn't know, and a row this route can't use
 * simply doesn't assign a room. The world renders whatever the data says.
 */
export async function GET() {
  let rows: unknown[] = agentsJson as unknown[];

  if (process.env.DATABASE_URL) {
    try {
      const { sql } = await import("@/lib/db");
      const result = (await sql().query("SELECT data FROM agents ORDER BY id")) as
        | { rows?: { data: unknown }[] }
        | { data: unknown }[];
      const dbRows = Array.isArray(result) ? result : (result.rows ?? []);
      if (dbRows.length > 0) rows = dbRows.map((r) => r.data);
    } catch {
      // Table missing or Neon down — the fixture answers.
    }
  }

  return NextResponse.json(
    { buildings: resolveBuildings(registry.street.buildings, rows) },
    {
      headers: {
        // Occupancy changes when the roster does — rarely; open tabs pick
        // a new resident up on their next load.
        "cache-control": "public, max-age=300, stale-while-revalidate=600",
      },
    },
  );
}
