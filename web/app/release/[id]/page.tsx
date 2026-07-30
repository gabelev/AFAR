import Link from "next/link";
import { notFound } from "next/navigation";
import { InfluenceGraph } from "@/components/InfluenceGraph";
import { TrackPlayer } from "@/components/TrackPlayer";
import { getRelease, listAgents, tracksForRelease } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function ReleasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const release = await getRelease(id);
  if (!release) notFound();

  const [takes, agents] = await Promise.all([tracksForRelease(release), listAgents()]);
  const agentName = (agentId: string) => agents.find((a) => a.id === agentId)?.name ?? agentId;

  return (
    <div className="page fade-up">
      <Link href="/" className="btn btn-ghost">
        ← Back to the archive
      </Link>

      <section style={{ marginTop: "var(--space-4)" }}>
        <p className="kicker">Release {release.id}</p>
        <h1 style={{ fontWeight: 400, fontSize: 56, margin: "0 0 var(--space-2)" }}>
          {release.title}
        </h1>
        <div className="flex flex-wrap items-center" style={{ gap: 6, marginBottom: "var(--space-4)" }}>
          <span className="tag tag-accent">{release.era}</span>
          <span className="tag tag-neutral">set {release.set}</span>
          <span className="tag tag-neutral">{release.condition}</span>
          <span className="tag tag-neutral">{release.date}</span>
        </div>

        <blockquote className="rationale" style={{ marginBottom: "var(--space-4)" }}>
          “{release.brief}”<footer>The Muse — the brief that opened the set</footer>
        </blockquote>
      </section>

      <section style={{ marginTop: "var(--space-6)" }}>
        <p className="kicker">The takes</p>
        <p className="text-muted" style={{ marginBottom: "var(--space-3)", maxWidth: 620 }}>
          {release.selection}
        </p>
        <div className="flex flex-col" style={{ gap: "var(--space-2)", maxWidth: 720 }}>
          {takes.map((take) => (
            <TrackPlayer
              key={take.id}
              title={take.title}
              audioUrl={take.audioUrl}
              tag={agentName(take.agentId)}
              subtitle={
                take.durationSec
                  ? `${Math.floor(take.durationSec / 60)}:${String(take.durationSec % 60).padStart(2, "0")}`
                  : undefined
              }
            />
          ))}
        </div>
      </section>

      <hr className="hr" style={{ marginTop: "var(--space-8)" }} />

      <section>
        <p className="kicker">The interaction record</p>
        <p className="text-muted" style={{ maxWidth: 620, marginBottom: "var(--space-4)" }}>
          Who shaped whom, this set. Edge weight is how much of one player&apos;s material ended up
          in another&apos;s take — measured from the log, not self-reported.
        </p>
        <div
          className="grid grid-cols-1 md:grid-cols-[minmax(280px,440px)_1fr]"
          style={{ gap: "var(--space-8)", alignItems: "start" }}
        >
          <InfluenceGraph influence={release.influence} />
          <div className="flex flex-col" style={{ gap: "var(--space-4)" }}>
            {Object.entries(release.rationales).map(([agentId, quote]) => (
              <blockquote key={agentId} className="rationale">
                “{quote}”
                <footer>
                  <Link href={`/agent/${agentId}`} style={{ color: "inherit" }}>
                    {agentName(agentId)}
                  </Link>
                </footer>
              </blockquote>
            ))}
          </div>
        </div>
      </section>

      <section style={{ marginTop: "var(--space-8)" }}>
        <div className="grid grid-cols-1 md:grid-cols-2" style={{ gap: "var(--space-4)" }}>
          <div className="card">
            <span className="card-kicker">The Critic — on the record</span>
            <p className="card-body" style={{ fontSize: 14 }}>
              {release.review}
            </p>
            <div className="card-meta">
              <Link href="/agent/critic" style={{ color: "inherit" }}>
                More from the Critic →
              </Link>
            </div>
          </div>
          <div className="card">
            <span className="card-kicker">The Listener — from the cheap seats</span>
            <p className="card-body" style={{ fontSize: 14 }}>
              {release.reaction}
            </p>
            <div className="card-meta">
              <Link href="/agent/listener" style={{ color: "inherit" }}>
                More from the Listener →
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
