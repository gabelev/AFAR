import Link from "next/link";
import { PlayButton } from "@/components/TrackPlayer";
import { ACT_DESIGN, isActId } from "@/lib/acts";
import type { Tape, TapeTake } from "@/lib/data";

/**
 * The session tape's take list: every take, in round order, exactly as the
 * session happened. Selected-take markers (● ON THE RELEASE), the
 * Archivist's call-outs, and logged judge dissents ride the rows. Must
 * render inside a PlayerProvider — one audio owner per page, always.
 */
export function TapeTakes({
  tape,
  displayName,
}: {
  tape: Tape;
  displayName: (agentId: string) => string;
}) {
  const rows = tape.takes;
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {rows.map((take, i) => (
        <TapeTakeRow
          key={`${take.round}-${take.agentId}`}
          take={take}
          last={i === rows.length - 1}
          newRound={i === 0 || rows[i - 1].round !== take.round}
          displayName={displayName}
        />
      ))}
    </div>
  );
}

function TapeTakeRow({
  take,
  last,
  newRound,
  displayName,
}: {
  take: TapeTake;
  last: boolean;
  newRound: boolean;
  displayName: (agentId: string) => string;
}) {
  const accent = isActId(take.agentId) ? ACT_DESIGN[take.agentId].inkOnPaper : "var(--sec)";
  return (
    <div
      className={`rule-row${last ? " rule-row-last" : ""}`}
      style={{ display: "flex", flexDirection: "column", gap: 4, padding: "8px 0" }}
    >
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <span
          className="mono"
          style={{
            fontSize: 11,
            width: 40,
            flex: "none",
            color: newRound ? "var(--sec-deep)" : "var(--sec-faint)",
          }}
          title="The round this take was recorded in"
        >
          {newRound ? `R${String(take.round + 1).padStart(2, "0")}` : ""}
        </span>
        <span style={{ fontWeight: 600, width: 150, flex: "none", fontSize: 13 }}>
          {isActId(take.agentId) ? (
            <Link href={`/artist/${take.agentId}`}>{displayName(take.agentId)}</Link>
          ) : (
            displayName(take.agentId)
          )}
        </span>
        <PlayButton
          audioUrl={take.audioUrl}
          label={`${take.title ?? `Round ${take.round + 1} take`} — ${displayName(take.agentId)}`}
        />
        {take.title && (
          <span className="quote" style={{ fontSize: 13 }}>
            “{take.title}”
          </span>
        )}
        {take.selected && (
          <span
            className="mono"
            style={{ fontSize: 10, letterSpacing: "0.14em", color: accent, flex: "none" }}
            title="The Producer put this take on the release"
          >
            ● ON THE RELEASE
          </span>
        )}
        {take.durationSec ? (
          <span className="mono" style={{ fontSize: 11, color: "var(--sec)", marginLeft: "auto" }}>
            {`${Math.floor(take.durationSec / 60)}:${String(take.durationSec % 60).padStart(2, "0")}`}
          </span>
        ) : null}
      </div>
      {take.line && (
        <div className="mono" style={{ fontSize: 11, color: "var(--sec)", paddingLeft: 52 }}>
          “{take.line}”
        </div>
      )}
      {take.dissent && (
        <div
          className="mono"
          style={{ fontSize: 11, color: "var(--oxide)", paddingLeft: 52 }}
          title="A logged voice from the Producer's panel that wanted a different cut"
        >
          DISSENT ON RECORD: {take.dissent}
        </div>
      )}
      {take.callout && (
        <div className="quote" style={{ fontSize: 13, paddingLeft: 52, maxWidth: 620 }}>
          The Archivist: “{take.callout}”
        </div>
      )}
    </div>
  );
}
