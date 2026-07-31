import Link from "next/link";
import { notFound } from "next/navigation";
import { GraphCover } from "@/components/GraphCover";
import { PlayerProvider, PlayButton } from "@/components/TrackPlayer";
import { ACT_DESIGN, catalogueNumber, interactionRows, isActId, sideLabel } from "@/lib/acts";
import { conditionGloss, getRelease, listAgents, tracksForRelease } from "@/lib/data";

export const dynamic = "force-dynamic";

/** The office's voice on this release — kept content, re-registered. */
const OFFICE_BLOCKS = [
  { label: "FROM THE MUSE — THE BRIEF", staffId: "muse", pick: "brief" },
  { label: "FROM THE PRODUCER — THE SELECTION", staffId: "producer", pick: "selection" },
  { label: "FROM THE CRITIC — THE REVIEW", staffId: "critic", pick: "review" },
  { label: "FROM THE LISTENER — THE REACTION", staffId: "listener", pick: "reaction" },
] as const;

export default async function ReleasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const release = await getRelease(id);
  if (!release) notFound();

  const [takes, agents] = await Promise.all([tracksForRelease(release), listAgents()]);
  const displayName = (agentId: string) =>
    agents.find((a) => a.id === agentId)?.displayName ?? agentId;
  const initials = (agentId: string) =>
    isActId(agentId)
      ? ACT_DESIGN[agentId].initials
      : displayName(agentId)
          .split(/\s+/)
          .map((w) => w[0])
          .join("")
          .toUpperCase();
  const names = Object.fromEntries(agents.map((a) => [a.id, a.displayName]));
  const rows = interactionRows(release);

  return (
    <div className="sheet">
      <div className="crumbbar">
        <span>
          <Link href="/world">CATALOGUE</Link> / {catalogueNumber(release.id)}
        </span>
        <span>SET {release.set}</span>
      </div>

      <div style={{ display: "flex", justifyContent: "center", padding: "36px 0 0" }}>
        <GraphCover
          releaseId={release.id}
          title={release.title}
          edges={release.influence}
          names={names}
        />
      </div>

      <section
        style={{ padding: "28px var(--gutter) 0", display: "flex", flexDirection: "column", gap: 6 }}
      >
        <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          {release.title}
        </h1>
        <div className="mono" style={{ fontSize: 11, color: "var(--sec)", textTransform: "uppercase" }}>
          ONE TAKE FROM EACH ACT ·{" "}
          <span title="The decade this release reaches for">ERA {release.era}</span> ·{" "}
          <span title="The recording session it came from">SET {release.set}</span> ·{" "}
          <span title={conditionGloss(release.condition)}>{release.condition}</span>
        </div>
      </section>

      <section style={{ padding: "22px var(--gutter)", display: "flex", flexDirection: "column", fontSize: 13 }}>
        <div className="label" style={{ paddingBottom: 6 }}>
          INTERACTION RECORD
        </div>
        <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 10 }}>
          Who pulled whom: after each session, we measure how much each act moved toward the
          others&apos; music. The notation is measured from the recordings themselves; the words are
          what the acts claim.
        </p>
        {rows.map((row, i) => (
          <div
            key={`${row.from}-${row.to}`}
            className={`rule-row${i === rows.length - 1 ? " rule-row-last" : ""}`}
            style={{ display: "flex", gap: 12, alignItems: "baseline", padding: "9px 0" }}
          >
            <span
              className="mono"
              style={{
                fontSize: 11,
                width: 64,
                flex: "none",
                color: isActId(row.from) ? ACT_DESIGN[row.from].inkOnPaper : "var(--sec)",
              }}
            >
              {initials(row.from)} {row.from === row.to ? "⟲" : "→"} {initials(row.to)}
            </span>
            <span className="quote">“{row.quote}”</span>
          </div>
        ))}
      </section>

      <PlayerProvider>
        <section style={{ padding: "0 var(--gutter) 22px", display: "flex", flexDirection: "column", fontSize: 13 }}>
          <div className="label" style={{ paddingBottom: 6 }}>
            SIDES
          </div>
          <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 8 }}>
            The takes, laid out like a record sleeve. Press play on any of them.
          </p>
          {takes.map((take, i) => (
            <div
              key={take.id}
              className={`rule-row${i === takes.length - 1 ? " rule-row-last" : ""}`}
              style={{ display: "flex", gap: 12, alignItems: "center", padding: "9px 0" }}
            >
              <span className="mono" style={{ fontSize: 11, width: 34, flex: "none" }}>
                {sideLabel(i, takes.length)}
              </span>
              <span style={{ fontWeight: 600, width: 160 }}>
                {isActId(take.agentId) ? (
                  <Link href={`/act/${take.agentId}`}>{displayName(take.agentId)}</Link>
                ) : (
                  displayName(take.agentId)
                )}
              </span>
              <PlayButton
                audioUrl={take.audioUrl}
                label={`${take.title} — ${displayName(take.agentId)}`}
              />
              {/* The Critic titles takes; interim "<release> — <act>'s take"
                  placeholders would just repeat the sleeve, so they stay quiet. */}
              {!take.title.startsWith(release.title) && (
                <span className="quote" style={{ fontSize: 13 }}>
                  “{take.title}”
                </span>
              )}
              <span className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
                {take.audioUrl
                  ? take.durationSec
                    ? `${Math.floor(take.durationSec / 60)}:${String(take.durationSec % 60).padStart(2, "0")}`
                    : ""
                  : "audio not yet archived"}
              </span>
            </div>
          ))}
        </section>
      </PlayerProvider>

      {OFFICE_BLOCKS.map((block) => (
        <section
          key={block.staffId}
          style={{ margin: "0 var(--gutter)", borderTop: "1px solid var(--hairline-strong)", padding: "20px 0" }}
        >
          <div className="label">{block.label}</div>
          <p className="quote" style={{ fontSize: 14, marginTop: 10, maxWidth: 680 }}>
            “{release[block.pick]}”
          </p>
          <div style={{ fontSize: 12, marginTop: 8 }}>
            <Link href={`/staff/${block.staffId}`} className="link">
              more from {displayName(block.staffId).toLowerCase()} →
            </Link>
          </div>
        </section>
      ))}

      <div
        className="mono"
        style={{
          marginTop: "auto",
          padding: "18px var(--gutter) 28px",
          fontSize: 10,
          letterSpacing: "0.14em",
          color: "var(--sec)",
        }}
      >
        THE GRAPH IS THE COVER. NOTHING IS ILLUSTRATED TWICE.
      </div>
    </div>
  );
}
