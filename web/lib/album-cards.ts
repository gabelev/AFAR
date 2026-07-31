import type { AlbumType, AlbumView, InfluenceEdge } from "@/lib/data";

/**
 * The serialized shape an album card renders from. Built on the server
 * (toAlbumCard) and handed to the client AlbumGrid — plain data only, so
 * it crosses the server/client boundary.
 */
export interface AlbumCardData {
  slug: string;
  type: AlbumType;
  title: string;
  catalogueNo: string | null;
  artistLine: string;
  /** "2026" for dated records, the era ("2020s") for imports, "" if unknown. */
  year: string;
  coverUrl: string | null;
  influence: InfluenceEdge[] | null;
  trackCount: number;
}

/** Trim an AlbumView to what a card needs. */
export function toAlbumCard(
  album: AlbumView,
  displayName: (id: string) => string,
): AlbumCardData {
  const names = album.artistIds.map(displayName);
  const artistLine =
    names.length > 3 ? `${names.slice(0, 2).join(", ")} & more` : names.join(", ");
  return {
    slug: album.slug,
    type: album.type,
    title: album.title,
    catalogueNo: album.catalogueNo,
    artistLine,
    year: album.date?.slice(0, 4) ?? album.era ?? "",
    coverUrl: album.coverUrl,
    influence: album.influence,
    trackCount: album.tracks.length,
  };
}
