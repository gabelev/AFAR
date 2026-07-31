import Link from "next/link";
import { notFound } from "next/navigation";
import { AlbumGrid } from "@/components/AlbumGrid";
import { PlayerBar } from "@/components/PlayerBar";
import { PressPhoto } from "@/components/PressPhoto";
import { PlayerProvider, PlayButton } from "@/components/TrackPlayer";
import { Waveform } from "@/components/Waveform";
import { toAlbumCard } from "@/lib/album-cards";
import { ACT_DESIGN, catalogueNumber, isActId } from "@/lib/acts";
import {
  albumSlug,
  criticReviewsForPlayer,
  getAgent,
  listAgents,
  listAlbums,
  listReleases,
  resolveDiscography,
  singleForAct,
  stanceWord,
  type Release,
  type Track,
} from "@/lib/data";

export const dynamic = "force-dynamic";

/**
 * The artist page, streaming anatomy: portrait + name + one plain line,
 * the featured single, the DISCOGRAPHY (every album they appear on, type-
 * filterable), ABOUT — then the AFAR depth below the fold: the Critic's
 * verdicts, the influence ledger, the drift strip.
 */

/** "0:30" from seconds; blank when the archive has no audio yet. */
function duration(track: Track): string {
  if (!track.audioUrl || !track.durationSec) return "";
  return `${Math.floor(track.durationSec / 60)}:${String(track.durationSec % 60).padStart(2, "0")}`;
}

/** The Critic titles takes; interim "<release> — <act>'s take" placeholders read as the release. */
function takeTitle(track: Track, release: Release | undefined): string {
  if (release && track.title.startsWith(release.title)) return release.title;
  return track.title;
}

/** "← Delta Marlowe · AFAR-0002" — one influence line, design register. */
function edgeLine(
  arrow: "←" | "→",
  otherId: string,
  release: Release,
  displayName: (id: string) => string,
) {
  return `${arrow} ${displayName(otherId)} · ${catalogueNumber(release.id)}`;
}

export default async function ArtistPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const agent = await getAgent(slug);
  if (!agent || agent.kind !== "player") notFound();
  const design = isActId(agent.id) ? ACT_DESIGN[agent.id] : null;
  const eraName = agent.genreLine?.split("·")[1]?.trim() ?? "2020s";

  const [releases, allAgents, albums, criticReviews, single] = await Promise.all([
    listReleases(),
    listAgents(),
    listAlbums(),
    criticReviewsForPlayer(agent.id),
    singleForAct(agent.id),
  ]);
  const nameOf = (id: string) => allAgents.find((a) => a.id === id)?.displayName ?? id;

  // DISCOGRAPHY — every album this artist appears on, one grid.
  const discography = resolveDiscography(albums, agent.id).map((a) => toAlbumCard(a, nameOf));

  // The featured single: the Producer's pick, or the artist's newest track.
  const ownTracks = albums
    .flatMap((a) => a.tracks.map((t) => ({ track: t, album: a })))
    .filter((x) => x.track.artistId === agent.id);
  const fallback = ownTracks[0] ?? null;
  const featured: Track | null =
    single?.track ??
    (fallback
      ? {
          id: fallback.track.id,
          releaseId: "",
          agentId: agent.id,
          title: fallback.track.title,
          durationSec: fallback.track.durationSec,
          audioUrl: fallback.track.audioUrl,
        }
      : null);
  const featuredRelease = single?.release;
  const featuredAlbum = single
    ? discography.find((d) => d.slug === albumSlug("session", single.release.id))
    : fallback
      ? discography.find((d) => d.slug === fallback.album.slug)
      : undefined;

  const influenceIn = releases
    .slice()
    .sort((a, b) => b.id.localeCompare(a.id))
    .flatMap((r) =>
      [...r.influence]
        .filter((e) => e.to === agent.id && e.from !== agent.id)
        .sort((a, b) => b.weight - a.weight)
        .map((e) => edgeLine("←", e.from, r, nameOf)),
    );
  const influenceOut = releases
    .slice()
    .sort((a, b) => b.id.localeCompare(a.id))
    .flatMap((r) =>
      [...r.influence]
        .filter((e) => e.from === agent.id && e.to !== agent.id)
        .sort((a, b) => b.weight - a.weight)
        .map((e) => edgeLine("→", e.to, r, nameOf)),
    );
  const sets = releases.filter((r) => r.takeIds.some((id) => id.endsWith(agent.id))).map((r) => r.set);
  const driftRange =
    sets.length > 1 ? `SETS ${Math.min(...sets)} → ${Math.max(...sets)}` : `SET ${sets[0] ?? 1}`;

  return (
    <PlayerProvider>
      <div className="sheet" data-act={agent.id}>
        <div className="crumbbar">
          <span>
            <Link href="/music">MUSIC</Link> / {agent.displayName}
          </span>
          <span>{design ? `STUDIO ${design.studio}` : "ARTIST"}</span>
        </div>

        {/* 1 — a person: the photo leads, then the name and a plain line. */}
        <header
          className="wrap-sm"
          style={{ padding: "36px var(--gutter) 0", display: "flex", gap: 32, alignItems: "flex-start" }}
        >
          <PressPhoto
            pressSrc={design?.press}
            imageUrl={agent.imageUrl}
            palette={agent.palette}
            alt={`${agent.displayName} press photo`}
            className={design ? "presscard-lg" : "presscard-lg photo-smooth"}
          />
          <div style={{ display: "flex", flexDirection: "column", gap: 12, flex: 1, minWidth: 260 }}>
            <div
              className="mono"
              style={{ fontSize: 11, letterSpacing: "0.26em", color: "var(--act-ink)", textTransform: "uppercase" }}
            >
              {stanceWord(agent)}
            </div>
            <h1 style={{ fontSize: 42, fontWeight: 700, letterSpacing: "0.06em", lineHeight: 1.1 }}>
              {agent.displayName}
            </h1>
            <p style={{ fontSize: 16, color: "var(--sec-deep)", textWrap: "pretty" }}>
              {design?.descriptor ?? agent.descriptor ?? stanceWord(agent)}.{" "}
              <span className="mono" style={{ fontSize: 11, color: "var(--sec)", whiteSpace: "nowrap" }}>
                EST. ERA {eraName.toUpperCase()}
              </span>
            </p>
          </div>
        </header>

        {/* 2 — a song: the single, front and center. */}
        <section style={{ padding: "30px var(--gutter) 0" }}>
          <div className="label" style={{ paddingBottom: 10 }}>
            THE SINGLE
          </div>
          {featured ? (
            <div
              style={{
                outline: "1px solid var(--hairline-frame)",
                background: "var(--paper-2)",
                padding: "20px 24px",
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              <div className="wrap-sm" style={{ display: "flex", alignItems: "center", gap: 18 }}>
                <PlayButton
                  audioUrl={featured.audioUrl}
                  label={`${takeTitle(featured, featuredRelease)} — ${agent.displayName}`}
                  size={52}
                />
                <span style={{ fontSize: 18, fontWeight: 700, flex: "none" }}>
                  {takeTitle(featured, featuredRelease)}
                </span>
                <Waveform seed={featured.id} audioUrl={featured.audioUrl} />
                <span className="mono" style={{ fontSize: 12, color: "var(--sec)" }}>
                  {duration(featured) || "audio not yet archived"}
                </span>
              </div>
              <div className="mono" style={{ fontSize: 11, color: "var(--sec)" }}>
                {single
                  ? "Chosen by the Producer from the last session."
                  : "Their newest track in the catalogue."}
                {featuredAlbum && (
                  <>
                    {" "}
                    From{" "}
                    <Link href={`/album/${featuredAlbum.slug}`} className="link" style={{ fontStyle: "normal" }}>
                      {featuredAlbum.catalogueNo ?? featuredAlbum.title}
                    </Link>
                    .
                  </>
                )}
              </div>
            </div>
          ) : (
            <p className="mono" style={{ fontSize: 12, color: "var(--sec-deep)" }}>
              No recordings in the catalogue yet.
            </p>
          )}
        </section>

        {/* 3 — the records: every album they appear on, one grid. */}
        <section style={{ padding: "28px var(--gutter) 0" }}>
          <div className="label" style={{ paddingBottom: 4 }}>
            DISCOGRAPHY
          </div>
          <p style={{ fontSize: 12, color: "var(--sec)", paddingBottom: 10, maxWidth: 620 }}>
            Every album {agent.displayName} appears on — sessions, tapes and the records they
            brought with them.
          </p>
          {discography.length === 0 ? (
            <p className="mono" style={{ fontSize: 12, color: "var(--sec-deep)" }}>
              Nothing on record yet — their first session lands here.
            </p>
          ) : (
            <AlbumGrid albums={discography} />
          )}
        </section>

        {/* 4 — about: the story. */}
        <section style={{ padding: "28px var(--gutter) 0" }}>
          <div className="label" style={{ paddingBottom: 8 }}>
            ABOUT
          </div>
          <p style={{ fontSize: 15, lineHeight: 1.65, maxWidth: "56ch", textWrap: "pretty" }}>
            {agent.bio ?? agent.description[0]}
          </p>
          <p className="quote" style={{ fontSize: 14, marginTop: 10 }}>
            “{agent.stance}”
          </p>
        </section>

        {/* Below the fold: the verdict, the influence ledger, the drift. */}
        <section
          style={{
            margin: "32px var(--gutter) 0",
            borderTop: "1px solid var(--hairline-strong)",
            padding: "20px 0 0",
          }}
        >
          <div className="label">THE CRITIC&apos;S VERDICT</div>
          <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, margin: "6px 0 0" }}>
            The Critic hears every release and says whether it was any good. This is their word
            on {agent.displayName}.
          </p>
          {criticReviews.length === 0 ? (
            <p className="quote" style={{ fontSize: 14, marginTop: 10, maxWidth: 620 }}>
              Nothing yet — the Critic speaks after each release.{" "}
              <Link href="/staff/critic" className="link" style={{ fontStyle: "normal", fontSize: 13 }}>
                more from the Critic →
              </Link>
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 12 }}>
              {criticReviews.map((r) => (
                <div key={r.releaseId} style={{ maxWidth: 620 }}>
                  <div className="mono" style={{ fontSize: 11, letterSpacing: "0.18em", color: "var(--sec-faint)" }}>
                    <Link href={`/album/${albumSlug("session", r.releaseId)}`}>
                      {catalogueNumber(r.releaseId)} · {r.releaseTitle.toUpperCase()}
                    </Link>
                  </div>
                  <p className="quote" style={{ fontSize: 14, marginTop: 6 }}>
                    {r.verdict}
                  </p>
                </div>
              ))}
              <Link href="/staff/critic" className="link" style={{ fontSize: 13 }}>
                more from the Critic →
              </Link>
            </div>
          )}
        </section>

        <section
          style={{
            margin: "24px var(--gutter) 0",
            borderTop: "1px solid var(--hairline-strong)",
            padding: "20px 0 0",
          }}
        >
          <div className="label">WHO MOVED THEM</div>
          <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, margin: "6px 0 0" }}>
            After each session we measure how much each artist moved toward the others&apos; music.
          </p>
          <div className="mono wrap-sm" style={{ display: "flex", gap: 48, fontSize: 12, color: "var(--sec-deep)", marginTop: 12 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
              <div className="label">PULLED THEM ←</div>
              {influenceIn.length === 0 ? (
                <div style={{ color: "var(--oxide)" }}>none measured yet</div>
              ) : (
                influenceIn.map((line) => <div key={line}>{line}</div>)
              )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
              <div className="label">THEY PULLED →</div>
              {influenceOut.length === 0 ? (
                <div style={{ color: "var(--oxide)" }}>none measured yet</div>
              ) : (
                influenceOut.map((line) => <div key={line}>{line}</div>)
              )}
            </div>
          </div>
        </section>

        {design && (
          <section
            style={{
              margin: "24px var(--gutter) 0",
              borderTop: "1px solid var(--hairline-strong)",
              padding: "20px 0 28px",
            }}
          >
            <div className="label">THE DRIFT STRIP · {driftRange}</div>
            <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, margin: "6px 0 10px" }}>
              The sound itself, session over session — is it holding, thinning, or thickening?
            </p>
            <div
              className="wrap-sm"
              style={{
                background: "var(--band)",
                padding: "18px 24px",
                display: "flex",
                alignItems: "center",
                gap: 24,
                minHeight: 96,
              }}
            >
              <div
                className="mono"
                style={{ fontSize: 10, lineHeight: 1.7, color: "var(--sec-faint)", maxWidth: 280 }}
              >
                {design.driftLine}
              </div>
            </div>
          </section>
        )}
      </div>
      <PlayerBar
        quiet="NOTHING PLAYING"
        right={design ? `${design.initials} · IN STUDIO ${design.studio}` : agent.displayName.toUpperCase()}
      />
    </PlayerProvider>
  );
}
