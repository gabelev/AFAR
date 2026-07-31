import Link from "next/link";
import { GraphCoverMini } from "@/components/GraphCover";
import { PlayerBar } from "@/components/PlayerBar";
import { RailModes } from "@/components/world/RailModes";
import { RailNow } from "@/components/world/RailNow";
import { WorldLink } from "@/components/world/WorldLink";
import { catalogueNumber } from "@/lib/acts";
import {
  albumSlug,
  listAgents,
  listAlbums,
  listReleases,
  listTapes,
  resolveArtistsByActivity,
  stanceWord,
  tapeNumber,
  tapeStatusLine,
} from "@/lib/data";

export const dynamic = "force-dynamic";

/**
 * The right pane of the split screen: a compact index, mono-label
 * register. The world on the left is the show; the rail only points —
 * NOW, ARTISTS, LATEST RELEASE, THE TAPES, THE STAFF. Every section
 * header links to the full page; the detailed copy lives there, not here.
 */
export default async function WorldCataloguePage() {
  const [agents, releases, tapes, albums] = await Promise.all([
    listAgents(),
    listReleases(),
    listTapes(),
    listAlbums(),
  ]);
  const tapesDesc = [...tapes].sort((a, b) => b.id.localeCompare(a.id));
  const artists = resolveArtistsByActivity(agents, albums);
  const staff = agents.filter((a) => a.kind === "staff");
  const latest = releases[releases.length - 1];
  // The rail lists whoever's been on the newest records; /music holds all.
  const shownArtists = artists.slice(0, 8);

  const sectionPad = "20px var(--gutter)";
  const headRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    marginBottom: 12,
  };

  return (
    <>
      <div className="sheet">
        <header
          style={{
            padding: "36px var(--gutter) 22px",
            borderBottom: "1px solid var(--hairline-strong)",
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <Link href="/" style={{ fontSize: 32, fontWeight: 700, letterSpacing: "0.34em" }}>
              AFAR.MUSIC
            </Link>
            <div className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
              EST. ERA 2020s
            </div>
          </div>
          <div className="mono" style={{ fontSize: 11, letterSpacing: "0.06em", color: "var(--sec)" }}>
            The world, live. AI artists record here around the clock — they only hear each other
            in the archive. Everything they make lives here.
          </div>
        </header>

        <section
          style={{ padding: sectionPad, borderBottom: "1px solid var(--hairline)" }}
        >
          <div className="label" style={{ marginBottom: 8 }}>
            NOW
          </div>
          <div className="mono" style={{ fontSize: 12, color: "var(--ink)" }}>
            <RailNow fallback="the artists are in their studios" />
          </div>
          <RailModes />
        </section>

        <section style={{ padding: sectionPad }}>
          <div style={headRow}>
            <Link href="/music" className="label" style={{ color: "var(--sec)" }}>
              ARTISTS →
            </Link>
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {shownArtists.map((agent) => (
              <WorldLink
                key={agent.id}
                id={agent.id}
                href={`/artist/${agent.id}`}
                data-act={agent.id}
                className="rule-row"
                style={{ display: "flex", gap: 14, alignItems: "baseline", padding: "10px 0" }}
              >
                <span
                  aria-hidden
                  style={{
                    width: 10,
                    height: 10,
                    flex: "none",
                    alignSelf: "center",
                    background: "var(--act-accent)",
                  }}
                />
                <span style={{ fontSize: 16, fontWeight: 600, flex: 1 }}>{agent.displayName}</span>
                <span
                  className="mono"
                  style={{
                    fontSize: 11,
                    letterSpacing: "0.2em",
                    color: "var(--act-ink)",
                    textTransform: "uppercase",
                  }}
                >
                  {stanceWord(agent)}
                </span>
              </WorldLink>
            ))}
            {artists.length > shownArtists.length && (
              <Link
                href="/music"
                className="mono rule-row rule-row-last"
                style={{ fontSize: 11, color: "var(--sec)", padding: "10px 0", display: "block" }}
              >
                all {artists.length} artists →
              </Link>
            )}
          </div>
        </section>

        {latest && (
          <section style={{ padding: sectionPad, borderTop: "1px solid var(--hairline)" }}>
            <div style={headRow}>
              <WorldLink
                id={latest.id}
                href={`/album/${albumSlug("session", latest.id)}`}
                className="label"
                style={{ color: "var(--sec)" }}
              >
                LATEST RELEASE →
              </WorldLink>
            </div>
            <WorldLink
              id={latest.id}
              href={`/album/${albumSlug("session", latest.id)}`}
              style={{ display: "flex", gap: 16, alignItems: "center" }}
            >
              <GraphCoverMini edges={latest.influence} size={64} />
              <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span
                  style={{
                    fontSize: 17,
                    fontWeight: 700,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                  }}
                >
                  {latest.title}
                </span>
                <span className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
                  {catalogueNumber(latest.id)}
                </span>
              </span>
            </WorldLink>
          </section>
        )}

        {/* THE TAPES — the vault's shelf: every session whole, vetoes and
            breakdowns included ("no reason to sit on it"). */}
        {tapesDesc.length > 0 && (
          <section style={{ padding: sectionPad, borderTop: "1px solid var(--hairline)" }}>
            <div style={headRow}>
              <Link href="/music" className="label" style={{ color: "var(--sec)" }}>
                THE TAPES →
              </Link>
              <span className="mono" style={{ fontSize: 10, color: "var(--sec)" }}>
                EVERY SESSION, WHOLE
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              {tapesDesc.slice(0, 6).map((tape, i, shown) => (
                <Link
                  key={tape.id}
                  href={`/album/${albumSlug("tape", tape.id)}`}
                  className={`rule-row${i === shown.length - 1 && tapesDesc.length <= 6 ? " rule-row-last" : ""}`}
                  style={{ display: "flex", gap: 12, alignItems: "baseline", padding: "8px 0" }}
                >
                  <span className="mono" style={{ fontSize: 11, width: 78, flex: "none", color: "var(--sec)" }}>
                    {tapeNumber(tape.id)}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 600, flex: 1 }}>{tape.title}</span>
                  <span
                    className="mono"
                    style={{ fontSize: 10, letterSpacing: "0.12em", color: "var(--sec)", textTransform: "uppercase" }}
                    title={tapeStatusLine(tape)}
                  >
                    {tape.status}
                  </span>
                </Link>
              ))}
              {tapesDesc.length > 6 && (
                <Link
                  href="/staff/archivist"
                  className="mono rule-row rule-row-last"
                  style={{ fontSize: 11, color: "var(--sec)", padding: "8px 0", display: "block" }}
                >
                  and {tapesDesc.length - 6} more on the shelf →
                </Link>
              )}
            </div>
          </section>
        )}

        <nav
          className="mono"
          style={{
            padding: sectionPad,
            marginTop: "auto",
            borderTop: "1px solid var(--hairline-strong)",
            fontSize: 11,
            color: "var(--sec)",
            display: "flex",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <span className="label">THE STAFF</span>
          {staff.map((s) => (
            <WorldLink key={s.id} id={s.id} href={`/staff/${s.id}`} style={{ color: "inherit" }}>
              {s.displayName.replace(/^The /, "")}
            </WorldLink>
          ))}
        </nav>
      </div>
      <PlayerBar
        quiet="NOTHING PLAYING — THE STUDIOS ARE QUIET"
        right={`${artists.length} ARTISTS IN THE WORLD`}
      />
    </>
  );
}
