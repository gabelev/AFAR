"use client";

import Link from "next/link";
import { useState } from "react";
import { ArtImage } from "@/components/ArtImage";
import { GraphCoverMini } from "@/components/GraphCover";
import type { AlbumCardData } from "@/lib/album-cards";
import type { AlbumType } from "@/lib/data";

/**
 * The album grid every browse surface shares (/music, artist discographies):
 * one card per album — cover, title, artist line, a type badge — with
 * optional filter chips over the three album types. Client-side because the
 * filter is; the card data arrives serialized from the server page
 * (lib/album-cards.toAlbumCard).
 */

const TYPE_LABEL: Record<AlbumType, string> = {
  session: "SESSION",
  tape: "TAPE",
  album: "ALBUM",
};

const FILTERS: { key: AlbumType | "all"; label: string }[] = [
  { key: "all", label: "ALL" },
  { key: "session", label: "SESSIONS" },
  { key: "tape", label: "TAPES" },
  { key: "album", label: "ALBUMS" },
];

/** The cover slot: graph cover for sessions, art for imports, a reel plate for tapes. */
function CardCover({ album }: { album: AlbumCardData }) {
  if (album.influence) {
    return (
      <div className="album-card-cover" aria-hidden>
        <GraphCoverMini edges={album.influence} />
      </div>
    );
  }
  if (album.coverUrl) {
    return (
      <div className="album-card-cover">
        <ArtImage
          src={album.coverUrl}
          alt={`"${album.title}" cover`}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>
    );
  }
  // A tape's sleeve is paper and a catalogue number — the reel plate.
  return (
    <div className="album-card-cover album-card-reel mono" aria-hidden>
      <span style={{ fontSize: 20, letterSpacing: "0.3em" }}>◉ ◉</span>
      <span style={{ fontSize: 10, letterSpacing: "0.2em" }}>{album.catalogueNo}</span>
    </div>
  );
}

export function AlbumCard({ album }: { album: AlbumCardData }) {
  return (
    <Link href={`/album/${album.slug}`} className="roster-card">
      <CardCover album={album} />
      <div style={{ padding: "10px 12px 12px", display: "flex", flexDirection: "column", gap: 3 }}>
        <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.25 }}>{album.title}</div>
        <div style={{ fontSize: 12, color: "var(--sec-deep)" }}>{album.artistLine}</div>
        <div className="mono" style={{ fontSize: 10, letterSpacing: "0.12em", color: "var(--sec)" }}>
          {TYPE_LABEL[album.type]}
          {album.year && ` · ${album.year}`} · {album.trackCount} TRACKS
        </div>
      </div>
    </Link>
  );
}

export function AlbumGrid({
  albums,
  filterable = true,
}: {
  albums: AlbumCardData[];
  filterable?: boolean;
}) {
  const [filter, setFilter] = useState<AlbumType | "all">("all");
  const present = new Set(albums.map((a) => a.type));
  const shown = filter === "all" ? albums : albums.filter((a) => a.type === filter);
  const chips = FILTERS.filter((f) => f.key === "all" || present.has(f.key));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {filterable && present.size > 1 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }} role="group" aria-label="Filter albums by type">
          {chips.map((f) => (
            <button
              key={f.key}
              type="button"
              className="mono filter-chip"
              data-active={filter === f.key || undefined}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}
      {shown.length === 0 ? (
        <p className="mono" style={{ fontSize: 12, color: "var(--sec-deep)" }}>
          Nothing of that kind yet.
        </p>
      ) : (
        <div className="album-grid">
          {shown.map((album) => (
            <AlbumCard key={album.slug} album={album} />
          ))}
        </div>
      )}
    </div>
  );
}
