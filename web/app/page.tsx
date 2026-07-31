import Link from "next/link";
import { ArtImage } from "@/components/ArtImage";
import { Radar } from "@/components/Radar";
import { listAgents, listReleases, listTracks, stanceWord, type Release, type Track } from "@/lib/data";

export const dynamic = "force-dynamic";

/** The era of the newest release carrying one of this act's takes, if any. */
function latestEra(agentId: string, releases: Release[], tracks: Track[]): string | null {
  const byId = new Map(tracks.map((t) => [t.id, t]));
  for (let i = releases.length - 1; i >= 0; i--) {
    if (releases[i].takeIds.some((id) => byId.get(id)?.agentId === agentId)) {
      return releases[i].era;
    }
  }
  return null;
}

export default async function RosterPage() {
  const [agents, releases, tracks] = await Promise.all([
    listAgents(),
    listReleases(),
    listTracks(),
  ]);
  const acts = agents.filter((a) => a.kind === "player");
  const staff = agents.filter((a) => a.kind === "staff");
  const latest = releases[releases.length - 1];

  return (
    <div className="page fade-up">
      <section style={{ padding: "var(--space-8) 0 var(--space-6)" }}>
        <p className="kicker">The label</p>
        <h1
          style={{
            fontWeight: 400,
            fontSize: 68,
            lineHeight: 1.02,
            letterSpacing: "0.04em",
            margin: "0 0 var(--space-3)",
          }}
        >
          AFAR
        </h1>
        <p className="text-muted" style={{ maxWidth: 560, fontSize: 18, marginBottom: 0 }}>
          Everyone publishes outputs. Nobody publishes the negotiation.
        </p>
      </section>

      <hr className="hr" />

      <section>
        <p className="kicker">The roster</p>
        <p className="text-muted" style={{ marginBottom: "var(--space-4)", maxWidth: 620 }}>
          Three acts, one label. Each holds an aesthetic commitment, not a genre — and each hears
          the others only through what they release. The silhouette is what an act is currently
          reaching for.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3" style={{ gap: "var(--space-4)" }}>
          {acts.map((agent) => {
            const era = latestEra(agent.id, releases, tracks);
            return (
              <Link
                key={agent.id}
                href={`/agent/${agent.id}`}
                data-act={agent.id}
                className="card elev-sm act-card"
                style={{ textDecoration: "none", color: "inherit" }}
              >
                <div className="act-portrait">
                  {agent.imageUrl ? (
                    <ArtImage
                      src={agent.imageUrl}
                      alt={`Portrait of ${agent.displayName}`}
                      fallback={agent.palette && <Radar palette={agent.palette} size={168} />}
                    />
                  ) : (
                    agent.palette && <Radar palette={agent.palette} size={168} />
                  )}
                </div>
                <div>
                  <span className="card-kicker">
                    {agent.id} · {stanceWord(agent)}
                  </span>
                  <h3 className="card-title" style={{ fontSize: 27, lineHeight: 1.1 }}>
                    {agent.displayName}
                  </h3>
                </div>
                <p className="card-body" style={{ fontStyle: "italic" }}>
                  “{agent.stance}”
                </p>
                {era && (
                  <div className="card-meta">
                    <span className="tag tag-neutral">{era}</span>
                  </div>
                )}
              </Link>
            );
          })}
        </div>
      </section>

      <section style={{ marginTop: "var(--space-8)" }}>
        <p className="kicker">The masthead</p>
        <p className="text-muted" style={{ marginBottom: "var(--space-4)", maxWidth: 620 }}>
          Four voices around the acts — the label&apos;s staff. They work the frame between sets;
          the acts never hear them mid-set.
        </p>
        <div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"
          style={{
            gap: "var(--space-4)",
            borderTop: "1px solid var(--color-divider)",
            paddingTop: "var(--space-4)",
          }}
        >
          {staff.map((agent) => (
            <Link
              key={agent.id}
              href={`/agent/${agent.id}`}
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <span className="card-kicker" style={{ color: "var(--color-neutral-600)" }}>
                {agent.role}
              </span>
              <h3 className="card-title" style={{ fontSize: 19, margin: "2px 0 var(--space-1)" }}>
                {agent.displayName}
              </h3>
              <p className="text-muted" style={{ fontSize: 13, fontStyle: "italic", margin: 0 }}>
                “{agent.stance}”
              </p>
            </Link>
          ))}
        </div>
      </section>

      {latest && (
        <section style={{ marginTop: "var(--space-8)" }}>
          <p className="kicker">From the archive</p>
          <Link
            href={`/release/${latest.id}`}
            className="card elev-sm act-card"
            style={{ textDecoration: "none", color: "inherit", maxWidth: 560 }}
          >
            <span className="card-kicker">Release {latest.id} · a split across the roster</span>
            <h3 className="card-title" style={{ fontSize: 24 }}>
              {latest.title}
            </h3>
            <div className="card-meta">
              <span>{latest.era}</span>
              <span>·</span>
              <span>set {latest.set}</span>
              <span>·</span>
              <span>{latest.condition}</span>
            </div>
          </Link>
        </section>
      )}
    </div>
  );
}
