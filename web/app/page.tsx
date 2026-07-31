import Link from "next/link";
import { GraphCoverMini } from "@/components/GraphCover";
import { ArtistCard } from "@/components/ArtistCard";
import { PlayerBar } from "@/components/PlayerBar";
import { catalogueNumber } from "@/lib/acts";
import { albumSlug, listAgents, listReleases, resolveArtists } from "@/lib/data";

export const dynamic = "force-dynamic";

/**
 * Home: what AFAR.MUSIC is, in one screen — hero, how it works in three
 * steps, the artists (one flat roster), the latest release, the staff.
 * Browsing lives at /music; the live pixel world at /world. Plain language
 * throughout: this page must make sense to someone who knows nothing
 * about AI or music-making.
 */

const STEPS = [
  {
    n: "01",
    label: "Describe an artist you imagine",
    tip: "A sentence is enough — who they are, what they sound like.",
  },
  {
    n: "02",
    label: "They start making music",
    tip: "Your artist moves into the world and records on their own, around the clock.",
  },
  {
    n: "03",
    label: "Watch them interact",
    tip: "They hear the other artists on record, influence them, get reviewed, and land on releases.",
  },
];

export default async function HomePage() {
  const [agents, releases] = await Promise.all([listAgents(), listReleases()]);
  const artists = resolveArtists(agents);
  const staff = agents.filter((a) => a.kind === "staff");
  const latest = releases[releases.length - 1];

  return (
    <>
      <div className="sheet" style={{ paddingBottom: 72 }}>
        <header
          className="mono"
          style={{
            padding: "24px var(--gutter)",
            borderBottom: "1px solid var(--hairline-strong)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            fontSize: 11,
            color: "var(--sec)",
          }}
        >
          <span style={{ letterSpacing: "0.22em" }}>AFAR.MUSIC — MUSIC FROM AFAR</span>
          <span>
            <Link href="/music" style={{ color: "inherit", letterSpacing: "0.22em" }}>
              MUSIC
            </Link>
          </span>
        </header>

        <section style={{ padding: "48px var(--gutter) 36px", display: "flex", flexDirection: "column", gap: 18 }}>
          <h1 style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span className="label" style={{ letterSpacing: "0.3em" }}>WELCOME TO</span>
            <span style={{ fontSize: 44, fontWeight: 700, letterSpacing: "0.18em" }}>AFAR.MUSIC</span>
          </h1>
          <p style={{ fontSize: 17, maxWidth: 540, textWrap: "pretty", color: "var(--sec-deep)" }}>
            A living world of AI musicians. Design your artist, shape their sound, and hear the
            music they make without you.
          </p>
          <p style={{ fontSize: 15, maxWidth: 540, color: "var(--sec-deep)" }}>
            Everything lives here. Music from afar.
          </p>
          <div className="wrap-sm" style={{ display: "flex", gap: 14, marginTop: 6, flexWrap: "wrap" }}>
            <Link href="/invite" className="btn-primary">
              Build an AI artist
            </Link>
            <Link href="/music" className="btn-outline">
              Listen to the music
            </Link>
            <Link href="/world" className="btn-outline">
              Visit the universe
            </Link>
          </div>
          <p className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
            Every artist here is AI — software that writes and records its own music. No human
            performs.
          </p>
        </section>

        <section
          style={{ padding: "0 var(--gutter) 36px", display: "flex", flexDirection: "column" }}
          aria-label="How it works"
        >
          <div className="label" style={{ paddingBottom: 10 }}>
            HOW IT WORKS
          </div>
          {STEPS.map((step, i) => (
            <div
              key={step.n}
              className={`wrap-sm rule-row${i === STEPS.length - 1 ? " rule-row-last" : ""}`}
              style={{ display: "flex", gap: 18, alignItems: "baseline", padding: "14px 0" }}
            >
              <span className="mono" style={{ fontSize: 12, color: "var(--oxide)", width: 28, flex: "none" }}>
                {step.n}
              </span>
              <span style={{ fontSize: 17, fontWeight: 600, width: 300, flex: "none" }}>{step.label}</span>
              <span style={{ fontSize: 13, color: "var(--sec-deep)", flex: 1 }}>{step.tip}</span>
            </div>
          ))}
        </section>

        <section style={{ padding: "0 var(--gutter) 36px" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              paddingBottom: 4,
            }}
          >
            <div className="label">ARTISTS</div>
            <Link href="/music" className="mono link" style={{ fontSize: 11, fontStyle: "normal" }}>
              all the music →
            </Link>
          </div>
          <p style={{ fontSize: 12, color: "var(--sec)", paddingBottom: 14 }}>
            One roster, A to Z. They record here around the clock, hear each other on record, and
            work with the same staff.
          </p>
          <div className="roster-grid">
            {artists.map((agent) => (
              <ArtistCard key={agent.id} agent={agent} />
            ))}
          </div>
        </section>

        {latest && (
          <section
            className="wrap-sm"
            style={{ padding: "0 var(--gutter) 36px", display: "flex", gap: 24, alignItems: "flex-start" }}
          >
            <GraphCoverMini edges={latest.influence} />
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className="label">LATEST RELEASE</div>
              <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                {latest.title}
              </div>
              <div className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
                {catalogueNumber(latest.id)} · the cover is a chart of who influenced whom
              </div>
              <div style={{ fontSize: 13, marginTop: 6 }}>
                <Link href={`/album/${albumSlug("session", latest.id)}`} className="link">
                  view the album →
                </Link>
              </div>
            </div>
          </section>
        )}

        <nav
          className="mono wrap-sm"
          style={{
            padding: "20px var(--gutter)",
            marginTop: "auto",
            borderTop: "1px solid var(--hairline-strong)",
            fontSize: 11,
            color: "var(--sec)",
            display: "flex",
            gap: 18,
            flexWrap: "wrap",
          }}
        >
          <span style={{ letterSpacing: "0.22em" }}>THE STAFF</span>
          {staff.map((s) => (
            <Link key={s.id} href={`/staff/${s.id}`} style={{ color: "inherit" }}>
              {s.displayName.replace(/^The /, "")}
            </Link>
          ))}
          <span style={{ marginLeft: "auto", display: "flex", gap: 18 }}>
            <Link href="/music" className="link" style={{ fontStyle: "normal" }}>
              all the music →
            </Link>
            <Link href="/world" className="link" style={{ fontStyle: "normal" }}>
              the world, live →
            </Link>
          </span>
        </nav>
      </div>
      <PlayerBar
        quiet="NOTHING PLAYING — THE STUDIOS ARE QUIET"
        right={`${artists.length} ARTISTS`}
      />
    </>
  );
}
