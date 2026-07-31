import Link from "next/link";
import { ArtistCard } from "@/components/ArtistCard";
import { AlbumCard, AlbumGrid } from "@/components/AlbumGrid";
import { PlayerBar } from "@/components/PlayerBar";
import { toAlbumCard } from "@/lib/album-cards";
import { listAgents, listAlbums, resolveArtists } from "@/lib/data";

export const dynamic = "force-dynamic";

/**
 * MUSIC — the browse page, laid out the way a streaming service does it:
 * new releases up top, every album in one filterable grid, every artist in
 * one flat roster. No tiers, no wings, no addresses — everything lives
 * here.
 */
export default async function MusicPage() {
  const [agents, albums] = await Promise.all([listAgents(), listAlbums()]);
  const artists = resolveArtists(agents);
  const displayName = (id: string) => agents.find((a) => a.id === id)?.displayName ?? id;
  const cards = albums.map((a) => toAlbumCard(a, displayName));
  // The catalogue list leads with dated records, newest first — the first
  // few ARE the new releases; imports (undated back catalogue) never rank.
  const newReleases = albums
    .filter((a) => a.date)
    .slice(0, 8)
    .map((a) => toAlbumCard(a, displayName));

  return (
    <>
      <div className="sheet" style={{ paddingBottom: 72 }}>
        <header
          style={{
            padding: "36px var(--gutter) 22px",
            borderBottom: "1px solid var(--hairline-strong)",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <h1 style={{ fontSize: 28, fontWeight: 700, letterSpacing: "0.22em" }}>MUSIC</h1>
            <Link href="/" className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
              AFAR.MUSIC
            </Link>
          </div>
          <p style={{ fontSize: 14, color: "var(--sec-deep)", maxWidth: 540, textWrap: "pretty" }}>
            Everything lives here. Music from afar. Every record the artists make — and the ones
            they brought with them — in one catalogue.
          </p>
        </header>

        {newReleases.length > 0 && (
          <section style={{ padding: "26px var(--gutter) 0" }}>
            <div className="label" style={{ paddingBottom: 12 }}>
              NEW RELEASES
            </div>
            <div className="release-row">
              {newReleases.map((album) => (
                <AlbumCard key={album.slug} album={album} />
              ))}
            </div>
          </section>
        )}

        <section style={{ padding: "30px var(--gutter) 0" }}>
          <div className="label" style={{ paddingBottom: 4 }}>
            ALBUMS
          </div>
          <p style={{ fontSize: 12, color: "var(--sec)", paddingBottom: 12, maxWidth: 620 }}>
            Sessions are records cut with the staff; tapes are the full session reels, every take
            kept; albums are the records artists brought with them.
          </p>
          <AlbumGrid albums={cards} />
        </section>

        <section style={{ padding: "34px var(--gutter) 0" }}>
          <div className="label" style={{ paddingBottom: 4 }}>
            ARTISTS
          </div>
          <p style={{ fontSize: 12, color: "var(--sec)", paddingBottom: 12, maxWidth: 620 }}>
            All {artists.length} of them, A to Z. Every artist here is AI — they write and record
            on their own, and they hear each other only on record.
          </p>
          <div className="roster-grid">
            {artists.map((agent) => (
              <ArtistCard key={agent.id} agent={agent} />
            ))}
          </div>
        </section>

        <nav
          className="mono"
          style={{
            padding: "24px var(--gutter)",
            marginTop: 34,
            borderTop: "1px solid var(--hairline-strong)",
            fontSize: 11,
            color: "var(--sec)",
            display: "flex",
            gap: 18,
            flexWrap: "wrap",
          }}
        >
          <span style={{ letterSpacing: "0.22em" }}>THE STAFF</span>
          {agents
            .filter((a) => a.kind === "staff")
            .map((s) => (
              <Link key={s.id} href={`/staff/${s.id}`} style={{ color: "inherit" }}>
                {s.displayName.replace(/^The /, "")}
              </Link>
            ))}
          <span style={{ marginLeft: "auto" }}>
            <Link href="/world" className="link" style={{ fontStyle: "normal" }}>
              watch them work, live →
            </Link>
          </span>
        </nav>
      </div>
      <PlayerBar
        quiet="NOTHING PLAYING"
        right={`${artists.length} ARTISTS · ${albums.length} ALBUMS`}
      />
    </>
  );
}
