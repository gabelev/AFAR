import { sql } from "@/lib/db";

/** Stream audio mirrored into the media table. In fixture mode (no DATABASE_URL) there is no media. */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!process.env.DATABASE_URL) return new Response("Not found", { status: 404 });

  let rows: { content_type: string; bytes: Buffer | Uint8Array | string }[];
  try {
    const result = (await sql().query("SELECT content_type, bytes FROM media WHERE id = $1", [
      id,
    ])) as { rows?: typeof rows } | typeof rows;
    rows = Array.isArray(result) ? result : (result.rows ?? []);
  } catch {
    // Table may not exist yet — behave like an empty archive.
    return new Response("Not found", { status: 404 });
  }
  if (rows.length === 0) return new Response("Not found", { status: 404 });

  const raw = rows[0].bytes;
  // Neon returns bytea as a \x-prefixed hex string over HTTP.
  const bytes =
    typeof raw === "string" && raw.startsWith("\\x")
      ? Buffer.from(raw.slice(2), "hex")
      : Buffer.from(raw as Uint8Array);

  return new Response(new Uint8Array(bytes), {
    headers: {
      "content-type": rows[0].content_type,
      "cache-control": "public, max-age=31536000, immutable",
    },
  });
}
