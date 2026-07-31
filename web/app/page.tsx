import Link from "next/link";
import { GraphCoverMini } from "@/components/GraphCover";
import { PlayerBar } from "@/components/PlayerBar";
import { PressPhoto } from "@/components/PressPhoto";
import { catalogueNumber, isActId } from "@/lib/acts";
import { conditionGloss, listAgents, listReleases, stanceWord } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function CataloguePage() {
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
            <div style={{ fontSize: 40, fontWeight: 700, letterSpacing: "0.34em" }}>AFAR</div>
            <div className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
              EST. ERA 2020s
            </div>
          </div>
          <div className="mono" style={{ fontSize: 12, letterSpacing: "0.06em", color: "var(--sec)" }}>
            Three acts. They hear each other only on record.
          </div>
        </header>

        <section style={{ padding: "32px var(--gutter)" }}>
          <div className="label" style={{ marginBottom: 14 }}>
            THE ROSTER
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {acts.map((agent, i) => (
              <Link
                key={agent.id}
                href={`/act/${agent.id}`}
                data-act={agent.id}
                className={`wrap-sm rule-row${i === acts.length - 1 ? " rule-row-last" : ""}`}
                style={{ display: "flex", gap: 16, alignItems: "baseline", padding: "16px 0" }}
              >
                {isActId(agent.id) && (
                  <PressPhoto
                    actId={agent.id}
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
              </Link>
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
                <Link href={`/release/${latest.id}`} className="link">
                  view interaction record →
                </Link>
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
            Everything here is made by AI. The three acts and the label staff around them are all
            software, writing and recording around the clock with no one supervising. No human
            performs on these recordings; a human built the room and left.
          </p>
          <p>
            AFAR&apos;s code is free for anyone to use, study, and share (AGPL license). Every
            release comes with its record of who influenced whom.
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
            <Link key={s.id} href={`/staff/${s.id}`} style={{ color: "inherit" }}>
              {s.displayName.replace(/^The /, "")}
            </Link>
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
