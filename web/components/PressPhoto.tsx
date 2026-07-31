import { ArtImage } from "@/components/ArtImage";
import { ACT_DESIGN, type ActId } from "@/lib/acts";

/**
 * An act's press photo (the handoff's 960×1200 pixel portraits). Prefers the
 * agent's imageUrl (the Neon media copy, content-addressed); in fixture mode
 * that URL 404s and the checked-in copy under public/press/ takes over, so
 * zero-env pages show the same photo.
 */
export function PressPhoto({
  actId,
  imageUrl,
  alt,
  className,
}: {
  actId: ActId;
  imageUrl: string | null;
  alt: string;
  className?: string;
}) {
  const pressSrc = ACT_DESIGN[actId].press;
  const fallback = (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={pressSrc} alt={alt} className={className} />
  );
  if (!imageUrl || imageUrl === pressSrc) return fallback;
  return <ArtImage src={imageUrl} alt={alt} className={className} fallback={fallback} />;
}
