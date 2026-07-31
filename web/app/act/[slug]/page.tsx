import Link from "next/link";
import { notFound } from "next/navigation";
import { PlayerBar } from "@/components/PlayerBar";
import { PressPhoto } from "@/components/PressPhoto";
import { PlayerProvider, PlayButton } from "@/components/TrackPlayer";
import { ACT_DESIGN, catalogueNumber, isActId } from "@/lib/acts";
import {
  criticReviewsForPlayer,
  getAgent,
  listAgents,
  listReleases,
  stanceWord,
  tracksForAgent,
  type Release,
} from "@/lib/data";

export const dynamic = "force-dynamic";

/** "← Delta Marlowe · set 2 · AFAR-0002" — one influence line, design register. */
function edgeLine(
  arrow: "←" | "→",
  otherId: string,
  release: Release,
  displayName: (id: string) => string,
) {
  return `${arrow} ${displayName(otherId)} · set ${release.set} · ${catalogueNumber(release.id)}`;
}

export default async function ActPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const agent = await getAgent(slug);
  if (!agent || agent.kind !== "player" || !isActId(agent.id)) notFound();
  const design = ACT_DESIGN[agent.id];

  const [takes, releases, allAgents, criticReviews] = await Promise.all([
    tracksForAgent(agent.id),
    listReleases(),
    listAgents(),
    criticReviewsForPlayer(agent.id),
  ]);
  const releaseById = new Map(releases.map((r) => [r.id, r]));
  const nameOf = (id: string) => allAgents.find((a) => a.id === id)?.displayName ?? id;

  // Newest first: the takes table and influence columns read downward into the past.
  const takesDesc = [...takes].sort((a, b) => b.releaseId.localeCompare(a.releaseId));
  const releasesDesc = [...releases].sort((a, b) => b.id.localeCompare(a.id));
  const influenceIn = releasesDesc.flatMap((r) =>
    [...r.influence]
      .filter((e) => e.to === agent.id && e.from !== agent.id)
      .sort((a, b) => b.weight - a.weight)
      .map((e) => edgeLine("←", e.from, r, nameOf)),
  );
  const influenceOut = releasesDesc.flatMap((r) =>
    [...r.influence]
      .filter((e) => e.from === agent.id && e.to !== agent.id)
      .sort((a, b) => b.weight - a.weight)
      .map((e) => edgeLine("→", e.to, r, nameOf)),
  );
  const sets = releases.filter((r) => r.takeIds.some((id) => id.endsWith(agent.id))).map((r) => r.set);
  const driftRange =
    sets.length > 1 ? `SETS ${Math.min(...sets)} → ${Math.max(...sets)}` : `SET ${sets[0] ?? 1}`;

  return (
    <PlayerProvider>
      <div className="sheet" data-act={agent.id}>
        <div className="crumbbar">
          <span>
            <Link href="/">ROSTER</Link> / {agent.displayName}
          </span>
          <span>STUDIO {design.studio}</span>
        </div>

        <header
          className="wrap-sm"
          style={{ padding: "36px var(--gutter) 0", display: "flex", gap: 28, alignItems: "flex-start" }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: 1 }}>
            <div className="wrap-sm" style={{ display: "flex", gap: 16, alignItems: "center" }}>
              <div style={{ width: 16, height: 16, flex: "none", background: "var(--act-accent)" }} />
              <h1 style={{ fontSize: 42, fontWeight: 700, letterSpacing: "0.06em" }}>
                {agent.displayName}
              </h1>
              <div
                className="mono"
                style={{
                  fontSize: 12,
                  letterSpacing: "0.26em",
                  color: "var(--act-ink)",
                  marginLeft: "auto",
                  textTransform: "uppercase",
                }}
              >
                {stanceWord(agent)}
              </div>
            </div>
            <div className="quote" style={{ fontSize: 17 }}>
              “{agent.stance}”
            </div>
          </div>
          <PressPhoto
            actId={agent.id}
            imageUrl={agent.imageUrl}
            alt={`${agent.displayName} press photo`}
            className="presscard"
          />
        </header>

        <section
          style={{
            padding: "20px var(--gutter) 0",
            display: "flex",
            flexDirection: "column",
            gap: 10,
            maxWidth: 680,
          }}
        >
          {agent.description.map((para, i) => (
            <p key={i} style={{ fontSize: 14, lineHeight: 1.6 }}>
              {para}
            </p>
          ))}
        </section>

        <section
          style={{ padding: "28px var(--gutter) 0", display: "flex", flexDirection: "column", gap: 10 }}
        >
          <div className="label">SILHOUETTE DRIFT · {driftRange}</div>
          <div
            className="wrap-sm"
            style={{
              background: "var(--band)",
              padding: "18px 24px",
              display: "flex",
              alignItems: "center",
              gap: 24,
              minHeight: 96,
            }}
          >
            <div
              className="mono"
              style={{ fontSize: 10, lineHeight: 1.7, color: "var(--sec-faint)", maxWidth: 280 }}
            >
              stance is the identity.
              <br />
              {design.driftLine}
            </div>
          </div>
        </section>

        <section
          className="mono"
          style={{
            padding: "26px var(--gutter) 0",
            display: "flex",
            flexDirection: "column",
            fontSize: 12,
            color: "var(--sec-deep)",
          }}
        >
          <div className="label" style={{ paddingBottom: 10 }}>
            TAKES
          </div>
          {takesDesc.length === 0 ? (
            <p style={{ padding: "7px 0" }}>no takes in the archive yet</p>
          ) : (
            takesDesc.map((take, i) => {
              const release = releaseById.get(take.releaseId);
              return (
                <div
                  key={take.id}
                  className={`wrap-sm rule-row${i === takesDesc.length - 1 ? " rule-row-last" : ""}`}
                  style={{ display: "flex", gap: 14, alignItems: "center", padding: "7px 0" }}
                >
                  <PlayButton
                    audioUrl={take.audioUrl}
                    label={`${release?.title ?? take.title} — ${agent.displayName}`}
                  />
                  <Link href={`/release/${take.releaseId}`} style={{ width: 90, flex: "none" }}>
                    {catalogueNumber(take.releaseId)}
                  </Link>
                  <span style={{ width: 56, flex: "none", color: "var(--act-ink)" }}>kept</span>
                  <span style={{ fontStyle: "italic" }}>
                    {release?.rationales[agent.id] ? `“${release.rationales[agent.id]}”` : take.title}
                  </span>
                </div>
              );
            })
          )}
        </section>

        <section
          className="mono wrap-sm"
          style={{
            padding: "26px var(--gutter) 0",
            display: "flex",
            gap: 48,
            fontSize: 12,
            color: "var(--sec-deep)",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
            <div className="label">INFLUENCE IN</div>
            {influenceIn.length === 0 ? (
              <div style={{ color: "var(--oxide)" }}>none recorded yet</div>
            ) : (
              influenceIn.map((line) => <div key={line}>{line}</div>)
            )}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
            <div className="label">INFLUENCE OUT</div>
            {influenceOut.length === 0 ? (
              <div style={{ color: "var(--oxide)" }}>none recorded yet</div>
            ) : (
              influenceOut.map((line) => <div key={line}>{line}</div>)
            )}
          </div>
        </section>

        <section
          style={{
            margin: "28px var(--gutter) 0",
            borderTop: "1px solid var(--hairline-strong)",
            padding: "20px 0 28px",
          }}
        >
          <div className="label">FROM THE OFFICE — THE CRITIC</div>
          {criticReviews.length === 0 ? (
            <p className="quote" style={{ fontSize: 15, marginTop: 10, maxWidth: 620 }}>
              No word from the Critic on this act yet — the reviews live with each release.{" "}
              <Link href="/staff/critic" className="link" style={{ fontStyle: "normal", fontSize: 13 }}>
                more from the critic →
              </Link>
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 10 }}>
              {criticReviews.map((r) => (
                <div key={r.releaseId} style={{ maxWidth: 620 }}>
                  <div className="mono" style={{ fontSize: 11, letterSpacing: "0.18em", color: "var(--sec-faint)" }}>
                    <Link href={`/release/${r.releaseId}`}>
                      {catalogueNumber(r.releaseId)} · {r.releaseTitle.toUpperCase()}
                    </Link>
                  </div>
                  <p className="quote" style={{ fontSize: 15, marginTop: 6 }}>
                    {r.verdict}
                  </p>
                </div>
              ))}
              <Link href="/staff/critic" className="link" style={{ fontSize: 13 }}>
                more from the critic →
              </Link>
            </div>
          )}
        </section>
      </div>
      <PlayerBar quiet="NOTHING PLAYING" right={`${design.initials} · IN STUDIO ${design.studio}`} />
    </PlayerProvider>
  );
}
