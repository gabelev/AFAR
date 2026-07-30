import { z } from "zod";
import { ERAS, SonicPaletteSchema } from "@/lib/intent/schema";
import agentsJson from "@/fixtures/agents.json";
import releasesJson from "@/fixtures/releases.json";
import tracksJson from "@/fixtures/tracks.json";

/**
 * The archive's read layer. If DATABASE_URL is set, reads come from Neon
 * (mirroring the kernel's append-only log); otherwise — and whenever a
 * query fails, e.g. before the tables exist — everything falls back to the
 * checked-in fixtures. Every page must work with zero env vars.
 */

export const PLAYER_IDS = ["silt", "rust", "keep"] as const;
export const STAFF_IDS = ["muse", "producer", "critic", "listener"] as const;
export type PlayerId = (typeof PLAYER_IDS)[number];

export const AgentSchema = z.object({
  id: z.string().min(1),
  kind: z.enum(["player", "staff"]),
  name: z.string().min(1),
  role: z.string().min(1),
  stance: z.string().min(1),
  description: z.array(z.string().min(1)),
  palette: SonicPaletteSchema.nullable(),
});

export const TrackSchema = z.object({
  id: z.string().min(1),
  releaseId: z.string().min(1),
  agentId: z.string().min(1),
  title: z.string().min(1),
  durationSec: z.number().int().positive().nullable(),
  audioUrl: z.string().min(1).nullable(),
});

export const InfluenceEdgeSchema = z.object({
  from: z.enum(PLAYER_IDS),
  to: z.enum(PLAYER_IDS),
  weight: z.number().min(0).max(1),
});

export const ReleaseSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  era: z.enum(ERAS),
  set: z.number().int().positive(),
  condition: z.string().min(1),
  date: z.string().min(1),
  brief: z.string().min(1),
  selection: z.string().min(1),
  review: z.string().min(1),
  reaction: z.string().min(1),
  takeIds: z.array(z.string().min(1)),
  influence: z.array(InfluenceEdgeSchema),
  rationales: z.record(z.string(), z.string()),
});

export type Agent = z.infer<typeof AgentSchema>;
export type Track = z.infer<typeof TrackSchema>;
export type InfluenceEdge = z.infer<typeof InfluenceEdgeSchema>;
export type Release = z.infer<typeof ReleaseSchema>;

/** Fixtures are validated once at module load — a bad fixture fails the build/test, not a visitor. */
export const fixtureAgents: Agent[] = z.array(AgentSchema).parse(agentsJson);
export const fixtureReleases: Release[] = z.array(ReleaseSchema).parse(releasesJson);
export const fixtureTracks: Track[] = z.array(TrackSchema).parse(tracksJson);

/**
 * Thin Neon branch: run a query if DATABASE_URL is set, fall back to
 * fixtures on any failure (tables may not exist yet — no migrations ship
 * with the web layer).
 */
async function fromDb<T>(query: () => Promise<T | null>): Promise<T | null> {
  if (!process.env.DATABASE_URL) return null;
  try {
    return await query();
  } catch {
    return null;
  }
}

type JsonRow = { data: unknown };

async function dbRows(table: "agents" | "releases" | "tracks"): Promise<unknown[] | null> {
  const { sql } = await import("@/lib/db");
  const result = (await sql().query(`SELECT data FROM ${table} ORDER BY id`)) as
    | { rows?: JsonRow[] }
    | JsonRow[];
  const rows = Array.isArray(result) ? result : (result.rows ?? []);
  if (rows.length === 0) return null;
  return rows.map((r) => r.data);
}

export async function listAgents(): Promise<Agent[]> {
  const db = await fromDb(async () => {
    const rows = await dbRows("agents");
    return rows ? z.array(AgentSchema).parse(rows) : null;
  });
  return db ?? fixtureAgents;
}

export async function getAgent(id: string): Promise<Agent | null> {
  const agents = await listAgents();
  return agents.find((a) => a.id === id) ?? null;
}

export async function listReleases(): Promise<Release[]> {
  const db = await fromDb(async () => {
    const rows = await dbRows("releases");
    return rows ? z.array(ReleaseSchema).parse(rows) : null;
  });
  return db ?? fixtureReleases;
}

export async function getRelease(id: string): Promise<Release | null> {
  const releases = await listReleases();
  return releases.find((r) => r.id === id) ?? null;
}

export async function listTracks(): Promise<Track[]> {
  const db = await fromDb(async () => {
    const rows = await dbRows("tracks");
    return rows ? z.array(TrackSchema).parse(rows) : null;
  });
  return db ?? fixtureTracks;
}

export async function tracksForAgent(agentId: string): Promise<Track[]> {
  return (await listTracks()).filter((t) => t.agentId === agentId);
}

export async function tracksForRelease(release: Release): Promise<Track[]> {
  const tracks = await listTracks();
  const byId = new Map(tracks.map((t) => [t.id, t]));
  return release.takeIds
    .map((id) => byId.get(id))
    .filter((t): t is Track => t !== undefined);
}

/** Rationale quotes a player has left on releases, newest first. */
export async function rationalesForPlayer(
  agentId: string,
): Promise<{ releaseId: string; releaseTitle: string; quote: string }[]> {
  const releases = await listReleases();
  return releases
    .filter((r) => typeof r.rationales[agentId] === "string")
    .map((r) => ({ releaseId: r.id, releaseTitle: r.title, quote: r.rationales[agentId] }))
    .reverse();
}
