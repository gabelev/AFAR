"use client";

import { usePlayer } from "@/components/TrackPlayer";

/**
 * Deterministic dashed waveform (ported from Tunz's Waveform pattern, re-set
 * in the paper/ink system: square bars, hairline ink, act accent when live).
 * The bars are seeded by the take id, so a take always draws the same shape —
 * it is a fingerprint, not an analysis. Lights up while its take is playing.
 */
export function Waveform({ seed, audioUrl }: { seed: string; audioUrl: string | null }) {
  const { playingUrl } = usePlayer();
  const active = audioUrl !== null && playingUrl === audioUrl;
  const bars = Array.from({ length: 32 }, (_, i) => {
    const h = seed.charCodeAt(i % seed.length) + i * 7;
    return 5 + (h % 16);
  });
  return (
    <span
      aria-hidden
      style={{
        flex: 1,
        minWidth: 60,
        height: 24,
        display: "flex",
        alignItems: "center",
        gap: 3,
      }}
    >
      {bars.map((height, i) => (
        <span
          key={i}
          style={{
            flex: 1,
            height,
            background: active ? "var(--act-accent, var(--oxide))" : "var(--hairline-frame)",
          }}
        />
      ))}
    </span>
  );
}
