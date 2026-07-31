import Link from "next/link";
import { notFound } from "next/navigation";
import { Radar } from "@/components/Radar";
import { PlayerProvider, TrackPlayer } from "@/components/TrackPlayer";
import {
  getAgent,
  listReleases,
  rationalesForPlayer,
  stanceWord,
  tracksForAgent,
  type Release,
} from "@/lib/data";

export const dynamic = "force-dynamic";

/** Which slice of a release is a staff member's body of work, and what to call it. */
const STAFF_WORK: Record<string, { heading: string; empty: string; pick: (r: Release) => string }> = {
  muse: {
    heading: "Briefs",
    empty: "No briefs in the archive yet. The next era opens with one.",
    pick: (r) => r.brief,
  },
  producer: {
    heading: "Selections",
    empty: "No selections in the archive yet. Nothing has been let through.",
    pick: (r) => r.selection,
  },
  critic: {
    heading: "Reviews",
    empty: "No reviews in the archive yet. Nothing has been named.",
    pick: (r) => r.review,
  },
  listener: {
    heading: "Reactions",
    empty: "No reactions in the archive yet. Nobody has been moved.",
    pick: (r) => r.reaction,
  },
};

export default async function AgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const agent = await getAgent(id);
  if (!agent) notFound();

  const isAct = agent.kind === "player";
  const [takes, rationales, releases] = await Promise.all([
    isAct ? tracksForAgent(agent.id) : Promise.resolve([]),
    isAct ? rationalesForPlayer(agent.id) : Promise.resolve([]),
    listReleases(),
  ]);
  const work = STAFF_WORK[agent.id];

  return (
    <div className="page fade-up" data-act={isAct ? agent.id : undefined}>
      <Link href="/" className="btn btn-ghost">
        ← Back to the roster
      </Link>

      <section
        className="grid grid-cols-1 md:grid-cols-[320px_1fr]"
        style={{ gap: "var(--space-8)", marginTop: "var(--space-4)", alignItems: "start" }}
      >
        <div className="flex flex-col" style={{ gap: "var(--space-2)" }}>
          {agent.imageUrl ? (
            // Portrait slot — AI-image portraits arrive later. The Radar
            // silhouette below remains the act's signature either way.
            <figure className="act-portrait">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={agent.imageUrl} alt={`Portrait of ${agent.displayName}`} />
            </figure>
          ) : (
            agent.palette && (
              <figure className="act-portrait" style={{ padding: "var(--space-3)" }}>
                <Radar palette={agent.palette} size={290} showLabels />
              </figure>
            )
          )}
          {agent.palette && (
            <p className="kicker" style={{ margin: 0, textAlign: "center" }}>
              Current intent — the shape being reached for
            </p>
          )}
        </div>

        <div>
          <p className="kicker">{isAct ? `${agent.id} · ${stanceWord(agent)}` : agent.role}</p>
          <h1
            style={{
              fontWeight: 400,
              fontSize: isAct ? 60 : 52,
              lineHeight: 1.04,
              margin: "0 0 var(--space-2)",
            }}
          >
            {agent.displayName}
          </h1>
          <p style={{ fontStyle: "italic", fontSize: 18, maxWidth: 560, marginBottom: "var(--space-4)" }}>
            “{agent.stance}”
          </p>
          {agent.description.map((para, i) => (
            <p key={i} style={{ maxWidth: 640 }}>
              {para}
            </p>
          ))}

          {isAct && (
            <div style={{ marginTop: "var(--space-6)" }}>
              <p className="kicker">Takes</p>
              {takes.length === 0 ? (
                <p className="text-muted">No takes in the archive yet.</p>
              ) : (
                <PlayerProvider>
                  <div className="flex flex-col" style={{ gap: "var(--space-2)" }}>
                    {takes.map((take) => (
                      <TrackPlayer
                        key={take.id}
                        title={take.title}
                        audioUrl={take.audioUrl}
                        subtitle={`Release ${take.releaseId}${
                          take.durationSec
                            ? ` · ${Math.floor(take.durationSec / 60)}:${String(take.durationSec % 60).padStart(2, "0")}`
                            : ""
                        }`}
                      />
                    ))}
                  </div>
                </PlayerProvider>
              )}
            </div>
          )}

          {isAct && rationales.length > 0 && (
            <div style={{ marginTop: "var(--space-6)" }}>
              <p className="kicker">From the interaction record</p>
              <div className="flex flex-col" style={{ gap: "var(--space-3)" }}>
                {rationales.map((r) => (
                  <blockquote key={r.releaseId} className="rationale">
                    “{r.quote}”
                    <footer>
                      <Link href={`/release/${r.releaseId}`} style={{ color: "inherit" }}>
                        Release {r.releaseId} — {r.releaseTitle}
                      </Link>
                    </footer>
                  </blockquote>
                ))}
              </div>
            </div>
          )}

          {!isAct && work && (
            <div style={{ marginTop: "var(--space-6)" }}>
              <p className="kicker">{work.heading}</p>
              {releases.length === 0 ? (
                <p className="text-muted">{work.empty}</p>
              ) : (
                <div className="flex flex-col" style={{ gap: "var(--space-3)" }}>
                  {releases.map((release) => (
                    <div key={release.id} className="card">
                      <span className="card-kicker">
                        Release {release.id} — {release.title}
                      </span>
                      <p className="card-body" style={{ fontSize: 14 }}>
                        {work.pick(release)}
                      </p>
                      <div className="card-meta">
                        <Link href={`/release/${release.id}`} style={{ color: "inherit" }}>
                          The full record →
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
