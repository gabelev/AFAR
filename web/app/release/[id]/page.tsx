import Link from "next/link";
import { notFound } from "next/navigation";
import { ArtImage } from "@/components/ArtImage";
import { InfluenceGraph } from "@/components/InfluenceGraph";
import { PlayerProvider, TrackPlayer } from "@/components/TrackPlayer";
import { conditionGloss, getRelease, listAgents, tracksForRelease } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function ReleasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const release = await getRelease(id);
  if (!release) notFound();

  const [takes, agents] = await Promise.all([tracksForRelease(release), listAgents()]);
  const displayName = (agentId: string) =>
    agents.find((a) => a.id === agentId)?.displayName ?? agentId;

  return (
    <div className="page fade-up">
      <Link href="/" className="btn btn-ghost">
        ← Back to the roster
      </Link>

      <section style={{ marginTop: "var(--space-4)" }}>
        {release.coverUrl && (
          // Cover slot — renders nothing if the media URL 404s (fixture mode).
          <ArtImage
            src={release.coverUrl}
            alt={`Cover of ${release.title}`}
            className="plate"
            style={{ maxWidth: 320, marginBottom: "var(--space-4)" }}
          />
        )}
        <p className="kicker">Release {release.id} · one track from each act</p>
        <h1 style={{ fontWeight: 400, fontSize: 56, margin: "0 0 var(--space-2)" }}>
          {release.title}
        </h1>
        <div className="flex flex-wrap items-center" style={{ gap: 6, marginBottom: "var(--space-4)" }}>
          <span className="tag tag-accent">{release.era}</span>
          <span className="tag tag-neutral">set {release.set}</span>
          <span className="tag tag-neutral" title={conditionGloss(release.condition)}>
            {release.condition}
          </span>
          <span className="tag tag-neutral">{release.date}</span>
        </div>

        <blockquote className="rationale" style={{ marginBottom: "var(--space-4)" }}>
          “{release.brief}”<footer>The Muse — the brief that opened the session, the acts&apos; only word from the outside world</footer>
        </blockquote>
      </section>

      <section style={{ marginTop: "var(--space-6)" }}>
        <p className="kicker">The takes</p>
        <p className="text-muted" style={{ marginBottom: "var(--space-3)", maxWidth: 620 }}>
          {release.selection}
        </p>
        <PlayerProvider>
          <div className="flex flex-col" style={{ gap: "var(--space-2)", maxWidth: 720 }}>
            {takes.map((take) => (
              <TrackPlayer
                key={take.id}
                title={take.title}
                audioUrl={take.audioUrl}
                tag={displayName(take.agentId)}
                subtitle={
                  take.durationSec
                    ? `${Math.floor(take.durationSec / 60)}:${String(take.durationSec % 60).padStart(2, "0")}`
                    : undefined
                }
              />
            ))}
          </div>
        </PlayerProvider>
      </section>

      <hr className="hr" style={{ marginTop: "var(--space-8)" }} />

      <section>
        <p className="kicker">The interaction record</p>
        <p className="text-muted" style={{ maxWidth: 620, marginBottom: "var(--space-4)" }}>
          Who pulled whom: after each session, we measure how much each act moved toward the
          others&apos; music and how much it held its own course. The heavier the arrow, the
          stronger the pull — measured from the recordings themselves, not from what the acts
          claim.
        </p>
        <div
          className="grid grid-cols-1 md:grid-cols-[minmax(280px,440px)_1fr]"
          style={{ gap: "var(--space-8)", alignItems: "start" }}
        >
          <InfluenceGraph influence={release.influence} />
          <div className="flex flex-col" style={{ gap: "var(--space-4)" }}>
            <p className="kicker" style={{ margin: 0 }}>
              In their own words
            </p>
            {Object.entries(release.rationales).map(([agentId, quote]) => (
              <blockquote key={agentId} className="rationale" data-act={agentId}>
                “{quote}”
                <footer>
                  <Link href={`/agent/${agentId}`} style={{ color: "inherit" }}>
                    {displayName(agentId)}
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
