import Link from "next/link";
import { PressPhoto } from "@/components/PressPhoto";
import { ACT_DESIGN, isActId } from "@/lib/acts";
import { stanceWord, type Agent } from "@/lib/data";

/**
 * One artist card for the flat roster grids (home, /music). Every artist
 * gets the same card — portrait, name, a one-word stance and the genre
 * line. No tiers, no addresses: the roster is one list.
 */
export function ArtistCard({ agent }: { agent: Agent }) {
  return (
    <Link href={`/artist/${agent.id}`} data-act={agent.id} className="roster-card">
      <PressPhoto
        pressSrc={isActId(agent.id) ? ACT_DESIGN[agent.id].press : undefined}
        imageUrl={agent.imageUrl}
        palette={agent.palette}
        alt={`${agent.displayName} press photo`}
        className={isActId(agent.id) ? "roster-card-photo" : "roster-card-photo photo-smooth"}
      />
      <div style={{ padding: "10px 12px 12px", display: "flex", flexDirection: "column", gap: 3 }}>
        <div style={{ fontSize: 18, fontWeight: 600 }}>{agent.displayName}</div>
        <div
          className="mono"
          style={{
            fontSize: 10,
            letterSpacing: "0.2em",
            color: "var(--act-ink)",
            textTransform: "uppercase",
          }}
        >
          {stanceWord(agent)}
        </div>
        {agent.genreLine && (
          <div className="mono" style={{ fontSize: 10, color: "var(--sec)" }}>
            {agent.genreLine}
          </div>
        )}
      </div>
    </Link>
  );
}
