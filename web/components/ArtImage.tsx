"use client";

import { useState, type CSSProperties, type ReactNode } from "react";

/**
 * An <img> that renders `fallback` if the source fails to load. Fixtures
 * carry /api/media URLs so fixture mode stays in step with Neon, but with no
 * DATABASE_URL those URLs 404 — the Radar plate (or nothing, for covers)
 * takes over instead of a broken-image glyph.
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
  if (failed) return <>{fallback}</>;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} className={className} style={style} onError={() => setFailed(true)} />
  );
}
