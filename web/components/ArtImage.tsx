"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

/**
 * An <img> that renders `fallback` if the source fails to load. Fixtures
 * carry /api/media URLs so fixture mode stays in step with Neon, but with no
 * DATABASE_URL those URLs 404 — the fallback (the checked-in press photo,
 * or nothing) takes over instead of a broken-image glyph.
 *
 * The effect covers the hydration race: if the 404 lands before React
 * attaches onError, the browser has already marked the image complete with
 * no pixels — check for that on mount.
 */
export function ArtImage({
  src,
  alt,
  fallback = null,
  className,
  style,
}: {
  src: string;
  alt: string;
  fallback?: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  const [failed, setFailed] = useState(false);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const img = imgRef.current;
    if (img && img.complete && img.naturalWidth === 0) setFailed(true);
  }, [src]);

  if (failed) return <>{fallback}</>;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      ref={imgRef}
      src={src}
      alt={alt}
      className={className}
      style={style}
      onError={() => setFailed(true)}
    />
  );
}
