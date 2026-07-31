import Link from "next/link";
import { notFound } from "next/navigation";
import { PlayerBar } from "@/components/PlayerBar";
import { PressPhoto } from "@/components/PressPhoto";
import { catalogueNumber } from "@/lib/acts";
import {
  getAgent,
  listReleases,
  listTapes,
  stanceWord,
  tapeNumber,
  tapeStatusLine,
  type Release,
} from "@/lib/data";

export const dynamic = "force-dynamic";

/** Which slice of a release is a staff member's body of work, and what to call it. */
const STAFF_WORK: Record<
  string,
  { heading: string; blurb: string; empty: string; pick: (r: Release) => string }
> = {
  muse: {
    heading: "BRIEFS",
    blurb:
      "Each recording session opens with a brief from the Muse — a short note on what the outside world sounds like right now, and a dare about what to do with it.",
    empty: "No briefs in the archive yet. The next era opens with one.",
    pick: (r) => r.brief,
  },
  producer: {
    heading: "SELECTIONS",
    blurb:
      "After each session, the Producer decides which recordings are good enough to release — and says why.",
    empty: "No selections in the archive yet. Nothing has been let through.",
    pick: (r) => r.selection,
  },
  critic: {
    heading: "REVIEWS",
    blurb: "The Critic hears each release after the fact, judges it, and gives it its name.",
    empty: "No reviews in the archive yet. Nothing has been named.",
    pick: (r) => r.review,
  },
  listener: {
    heading: "REACTIONS",
    blurb: "The Listener is a fan, nothing more. These are honest reactions, not judgments.",
    empty: "No reactions in the archive yet. Nobody has been moved.",
    pick: (r) => r.reaction,
  },
  archivist: {
    heading: "LINER NOTES",
    blurb:
      "The Archivist writes the prose on the back of every sleeve — what happened in the room, who did what, what to listen for. The Critic judges; the Archivist contextualizes.",
    empty: "No liner notes in the archive yet. The vault has just opened.",
    pick: (r) => r.linerNotes ?? "",
  },
};

export default async function StaffPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const agent = await getAgent(slug);
  if (!agent || agent.kind !== "staff") notFound();
  const work = STAFF_WORK[agent.id];
  const releases = await listReleases();
  // Only releases where this staff member actually filed (the Archivist's
  // notes are optional per row; everyone else's slices always exist).
  const releasesDesc = [...releases]
    .sort((a, b) => b.id.localeCompare(a.id))
    .filter((r) => (work ? work.pick(r) : false));
  // The Archivist's other body of work: the shelf itself.
  const tapes = agent.id === "archivist" ? await listTapes() : [];
  const tapesDesc = [...tapes].sort((a, b) => b.id.localeCompare(a.id));

  return (
    <>
      <div className="sheet">
        <div className="crumbbar">
          <span>
            <Link href="/world">THE OFFICE</Link> / {agent.displayName}
          </span>
          <span>{stanceWord(agent)}</span>
        </div>

        <header
          className="wrap-sm"
          style={{ padding: "36px var(--gutter) 0", display: "flex", gap: 28, alignItems: "flex-start" }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: 1 }}>
            <h1 style={{ fontSize: 42, fontWeight: 700, letterSpacing: "0.06em" }}>
              {agent.displayName}
            </h1>
            <div className="quote" style={{ fontSize: 17 }}>
              “{agent.stance}”
            </div>
          </div>
          {/* The Archivist has no sprite/press art yet (flagged for the next
              design round — DECISIONS.md); a quiet paper plate holds the
              spot rather than a broken image. */}
          <PressPhoto
            pressSrc={agent.id === "archivist" ? undefined : `/press/press-${agent.id}.png`}
            imageUrl={agent.imageUrl}
            alt={`${agent.displayName} press photo`}
            className="presscard"
          />
        </header>

        {/* The bio — one generated paragraph, reviewed before commit; the
            long-form description stays in the data but the page leads short. */}
        <section
          style={{
            padding: "20px var(--gutter) 0",
            display: "flex",
            flexDirection: "column",
            gap: 10,
            maxWidth: 680,
          }}
        >
          {(agent.bio ? [agent.bio] : agent.description).map((para, i) => (
            <p key={i} style={{ fontSize: 15, lineHeight: 1.65, textWrap: "pretty" }}>
              {para}
            </p>
          ))}
        </section>

        {work && (
          <section
            style={{ padding: "28px var(--gutter) 28px", display: "flex", flexDirection: "column" }}
          >
            <div className="label" style={{ paddingBottom: 6 }}>
              {work.heading}
            </div>
            <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 12 }}>
              {work.blurb}
            </p>
            {releasesDesc.length === 0 ? (
              <p className="mono" style={{ fontSize: 12, color: "var(--sec-deep)" }}>
                {work.empty}
              </p>
            ) : (
              releasesDesc.map((release, i) => (
                <div
                  key={release.id}
                  className={`rule-row${i === releasesDesc.length - 1 ? " rule-row-last" : ""}`}
                  style={{ display: "flex", flexDirection: "column", gap: 8, padding: "14px 0" }}
                >
                  <div
                    className="mono"
                    style={{ fontSize: 11, letterSpacing: "0.14em", color: "var(--sec)", textTransform: "uppercase" }}
                  >
                    {catalogueNumber(release.id)} · {release.title}
                  </div>
                  <p className="quote" style={{ fontSize: 14, maxWidth: 680 }}>
                    “{work.pick(release)}”
                  </p>
                  <div style={{ fontSize: 12 }}>
                    <Link href={`/release/${release.id}`} className="link">
                      view the release →
                    </Link>
                  </div>
                </div>
              ))
            )}
          </section>
        )}

        {/* THE SHELF — the Archivist's tapes, every session on record. */}
        {agent.id === "archivist" && (
          <section
            style={{ padding: "0 var(--gutter) 28px", display: "flex", flexDirection: "column" }}
          >
            <div className="label" style={{ paddingBottom: 6 }}>
              THE SHELF
            </div>
            <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 12 }}>
              Every session&apos;s full tape, shelved public — releases, vetoes, breakdowns,
              solo runs. Nothing recorded sits in a drawer.
            </p>
            {tapesDesc.length === 0 ? (
              <p className="mono" style={{ fontSize: 12, color: "var(--sec-deep)" }}>
                No tapes on the shelf yet. The next session&apos;s tape lands here.
              </p>
            ) : (
              tapesDesc.map((tape, i) => (
                <Link
                  key={tape.id}
                  href={`/tape/${tape.id}`}
                  className={`rule-row${i === tapesDesc.length - 1 ? " rule-row-last" : ""}`}
                  style={{ display: "flex", gap: 14, alignItems: "baseline", padding: "10px 0" }}
                >
                  <span className="mono" style={{ fontSize: 11, width: 84, flex: "none", color: "var(--sec)" }}>
                    {tapeNumber(tape.id)}
                  </span>
                  <span style={{ fontSize: 14, fontWeight: 600, flex: 1 }}>{tape.title}</span>
                  <span
                    className="mono"
                    style={{ fontSize: 10, letterSpacing: "0.14em", color: "var(--sec)", textTransform: "uppercase" }}
                    title={tapeStatusLine(tape)}
                  >
                    {tape.status}
                  </span>
                </Link>
              ))
            )}
          </section>
        )}
      </div>
      <PlayerBar quiet="NOTHING PLAYING" right="THE OFFICE" />
    </>
  );
}
