import Link from "next/link";
import { notFound } from "next/navigation";
import { ArtImage } from "@/components/ArtImage";
import { PlayerBar } from "@/components/PlayerBar";
import { PressPhoto } from "@/components/PressPhoto";
import { PlayerProvider, PlayButton } from "@/components/TrackPlayer";
import { Waveform } from "@/components/Waveform";
import { ACT_DESIGN, catalogueNumber, isActId } from "@/lib/acts";
import {
  criticReviewsForPlayer,
  getAgent,
  listAgents,
  listReleases,
  singleForAct,
  stanceWord,
  tapeNumber,
  tapeStatusLine,
  tapesForAgent,
  tracksForAgent,
  type Release,
  type Track,
} from "@/lib/data";

export const dynamic = "force-dynamic";

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

/** "← Delta Marlowe · set 2 · AFAR-0002" — one influence line, design register. */
function edgeLine(
  arrow: "←" | "→",
  otherId: string,
  release: Release,
  displayName: (id: string) => string,
) {
  return `${arrow} ${displayName(otherId)} · set ${release.set} · ${catalogueNumber(release.id)}`;
}

/** "RES-03" -> "RES 03"; the street address chip for imported residents. */
function buildingLabel(building: string): string {
  return building.replace(/-/g, " ").toUpperCase();
}

export default async function ActPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const agent = await getAgent(slug);
  if (!agent || agent.kind !== "player") notFound();
  // House acts carry full design metadata; imported acts derive their line
  // from their own data (descriptor, genreLine, resident block).
  const design = isActId(agent.id) ? ACT_DESIGN[agent.id] : null;
  const eraName = agent.genreLine?.split("·")[1]?.trim() ?? "2020s";
  const locationChip = design
    ? `STUDIO ${design.studio}`
    : agent.resident?.building
      ? buildingLabel(agent.resident.building)
      : "IN TOWN";

  const [takes, releases, allAgents, criticReviews, single, tapes] = await Promise.all([
    tracksForAgent(agent.id),
    listReleases(),
    listAgents(),
    criticReviewsForPlayer(agent.id),
    singleForAct(agent.id),
    tapesForAgent(agent.id),
  ]);
  const releaseById = new Map(releases.map((r) => [r.id, r]));
  const nameOf = (id: string) => allAgents.find((a) => a.id === id)?.displayName ?? id;

  // The single leads; everything else is the catalogue, newest first. When the
  // Producer has never picked (fixture mode), the newest take is featured
  // instead — without the Producer's caption.
  const takesDesc = [...takes].sort((a, b) => b.releaseId.localeCompare(a.releaseId));
  const featured = single?.track ?? takesDesc[0] ?? null;
  const featuredRelease = single?.release ?? (featured ? releaseById.get(featured.releaseId) : undefined);
  const catalogue = takesDesc.filter((t) => t.id !== featured?.id);

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
            <Link href="/world">ROSTER</Link> / {agent.displayName}
          </span>
          <span>{locationChip}</span>
        </div>

        {/* 1 — a person: the photo leads, then the name and a plain line. */}
        <header
          className="wrap-sm"
          style={{ padding: "36px var(--gutter) 0", display: "flex", gap: 32, alignItems: "flex-start" }}
        >
          <PressPhoto
            pressSrc={design?.press}
            imageUrl={agent.imageUrl}
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

            {/* 2 — a story: the press bio. */}
            <p style={{ fontSize: 15, lineHeight: 1.65, maxWidth: "56ch", textWrap: "pretty" }}>
              {agent.bio ?? agent.description[0]}
            </p>
            <p className="quote" style={{ fontSize: 14 }}>
              “{agent.stance}”
            </p>
          </div>
        </header>

        {/* 3 — a song: the Producer's pick, front and center. */}
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
                {!design && agent.coverUrl && (
                  <ArtImage
                    src={agent.coverUrl}
                    alt={agent.album ? `"${agent.album.title}" cover` : `${agent.displayName} record cover`}
                    style={{ width: 72, height: 72, objectFit: "cover", flex: "none", outline: "1px solid var(--hairline-frame)" }}
                  />
                )}
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
                  : agent.album
                    ? `From "${agent.album.title}" — the record they brought to town.`
                    : "The newest take in the archive — the Producer has not picked a single yet."}
                {featuredRelease && (
                  <>
                    {" "}
                    From{" "}
                    <Link href={`/release/${featuredRelease.id}`} className="link" style={{ fontStyle: "normal" }}>
                      {catalogueNumber(featuredRelease.id)} · {featuredRelease.title}
                    </Link>
                    .
                  </>
                )}
              </div>
            </div>
          ) : (
            <p className="mono" style={{ fontSize: 12, color: "var(--sec-deep)" }}>
              No recordings in the archive yet.
            </p>
          )}
        </section>

        {/* The Archivist on the record an imported act brought to town —
            "what this record is", from the back of the sleeve. */}
        {agent.album?.linerNotes && (
          <section style={{ padding: "24px var(--gutter) 0" }}>
            <div className="label" style={{ paddingBottom: 4 }}>
              LINER NOTES · &ldquo;{agent.album.title.toUpperCase()}&rdquo;
            </div>
            <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 8 }}>
              The Archivist on the record they brought to town.
            </p>
            {agent.album.linerNotes.split(/\n\s*\n/).map((para, i) => (
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
              style={{ fontSize: 10, letterSpacing: "0.18em", color: "var(--sec)", marginTop: 12 }}
            >
              — THE ARCHIVIST
            </div>
          </section>
        )}

        {/* 4 — the rest of the archive. */}
        {catalogue.length > 0 && (
          <section style={{ padding: "28px var(--gutter) 0", display: "flex", flexDirection: "column" }}>
            <div className="label" style={{ paddingBottom: 6 }}>
              CATALOGUE
            </div>
            <p style={{ fontSize: 12, color: "var(--sec)", paddingBottom: 8 }}>
              Every other take of theirs on record, newest first.
            </p>
            {catalogue.map((take, i) => {
              const release = releaseById.get(take.releaseId);
              return (
                <div
                  key={take.id}
                  className={`wrap-sm rule-row${i === catalogue.length - 1 ? " rule-row-last" : ""}`}
                  style={{ display: "flex", gap: 14, alignItems: "center", padding: "9px 0" }}
                >
                  <PlayButton
                    audioUrl={take.audioUrl}
                    label={`${takeTitle(take, release)} — ${agent.displayName}`}
                  />
                  <span style={{ fontSize: 14, fontWeight: 600, width: 200, flex: "none" }}>
                    {takeTitle(take, release)}
                  </span>
                  <Waveform seed={take.id} audioUrl={take.audioUrl} />
                  <span className="mono" style={{ fontSize: 11, color: "var(--sec)", width: 34, flex: "none" }}>
                    {duration(take)}
                  </span>
                  {release ? (
                    <Link
                      href={`/release/${take.releaseId}`}
                      className="mono"
                      style={{ fontSize: 11, color: "var(--sec)", flex: "none" }}
                    >
                      {catalogueNumber(take.releaseId)}
                    </Link>
                  ) : (
                    <span className="mono" style={{ fontSize: 11, color: "var(--sec)", flex: "none" }}>
                      {agent.album ? agent.album.title.toUpperCase() : take.releaseId.toUpperCase()}
                    </span>
                  )}
                </div>
              );
            })}
          </section>
        )}

        {/* SESSION TAPES — every full session this act played on, from the
            vault (the vault doctrine: the releases are the cuts; the tapes
            are everything, vetoed and abandoned sessions included). */}
        {tapes.length > 0 && (
          <section style={{ padding: "28px var(--gutter) 0", display: "flex", flexDirection: "column" }}>
            <div className="label" style={{ paddingBottom: 6 }}>
              SESSION TAPES
            </div>
            <p style={{ fontSize: 12, color: "var(--sec)", maxWidth: 620, paddingBottom: 8 }}>
              The full sessions behind the releases — every take they played, kept whole in
              the vault, including the sessions nothing was released from.
            </p>
            {tapes.map((tape, i) => (
              <Link
                key={tape.id}
                href={`/tape/${tape.id}`}
                className={`wrap-sm rule-row${i === tapes.length - 1 ? " rule-row-last" : ""}`}
                style={{ display: "flex", gap: 14, alignItems: "baseline", padding: "9px 0" }}
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
            ))}
          </section>
        )}

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
                    <Link href={`/release/${r.releaseId}`}>
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
            After each session we measure how much each act moved toward the others&apos; music.
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
        right={design ? `${design.initials} · IN STUDIO ${design.studio}` : `${agent.displayName.toUpperCase()} · ${locationChip}`}
      />
    </PlayerProvider>
  );
}
