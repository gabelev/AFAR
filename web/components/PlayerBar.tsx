"use client";

import { usePlayer } from "@/components/TrackPlayer";

/**
 * The 72px #14130f player bar from the design handoff. Quiet by default
 * (mono 12, #a9a290); when the page's PlayerProvider has a take playing,
 * the left side goes live — lamp-coloured ▶ and paper text, per frame 1b.
 * Pages without audio simply never leave the quiet state.
 */
export function PlayerBar({ quiet, right }: { quiet: string; right: string }) {
  const { playingUrl, playingLabel } = usePlayer();

  return (
    <div className="playerbar-outer">
      <div className="playerbar">
        {playingUrl && playingLabel ? (
          <span className="live">
            <span className="glyph">▶</span>&nbsp; {playingLabel.toUpperCase()}
          </span>
        ) : (
          <span>■&nbsp; {quiet}</span>
        )}
        <span>{right}</span>
      </div>
    </div>
  );
}
