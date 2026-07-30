"use client";

import { useEffect, useRef, useState } from "react";

/**
 * One take row with play/pause. Plain <audio> under the hood; only one
 * take plays at a time per page. When audioUrl is null (the take exists in
 * the log but its audio hasn't been mirrored yet) the row renders disabled.
 */
export function TrackPlayer({
  title,
  audioUrl,
  subtitle,
  tag,
}: {
  title: string;
  audioUrl: string | null;
  subtitle?: string;
  tag?: string;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onPlay = () => {
      // Pause every other player on the page.
      document.querySelectorAll("audio").forEach((other) => {
        if (other !== el) other.pause();
      });
      setPlaying(true);
    };
    const onStop = () => setPlaying(false);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onStop);
    el.addEventListener("ended", onStop);
    return () => {
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onStop);
      el.removeEventListener("ended", onStop);
    };
  }, [audioUrl]);

  const toggle = () => {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) void el.play();
    else el.pause();
  };

  return (
    <div
      className="flex items-center gap-3"
      style={{
        padding: "var(--space-2) var(--space-3)",
        border: "1px solid var(--color-divider)",
        borderRadius: "var(--radius-md)",
        opacity: audioUrl ? 1 : 0.75,
      }}
    >
      <button
        type="button"
        className="btn btn-primary btn-icon"
        onClick={toggle}
        disabled={!audioUrl}
        aria-label={playing ? `Pause ${title}` : `Play ${title}`}
      >
        {playing ? "❚❚" : "▶"}
      </button>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="card-title">{title}</span>
          {tag && <span className="tag tag-outline">{tag}</span>}
          {!audioUrl && <span className="tag tag-neutral">audio not yet archived</span>}
        </div>
        {subtitle && <div className="card-meta">{subtitle}</div>}
      </div>
      {audioUrl && <audio ref={audioRef} src={audioUrl} preload="none" />}
    </div>
  );
}
