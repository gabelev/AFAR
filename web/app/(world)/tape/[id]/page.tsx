import Link from "next/link";
import { notFound } from "next/navigation";
import { PlayerProvider } from "@/components/TrackPlayer";
import { TapeTakes } from "@/components/TapeTakes";
import { catalogueNumber } from "@/lib/acts";
import {
  conditionGloss,
  getRelease,
  getTape,
  listAgents,
  tapeNumber,
  tapeStatusLine,
} from "@/lib/data";

export const dynamic = "force-dynamic";

/**
 * A session tape's page — the release page's pattern with kind-aware
 * framing (the vault doctrine: every session releases; tapes ≠ releases).
 * A companion tape points home at its release; a standalone tape (a vetoed
 * session, an abandoned set, a solo run) holds the shelf alone, its status
 * framed honestly in the first two lines.
 */
export default async function TapePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const tape = await getTape(id);
  if (!tape) notFound();

  const [agents, release] = await Promise.all([
    listAgents(),
    tape.releaseId ? getRelease(tape.releaseId) : Promise.resolve(null),
  ]);
  const displayName = (agentId: string) =>
    agents.find((a) => a.id === agentId)?.displayName ?? agentId;

  return (
    <div className="sheet">
      <div className="crumbbar">
        <span>
          <Link href="/world">CATALOGUE</Link> / {tapeNumber(tape.id)}
        </span>
        <span>SESSION TAPE</span>
      </div>

      <section
        style={{ padding: "36px var(--gutter) 0", display: "flex", flexDirection: "column", gap: 6 }}
      >
        <div className="mono" style={{ fontSize: 11, letterSpacing: "0.26em", color: "var(--sec)" }}>
          {tapeNumber(tape.id)} · FROM THE VAULT
        </div>
        <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          {tape.title}
        </h1>
        <div className="mono" style={{ fontSize: 11, color: "var(--sec)", textTransform: "uppercase" }}>
          {tape.date} ·{" "}
          <span title="The recording session's rounds — every act takes one take per round">
            {tape.rounds} ROUNDS
          </span>{" "}
          · <span title={conditionGloss(tape.condition)}>{tape.condition}</span> ·{" "}
          {tape.takes.length} TAKES
        </div>
        {/* The honest frame — what happened to this session, first thing. */}
        <p style={{ fontSize: 14, color: "var(--sec-deep)", maxWidth: 620, marginTop: 6 }}>
          {tapeStatusLine(tape)}
          {release && (
            <>
              {" "}
              The cut became{" "}
              <Link href={`/release/${release.id}`} className="link">
                {catalogueNumber(release.id)} · {release.title}
              </Link>
              .
            </>
          )}
        </p>
        {tape.vetoNote && (
          <p className="quote" style={{ fontSize: 14, maxWidth: 620, marginTop: 4 }}>
            The Producer, on record: “{tape.vetoNote}”
          </p>
        )}
      </section>

      {/* THE LINER NOTES — the Archivist's sleeve, typographically first. */}
      {tape.linerNotes ? (
        <section
          style={{
            margin: "22px var(--gutter) 0",
            borderTop: "1px solid var(--hairline-strong)",
            padding: "20px 0 4px",
          }}
        >
          <div className="label" style={{ paddingBottom: 4 }}>
            LINER NOTES
          </div>
          {tape.arc && (
            <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 8 }}>
              {tape.arc}
            </p>
          )}
          {tape.linerNotes.split(/\n\s*\n/).map((para, i) => (
            <p
              key={i}
              className="quote"
              style={{ fontSize: 15, lineHeight: 1.7, maxWidth: 680, marginTop: i === 0 ? 2 : 12 }}
            >
              {para}
            </p>
          ))}
          <div
            className="mono"
            style={{ fontSize: 10, letterSpacing: "0.18em", color: "var(--sec)", marginTop: 14 }}
          >
            — THE ARCHIVIST
          </div>
        </section>
      ) : (
        <section style={{ margin: "22px var(--gutter) 0", padding: "4px 0" }}>
          <p className="mono" style={{ fontSize: 12, color: "var(--sec-deep)", maxWidth: 620 }}>
            The Archivist did not file notes for this tape; the takes speak for themselves.
          </p>
        </section>
      )}

      {/* THE TAPE — every take, round order, markers and dissents on row. */}
      <PlayerProvider>
        <section
          style={{
            margin: "16px var(--gutter) 0",
            borderTop: "1px solid var(--hairline-strong)",
            padding: "20px 0 28px",
            fontSize: 13,
          }}
        >
          <div className="label" style={{ paddingBottom: 6 }}>
            THE TAPE
          </div>
          <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 8 }}>
            Every take from the session, in the order it was recorded.
            {tape.status === "released" && " ● marks the takes that made the release."}
          </p>
          <TapeTakes tape={tape} displayName={displayName} />
        </section>
      </PlayerProvider>

      <div
        className="mono"
        style={{
          marginTop: "auto",
          padding: "18px var(--gutter) 28px",
          fontSize: 10,
          letterSpacing: "0.14em",
          color: "var(--sec)",
        }}
      >
        NOTHING RECORDED IS EVER WORTHLESS. SOME THINGS ARE JUST SHELVED WRONG.
      </div>
    </div>
  );
}
