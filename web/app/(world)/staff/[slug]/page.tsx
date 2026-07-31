import Link from "next/link";
import { notFound } from "next/navigation";
import { PlayerBar } from "@/components/PlayerBar";
import { PressPhoto } from "@/components/PressPhoto";
import { catalogueNumber } from "@/lib/acts";
import { getAgent, listReleases, stanceWord, type Release } from "@/lib/data";

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
};

export default async function StaffPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const agent = await getAgent(slug);
  if (!agent || agent.kind !== "staff") notFound();
  const work = STAFF_WORK[agent.id];
  const releases = await listReleases();
  const releasesDesc = [...releases].sort((a, b) => b.id.localeCompare(a.id));

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
          <PressPhoto
            pressSrc={`/press/press-${agent.id}.png`}
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
                      view interaction record →
                    </Link>
                  </div>
                </div>
              ))
            )}
          </section>
        )}
      </div>
      <PlayerBar quiet="NOTHING PLAYING" right="THE OFFICE" />
    </>
  );
}
