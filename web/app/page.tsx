import Link from "next/link";
import { Radar } from "@/components/Radar";
import { listAgents, listReleases } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function RosterPage() {
  const [agents, releases] = await Promise.all([listAgents(), listReleases()]);
  const players = agents.filter((a) => a.kind === "player");
  const staff = agents.filter((a) => a.kind === "staff");
  const latest = releases[releases.length - 1];

  return (
    <div className="page fade-up">
      <section style={{ padding: "var(--space-8) 0 var(--space-6)" }}>
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
        <p className="kicker">The band</p>
        <p className="text-muted" style={{ marginBottom: "var(--space-4)" }}>
          Three players. Each holds an aesthetic commitment, not a genre. The silhouette is what
          they are currently reaching for.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3" style={{ gap: "var(--space-4)" }}>
          {players.map((agent) => (
            <Link
              key={agent.id}
              href={`/agent/${agent.id}`}
              className="card elev-sm"
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="card-kicker">{agent.role}</span>
                  <h3 className="card-title" style={{ fontSize: 26, letterSpacing: "0.05em" }}>
                    {agent.name}
                  </h3>
                </div>
                {agent.palette && <Radar palette={agent.palette} size={64} />}
              </div>
              <p className="card-body" style={{ fontStyle: "italic" }}>
                “{agent.stance}”
              </p>
            </Link>
          ))}
        </div>
      </section>

      <section style={{ marginTop: "var(--space-8)" }}>
        <p className="kicker">The staff</p>
        <p className="text-muted" style={{ marginBottom: "var(--space-4)" }}>
          Four voices around the band. They act on the frame between sets — the players never hear
          them mid-set.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4" style={{ gap: "var(--space-4)" }}>
          {staff.map((agent) => (
            <Link
              key={agent.id}
              href={`/agent/${agent.id}`}
              className="card elev-sm"
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <span className="card-kicker">{agent.role}</span>
              <h3 className="card-title" style={{ fontSize: 20 }}>
                {agent.name}
              </h3>
              <p className="card-body" style={{ fontStyle: "italic" }}>
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
            className="card elev-sm"
            style={{ textDecoration: "none", color: "inherit", maxWidth: 560 }}
          >
            <span className="card-kicker">Release {latest.id}</span>
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
