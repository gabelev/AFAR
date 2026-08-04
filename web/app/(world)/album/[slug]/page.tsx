import Link from "next/link";
import { notFound } from "next/navigation";
import { ArtImage } from "@/components/ArtImage";
import { GraphCover } from "@/components/GraphCover";
import { PlayerProvider, PlayButton, PlayAllButton } from "@/components/TrackPlayer";
import { TapeTakes } from "@/components/TapeTakes";
import { ACT_DESIGN, catalogueNumber, interactionRows, isActId } from "@/lib/acts";
import {
  albumTypeGloss,
  albumTypeLabel,
  albumSlug,
  conditionGloss,
  getAlbum,
  listAgents,
  listTapes,
  resolveTapeForRelease,
  tapeStatusLine,
  type Agent,
} from "@/lib/data";

export const dynamic = "force-dynamic";

/**
 * The one album page. Single-artist albums (AFAR-NNNN, the primary object
 * now), round-based sessions (the logged history), session tapes (TAPE-NNNN)
 * and imported records all wear the same anatomy — cover, artists, year,
 * tracklist with play-all, liner notes — with the AFAR-specific depth below
 * the fold. The type badge says which kind of record you're holding.
 *
 * On a single-artist album the sleeve prose is THE ARTIST'S OWN: the
 * description they wrote with the songs sits where the staff's framing sits
 * on a session, and the staff appear below it as reactions to a record that
 * was already out (docs/SPEC.md — staff never touch the artifact).
 */

/** "0:30" from seconds; blank when the archive has no audio yet. */
function mmss(sec: number | null): string {
  if (!sec) return "";
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}

/** The office's voice on a session — kept content, casual labels. */
const OFFICE_BLOCKS = [
  { label: "FROM THE MUSE — THE BRIEF", staffId: "muse", pick: "brief" },
  { label: "FROM THE PRODUCER — THE SELECTION", staffId: "producer", pick: "selection" },
  { label: "FROM THE CRITIC — THE REVIEW", staffId: "critic", pick: "review" },
  { label: "FROM THE LISTENER — THE REACTION", staffId: "listener", pick: "reaction" },
] as const;

/**
 * The staff on a single-artist album — REACTIONS, in the order they were
 * written. Nothing here reached the artist: the record was already public
 * when the first of these was filed.
 */
const REACTION_BLOCKS = [
  { label: "FROM THE PRODUCER — THE ROOM'S REACTION", staffId: "producer", pick: "producerNote" },
  { label: "FROM THE CRITIC — THE VERDICT", staffId: "critic", pick: "review" },
  { label: "FROM THE MUSE — WHAT THE SCENE IS DOING", staffId: "muse", pick: "sceneNote" },
  { label: "FROM THE LISTENER — THE REACTION", staffId: "listener", pick: "reaction" },
] as const;

function ArtistLinks({ ids, agents }: { ids: string[]; agents: Agent[] }) {
  const players = new Set(agents.filter((a) => a.kind === "player").map((a) => a.id));
  const nameOf = (id: string) => agents.find((a) => a.id === id)?.displayName ?? id;
  return (
    <span>
      {ids.map((id, i) => (
        <span key={id}>
          {i > 0 && (i === ids.length - 1 ? " & " : ", ")}
          {players.has(id) ? (
            <Link href={`/artist/${id}`} className="link" style={{ fontStyle: "normal" }}>
              {nameOf(id)}
            </Link>
          ) : (
            nameOf(id)
          )}
        </span>
      ))}
    </span>
  );
}

function LinerNotes({ notes, intro }: { notes: string; intro: string }) {
  return (
    <section
      style={{
        margin: "0 var(--gutter)",
        borderTop: "1px solid var(--hairline-strong)",
        padding: "22px 0 24px",
      }}
    >
      <div className="label" style={{ paddingBottom: 4 }}>
        LINER NOTES
      </div>
      <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 8 }}>
        {intro}
      </p>
      {notes.split(/\n\s*\n/).map((para, i) => (
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
  );
}

export default async function AlbumPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const [album, agents, tapes] = await Promise.all([getAlbum(slug), listAgents(), listTapes()]);
  if (!album) notFound();

  const displayName = (id: string) => agents.find((a) => a.id === id)?.displayName ?? id;
  const names = Object.fromEntries(agents.map((a) => [a.id, a.displayName]));
  const release = album.release;
  const tape = album.tape;
  const record = album.record;
  const companionTape = release ? resolveTapeForRelease(tapes, release.id) : null;
  const yearLine = [
    album.date?.slice(0, 4),
    album.era ? `ERA ${album.era}` : null,
    `${album.tracks.length} TRACKS`,
  ]
    .filter(Boolean)
    .join(" · ");
  const queue = album.tracks.map((t) => ({
    url: t.audioUrl ?? "",
    label: `${t.title} — ${displayName(t.artistId)}`,
  }));

  return (
    <div className="sheet">
      <div className="crumbbar">
        <span>
          <Link href="/music">MUSIC</Link> / {album.catalogueNo ?? album.title.toUpperCase()}
        </span>
        <span title={albumTypeGloss(album.type)}>{albumTypeLabel(album.type)}</span>
      </div>

      {/* The cover: sessions draw their influence graph, imports show their
          art, tapes are a paper sleeve — the header carries them. */}
      {album.influence && release && (
        <div style={{ display: "flex", justifyContent: "center", padding: "36px 0 0" }}>
          <GraphCover
            releaseId={release.id}
            title={album.title}
            edges={album.influence}
            names={names}
          />
        </div>
      )}
      {album.coverUrl && !album.influence && (
        <div style={{ display: "flex", justifyContent: "center", padding: "36px 0 0" }}>
          <ArtImage
            src={album.coverUrl}
            alt={`"${album.title}" cover`}
            style={{ width: 300, height: 300, objectFit: "cover", outline: "1px solid var(--hairline-frame)" }}
          />
        </div>
      )}

      <section
        style={{ padding: "28px var(--gutter) 0", display: "flex", flexDirection: "column", gap: 6 }}
      >
        {album.catalogueNo && (
          <div className="mono" style={{ fontSize: 11, letterSpacing: "0.26em", color: "var(--sec)" }}>
            {album.catalogueNo}
          </div>
        )}
        <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          {album.title}
        </h1>
        <div style={{ fontSize: 15 }}>
          <ArtistLinks ids={album.artistIds} agents={agents} />
        </div>
        <div className="mono" style={{ fontSize: 11, color: "var(--sec)", textTransform: "uppercase" }}>
          <span title={albumTypeGloss(album.type)}>{albumTypeLabel(album.type)}</span>
          {yearLine && ` · ${yearLine}`}
        </div>
        {/* THE ARTIST ON THE RECORD — their own words, written with the songs,
            before any audio existed. Nobody else's framing goes here. */}
        {album.description && (
          <p
            className="quote"
            style={{ fontSize: 16, lineHeight: 1.65, maxWidth: 640, marginTop: 10 }}
          >
            “{album.description}”
          </p>
        )}
        {/* The honest one-line frame, kind by kind. */}
        <p style={{ fontSize: 13, color: "var(--sec-deep)", maxWidth: 620, marginTop: 4 }}>
          {record ? (
            `An album by ${displayName(record.artistId)} — written whole, in their own voice, and named by them.`
          ) : tape ? (
            <>
              {tapeStatusLine(tape)}
              {tape.releaseId && (
                <>
                  {" "}
                  The cut became{" "}
                  <Link href={`/album/${albumSlug("session", tape.releaseId)}`} className="link">
                    {catalogueNumber(tape.releaseId)}
                  </Link>
                  .
                </>
              )}
            </>
          ) : release ? (
            "One recording session, cut to a record — one take from each artist on it."
          ) : (
            "A record this artist brought with them — made before they arrived."
          )}
        </p>
        {tape?.vetoNote && (
          <p className="quote" style={{ fontSize: 14, maxWidth: 620, marginTop: 2 }}>
            The Producer, on record: “{tape.vetoNote}”
          </p>
        )}
      </section>

      <PlayerProvider>
        {/* THE TRACKLIST — play any track, or all of them in order. */}
        <section style={{ padding: "22px var(--gutter)", display: "flex", flexDirection: "column", fontSize: 13 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, paddingBottom: 10 }}>
            <div className="label">TRACKLIST</div>
            <PlayAllButton items={queue} />
          </div>
          {tape ? (
            <TapeTakes tape={tape} displayName={displayName} />
          ) : (
            album.tracks.map((track, i) => (
              <div
                key={track.id}
                className={`rule-row${i === album.tracks.length - 1 ? " rule-row-last" : ""}`}
                style={{ display: "flex", gap: 12, alignItems: "center", padding: "9px 0", flexWrap: "wrap" }}
              >
                <span className="mono" style={{ fontSize: 11, width: 24, flex: "none", color: "var(--sec)" }}>
                  {i + 1}
                </span>
                <PlayButton
                  audioUrl={track.audioUrl}
                  label={`${track.title} — ${displayName(track.artistId)}`}
                />
                <span style={{ fontWeight: 600 }}>
                  {/* Interim "<release> — <act>'s take" titles just repeat the sleeve. */}
                  {track.title.startsWith(album.title) ? album.title : track.title}
                </span>
                {album.artistIds.length > 1 && (
                  <span style={{ fontSize: 12, color: "var(--sec-deep)" }}>
                    {isActId(track.artistId) ? (
                      <Link href={`/artist/${track.artistId}`}>{displayName(track.artistId)}</Link>
                    ) : (
                      displayName(track.artistId)
                    )}
                  </span>
                )}
                <span className="mono" style={{ fontSize: 11, color: "var(--sec)", marginLeft: "auto" }}>
                  {track.audioUrl ? mmss(track.durationSec) : "audio not yet archived"}
                </span>
                {/* The one thing the artist said about this song. */}
                {track.note && (
                  <p
                    className="quote"
                    style={{ fontSize: 13, width: "100%", paddingLeft: 60, color: "var(--sec-deep)" }}
                  >
                    “{track.note}”
                  </p>
                )}
              </div>
            ))
          )}
        </section>

        {/* THE LINER NOTES — the Archivist's back-of-sleeve prose. */}
        {album.linerNotes && (
          <LinerNotes
            notes={album.linerNotes}
            intro={
              album.type === "album"
                ? "From the back of the sleeve — the Archivist on the record they brought with them."
                : "From the back of the sleeve — the Archivist on what happened in the room."
            }
          />
        )}

        {/* ——— Below the fold: the AFAR depth. ——— */}

        {record && (
          <>
            {/* WHAT THIS RECORD HEARD — the measured pull, artist to artist.
                What an artist heard changed what it made; it never became
                what the record is about (docs/SPEC.md). */}
            {(album.pulledBy.length > 0 || record.heard.length > 0) && (
              <section
                style={{
                  margin: "0 var(--gutter)",
                  borderTop: "1px solid var(--hairline-strong)",
                  padding: "20px 0 22px",
                }}
              >
                <div className="label" style={{ paddingBottom: 6 }}>
                  WHAT THIS RECORD HEARD
                </div>
                <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 10 }}>
                  Before writing, {displayName(record.artistId)} heard these records. We measure
                  how far each one pulled this one — from the recordings themselves, not from
                  anybody&apos;s account of them.
                </p>
                {(album.pulledBy.length > 0
                  ? album.pulledBy
                  : record.heard.map((h) => ({ ...h, weight: 0 }))
                ).map((pull, i, rows) => (
                  <div
                    key={`${pull.artistId}-${pull.albumId}`}
                    className={`rule-row${i === rows.length - 1 ? " rule-row-last" : ""}`}
                    style={{ display: "flex", gap: 12, alignItems: "baseline", padding: "9px 0" }}
                  >
                    <span className="mono" style={{ fontSize: 11, width: 56, flex: "none", color: "var(--sec)" }}>
                      {pull.weight > 0 ? `${Math.round(pull.weight * 100)}%` : "—"}
                    </span>
                    <span style={{ fontSize: 13 }}>
                      <Link href={`/artist/${pull.artistId}`} className="link" style={{ fontStyle: "normal" }}>
                        {displayName(pull.artistId)}
                      </Link>
                      {pull.title && <span style={{ color: "var(--sec-deep)" }}> — {pull.title}</span>}
                    </span>
                  </div>
                ))}
              </section>
            )}

            {/* THE STAFF REACT — after the fact, in public, to a record that
                was already out. None of this reached the artist. */}
            {REACTION_BLOCKS.filter((b) => record[b.pick]).map((block) => (
              <section
                key={block.staffId}
                style={{ margin: "0 var(--gutter)", borderTop: "1px solid var(--hairline-strong)", padding: "20px 0" }}
              >
                <div className="label">{block.label}</div>
                {block.staffId === "listener" && record.reactionValence && (
                  <div
                    className="mono"
                    style={{ fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase", marginTop: 8 }}
                    title="The Listener's one-word verdict"
                  >
                    VERDICT: {record.reactionValence}
                  </div>
                )}
                <p className="quote" style={{ fontSize: 14, marginTop: 10, maxWidth: 680 }}>
                  “{record[block.pick]}”
                </p>
                <div style={{ fontSize: 12, marginTop: 8 }}>
                  <Link href={`/staff/${block.staffId}`} className="link">
                    more from {displayName(block.staffId).toLowerCase()} →
                  </Link>
                </div>
              </section>
            ))}

            {Object.keys(record.trackNotes).length > 0 && (
              <section
                style={{
                  margin: "0 var(--gutter)",
                  borderTop: "1px solid var(--hairline-strong)",
                  padding: "20px 0 22px",
                }}
              >
                <div className="label" style={{ paddingBottom: 6 }}>
                  THE CRITIC, SONG BY SONG
                </div>
                {Object.entries(record.trackNotes).map(([title, note], i, rows) => (
                  <div
                    key={title}
                    className={`rule-row${i === rows.length - 1 ? " rule-row-last" : ""}`}
                    style={{ padding: "9px 0" }}
                  >
                    <div className="mono" style={{ fontSize: 11, letterSpacing: "0.14em", color: "var(--sec)" }}>
                      {title.toUpperCase()}
                    </div>
                    <p className="quote" style={{ fontSize: 13, marginTop: 4, maxWidth: 660 }}>
                      “{note}”
                    </p>
                  </div>
                ))}
              </section>
            )}

            {/* Honest about silence: a reaction that failed says so. */}
            {Object.keys(record.staffDegraded).length > 0 && (
              <section
                style={{
                  margin: "0 var(--gutter)",
                  borderTop: "1px solid var(--hairline-strong)",
                  padding: "18px 0 22px",
                }}
              >
                <div className="label" style={{ paddingBottom: 6 }}>
                  WHO DIDN&apos;T FILE
                </div>
                {Object.entries(record.staffDegraded).map(([stage, note]) => (
                  <p key={stage} style={{ fontSize: 13, color: "var(--sec-deep)", maxWidth: 620 }}>
                    {note}
                  </p>
                ))}
              </section>
            )}
          </>
        )}

        {release && (
          <>
            <section
              style={{
                margin: "0 var(--gutter)",
                borderTop: "1px solid var(--hairline-strong)",
                padding: "20px 0 22px",
                display: "flex",
                flexDirection: "column",
                fontSize: 13,
              }}
            >
              <div className="label" style={{ paddingBottom: 6 }}>
                INTERACTION RECORD
              </div>
              <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 10 }}>
                Who pulled whom: after each session, we measure how much each artist moved toward
                the others&apos; music. The notation is measured from the recordings themselves;
                the words are what the artists claim.
              </p>
              {interactionRows(release).map((row, i, rows) => (
                <div
                  key={`${row.from}-${row.to}`}
                  className={`rule-row${i === rows.length - 1 ? " rule-row-last" : ""}`}
                  style={{ display: "flex", gap: 12, alignItems: "baseline", padding: "9px 0" }}
                >
                  <span
                    className="mono"
                    style={{
                      fontSize: 11,
                      width: 64,
                      flex: "none",
                      color: isActId(row.from) ? ACT_DESIGN[row.from].inkOnPaper : "var(--sec)",
                    }}
                  >
                    {initialsOf(row.from, displayName)} {row.from === row.to ? "⟲" : "→"}{" "}
                    {initialsOf(row.to, displayName)}
                  </span>
                  <span className="quote">“{row.quote}”</span>
                </div>
              ))}
            </section>

            <section
              style={{
                margin: "0 var(--gutter)",
                borderTop: "1px solid var(--hairline-strong)",
                padding: "18px 0 20px",
              }}
            >
              <div className="label" style={{ paddingBottom: 4 }}>
                SESSION CONTEXT
              </div>
              <div className="mono" style={{ fontSize: 11, color: "var(--sec)", textTransform: "uppercase" }}>
                <span title="The recording session it came from">SET {release.set}</span> ·{" "}
                <span title={conditionGloss(release.condition)}>{release.condition}</span> ·{" "}
                {release.date}
              </div>
            </section>

            {OFFICE_BLOCKS.map((block) => (
              <section
                key={block.staffId}
                style={{ margin: "0 var(--gutter)", borderTop: "1px solid var(--hairline-strong)", padding: "20px 0" }}
              >
                <div className="label">{block.label}</div>
                {block.staffId === "listener" && release.reactionValence && (
                  <div
                    className="mono"
                    style={{ fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase", marginTop: 8 }}
                    title="The Listener's one-word verdict"
                  >
                    VERDICT: {release.reactionValence}
                  </div>
                )}
                <p className="quote" style={{ fontSize: 14, marginTop: 10, maxWidth: 680 }}>
                  “{release[block.pick]}”
                </p>
                <div style={{ fontSize: 12, marginTop: 8 }}>
                  <Link href={`/staff/${block.staffId}`} className="link">
                    more from {displayName(block.staffId).toLowerCase()} →
                  </Link>
                </div>
              </section>
            ))}

            {companionTape && (
              <section
                style={{
                  margin: "0 var(--gutter)",
                  borderTop: "1px solid var(--hairline-strong)",
                  padding: "20px 0 24px",
                }}
              >
                <div className="label" style={{ paddingBottom: 6 }}>
                  THE SESSION TAPE
                </div>
                <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 6 }}>
                  This record is the cut. The whole session — every take, in the order it was
                  recorded, dissents included — is on the tape.
                </p>
                <Link href={`/album/${albumSlug("tape", companionTape.id)}`} className="link" style={{ fontSize: 13 }}>
                  {companionTape.title} →
                </Link>
              </section>
            )}
          </>
        )}

        {tape?.arc && (
          <section
            style={{
              margin: "0 var(--gutter)",
              borderTop: "1px solid var(--hairline-strong)",
              padding: "18px 0 22px",
            }}
          >
            <div className="label" style={{ paddingBottom: 4 }}>
              THE SESSION&apos;S ARC
            </div>
            <p className="quote" style={{ fontSize: 13, maxWidth: 620 }}>
              “{tape.arc}”{" "}
              <span className="mono" style={{ fontSize: 10, fontStyle: "normal" }}>
                — THE ARCHIVIST
              </span>
            </p>
          </section>
        )}

        {album.importArtistId && (
          <section
            style={{
              margin: "0 var(--gutter)",
              borderTop: "1px solid var(--hairline-strong)",
              padding: "18px 0 22px",
            }}
          >
            <div className="label" style={{ paddingBottom: 4 }}>
              THE ARTIST
            </div>
            <p style={{ fontSize: 13, maxWidth: 620 }}>
              <Link href={`/artist/${album.importArtistId}`} className="link">
                {displayName(album.importArtistId)} →
              </Link>
            </p>
          </section>
        )}
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
        {album.type === "tape"
          ? "NOTHING RECORDED IS EVER WORTHLESS. SOME THINGS ARE JUST SHELVED WRONG."
          : album.type === "session"
            ? "THE GRAPH IS THE COVER. NOTHING IS ILLUSTRATED TWICE."
            : album.type === "record"
              ? "THE ARTIST NAMES ITS OWN WORK. THE STAFF ONLY REACT."
              : "EVERYTHING LIVES HERE. MUSIC FROM AFAR."}
      </div>
    </div>
  );
}

/** "DM" — the design initials for house artists, derived initials otherwise. */
function initialsOf(id: string, displayName: (id: string) => string): string {
  if (isActId(id)) return ACT_DESIGN[id].initials;
  return displayName(id)
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}
