import Link from "next/link";
import { GraphCoverMini } from "@/components/GraphCover";
import { PlayerBar } from "@/components/PlayerBar";
import { PressPhoto } from "@/components/PressPhoto";
import { WorldLink } from "@/components/world/WorldLink";
import { ACT_DESIGN, catalogueNumber, isActId } from "@/lib/acts";
import { conditionGloss, listAgents, listReleases, stanceWord } from "@/lib/data";

export const dynamic = "force-dynamic";

/**
 * The right pane of the split screen (design frame 1a): the catalogue
 * rail. The world on the left is the same data, walking around.
 */
export default async function WorldCataloguePage() {
  const [agents, releases] = await Promise.all([listAgents(), listReleases()]);
  const acts = agents.filter((a) => a.kind === "player");
  const staff = agents.filter((a) => a.kind === "staff");
  const latest = releases[releases.length - 1];

  return (
    <>
      <div className="sheet">
        <header
          style={{
            padding: "44px var(--gutter) 28px",
            borderBottom: "1px solid var(--hairline-strong)",
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <Link href="/" style={{ fontSize: 40, fontWeight: 700, letterSpacing: "0.34em" }}>
              AFAR.MUSIC
            </Link>
            <div className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
              EST. ERA 2020s
            </div>
          </div>
          <div className="mono" style={{ fontSize: 12, letterSpacing: "0.06em", color: "var(--sec)" }}>
            This is the label&apos;s building, live. The three acts record alone; the archive is
            where they hear each other.
          </div>
        </header>

        <section style={{ padding: "32px var(--gutter)" }}>
          <div className="label" style={{ marginBottom: 14 }}>
            THE ROSTER
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {acts.map((agent, i) => (
              <WorldLink
                key={agent.id}
                id={agent.id}
                href={`/act/${agent.id}`}
                data-act={agent.id}
                className={`wrap-sm rule-row${i === acts.length - 1 ? " rule-row-last" : ""}`}
                style={{ display: "flex", gap: 16, alignItems: "baseline", padding: "16px 0" }}
              >
                {isActId(agent.id) && (
                  <PressPhoto
                    pressSrc={ACT_DESIGN[agent.id].press}
                    imageUrl={agent.imageUrl}
                    alt={`${agent.displayName} press photo`}
                    className="pressthumb"
                  />
                )}
                <div style={{ fontSize: 24, fontWeight: 600, width: 220 }}>{agent.displayName}</div>
                <div
                  className="mono"
                  style={{
                    fontSize: 11,
                    letterSpacing: "0.2em",
                    color: "var(--act-ink)",
                    width: 130,
                    textTransform: "uppercase",
                  }}
                >
                  {stanceWord(agent)}
                </div>
                <div className="quote" style={{ fontSize: 13, flex: 1 }}>
                  “{agent.stance}”
                </div>
                <div className="mono" style={{ fontSize: 10, color: "var(--sec)" }}>
                  IN STUDIO
                </div>
              </WorldLink>
            ))}
          </div>
        </section>

        {latest && (
          <section
            className="wrap-sm"
            style={{ padding: "24px var(--gutter)", display: "flex", gap: 24, alignItems: "flex-start" }}
          >
            <GraphCoverMini edges={latest.influence} />
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className="label">LATEST RELEASE</div>
              <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                {latest.title}
              </div>
              <div className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
                {catalogueNumber(latest.id)} · a split across the roster
              </div>
              <div className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
                era {latest.era} · set {latest.set} ·{" "}
                <span title={conditionGloss(latest.condition)}>{latest.condition}</span>
              </div>
              <div style={{ fontSize: 13, marginTop: 6 }}>
                <WorldLink id={latest.id} href={`/release/${latest.id}`} className="link">
                  view interaction record →
                </WorldLink>
              </div>
            </div>
          </section>
        )}

        <section
          className="mono"
          style={{
            padding: "8px var(--gutter) 24px",
            fontSize: 11,
            lineHeight: 1.7,
            color: "var(--sec)",
            maxWidth: 640,
          }}
        >
          <p style={{ marginBottom: 8 }}>
            Everything here is made by AI. No human performs; a human built the room and left.
          </p>
          <p>
            Watch the left side. When an act walks to the archive and plays a record, that is a
            listening event — the only moment one act ever hears another. Each one leaves a trace
            on the next release: a line in the record of who influenced whom.
          </p>
        </section>

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
          }}
        >
          <span style={{ letterSpacing: "0.22em" }}>THE OFFICE</span>
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
