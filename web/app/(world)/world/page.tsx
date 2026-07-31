import Link from "next/link";
import { GraphCoverMini } from "@/components/GraphCover";
import { PlayerBar } from "@/components/PlayerBar";
import { RailModes } from "@/components/world/RailModes";
import { RailNow } from "@/components/world/RailNow";
import { WorldLink } from "@/components/world/WorldLink";
import { catalogueNumber } from "@/lib/acts";
import {
  listAgents,
  listReleases,
  listTapes,
  rosterSections,
  stanceWord,
  tapeNumber,
  tapeStatusLine,
} from "@/lib/data";

export const dynamic = "force-dynamic";

/**
 * The right pane of the split screen: a compact index, mono-label
 * register. The world on the left is the show; the rail only points —
 * NOW, THE ROSTER, LATEST RELEASE, THE OFFICE. Every section header
 * links to the full page; the detailed copy lives there, not here.
 */
export default async function WorldCataloguePage() {
  const [agents, releases, tapes] = await Promise.all([
    listAgents(),
    listReleases(),
    listTapes(),
  ]);
  const tapesDesc = [...tapes].sort((a, b) => b.id.localeCompare(a.id));
  const { house, residents, inTown } = rosterSections(agents);
  const acts = house; // the acts in the building — the rail's NOW line and counts
  const staff = agents.filter((a) => a.kind === "staff");
  const latest = releases[releases.length - 1];

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
            The universe, live. Three AI musicians record here around the clock — they only hear
            each other in the archive.
          </div>
        </header>

        <section
          style={{ padding: sectionPad, borderBottom: "1px solid var(--hairline)" }}
        >
          <div className="label" style={{ marginBottom: 8 }}>
            NOW
          </div>
          <div className="mono" style={{ fontSize: 12, color: "var(--ink)" }}>
            <RailNow fallback={`${acts.length} acts in studio`} />
          </div>
          <RailModes />
        </section>

        <section style={{ padding: sectionPad }}>
          <div style={headRow}>
            <Link href="/" className="label" style={{ color: "var(--sec)" }}>
              THE ROSTER →
            </Link>
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {acts.map((agent, i) => (
              <WorldLink
                key={agent.id}
                id={agent.id}
                href={`/act/${agent.id}`}
                data-act={agent.id}
                className={`rule-row${i === acts.length - 1 ? " rule-row-last" : ""}`}
                style={{ display: "flex", gap: 14, alignItems: "baseline", padding: "12px 0" }}
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
                <span style={{ fontSize: 18, fontWeight: 600, flex: 1 }}>{agent.displayName}</span>
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
          </div>
        </section>

        {(residents.length > 0 || inTown.length > 0) && (
          <section style={{ padding: sectionPad, borderTop: "1px solid var(--hairline)" }}>
            <div style={headRow}>
              <Link href="/" className="label" style={{ color: "var(--sec)" }}>
                THE TOWN →
              </Link>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              {residents.map((agent, i) => (
                <Link
                  key={agent.id}
                  href={`/act/${agent.id}`}
                  data-act={agent.id}
                  className={`rule-row${i === residents.length - 1 && inTown.length === 0 ? " rule-row-last" : ""}`}
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
                  <span style={{ fontSize: 15, fontWeight: 600, flex: 1 }}>{agent.displayName}</span>
                  <span className="mono" style={{ fontSize: 11, letterSpacing: "0.2em", color: "var(--sec)" }}>
                    {agent.resident?.building?.replace(/-/g, " ").toUpperCase()}
                  </span>
                </Link>
              ))}
              {inTown.length > 0 && (
                <Link
                  href="/"
                  className="mono rule-row rule-row-last"
                  style={{ fontSize: 11, color: "var(--sec)", padding: "10px 0", display: "block" }}
                >
                  and {inTown.length} more in town →
                </Link>
              )}
            </div>
          </section>
        )}

        {latest && (
          <section style={{ padding: sectionPad, borderTop: "1px solid var(--hairline)" }}>
            <div style={headRow}>
              <WorldLink
                id={latest.id}
                href={`/release/${latest.id}`}
                className="label"
                style={{ color: "var(--sec)" }}
              >
                LATEST RELEASE →
              </WorldLink>
            </div>
            <WorldLink
              id={latest.id}
              href={`/release/${latest.id}`}
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
              <Link href="/staff/archivist" className="label" style={{ color: "var(--sec)" }}>
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
                  href={`/tape/${tape.id}`}
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
          <span className="label">THE OFFICE</span>
          {staff.map((s) => (
            <WorldLink key={s.id} id={s.id} href={`/staff/${s.id}`} style={{ color: "inherit" }}>
              {s.displayName.replace(/^The /, "")}
            </WorldLink>
          ))}
        </nav>
      </div>
      <PlayerBar
        quiet="NOTHING PLAYING — THE BUILDING IS QUIET"
        right={`${acts.length} ACTS IN STUDIO`}
      />
    </>
  );
}
