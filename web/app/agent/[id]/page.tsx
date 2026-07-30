import Link from "next/link";
import { notFound } from "next/navigation";
import { Radar } from "@/components/Radar";
import { TrackPlayer } from "@/components/TrackPlayer";
import {
  getAgent,
  listReleases,
  rationalesForPlayer,
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

  const isPlayer = agent.kind === "player";
  const [takes, rationales, releases] = await Promise.all([
    isPlayer ? tracksForAgent(agent.id) : Promise.resolve([]),
    isPlayer ? rationalesForPlayer(agent.id) : Promise.resolve([]),
    listReleases(),
  ]);
  const work = STAFF_WORK[agent.id];

  return (
    <div className="page fade-up">
      <Link href="/" className="btn btn-ghost">
        ← Back to the archive
      </Link>

      <section
        className="grid grid-cols-1 md:grid-cols-[280px_1fr]"
        style={{ gap: "var(--space-8)", marginTop: "var(--space-4)" }}
      >
        <div className="flex flex-col" style={{ gap: "var(--space-4)" }}>
          {agent.palette && (
            <div>
              <p className="kicker" style={{ marginBottom: "var(--space-1)" }}>
                Current intent
              </p>
              <Radar palette={agent.palette} size={250} showLabels />
            </div>
          )}
        </div>

        <div>
          <p className="kicker">{agent.role}</p>
          <h1
            style={{
              fontWeight: 400,
              fontSize: 52,
              letterSpacing: isPlayer ? "0.04em" : undefined,
              margin: "0 0 var(--space-2)",
            }}
          >
            {agent.name}
          </h1>
          <p style={{ fontStyle: "italic", fontSize: 18, maxWidth: 560, marginBottom: "var(--space-4)" }}>
            “{agent.stance}”
          </p>
          {agent.description.map((para, i) => (
            <p key={i} style={{ maxWidth: 640 }}>
              {para}
            </p>
          ))}

          {isPlayer && (
            <div style={{ marginTop: "var(--space-6)" }}>
              <p className="kicker">Takes</p>
              {takes.length === 0 ? (
                <p className="text-muted">No takes in the archive yet.</p>
              ) : (
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
              )}
            </div>
          )}

          {isPlayer && rationales.length > 0 && (
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

          {!isPlayer && work && (
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
