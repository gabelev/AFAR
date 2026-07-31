"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";

/**
 * One shared audio element per page — the archive's single <audio> owner
 * (web convention: exactly one owner; the world renderer never originates
 * sound). Take rows toggle through the provider, so starting one take
 * silently stops whichever other was playing.
 */

interface PlayerState {
  playingUrl: string | null;
  toggle: (url: string) => void;
}

const PlayerContext = createContext<PlayerState>({ playingUrl: null, toggle: () => {} });

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playingUrl, setPlayingUrl] = useState<string | null>(null);

  useEffect(() => {
    const audio = new Audio();
    audio.preload = "none";
    const clear = () => setPlayingUrl(null);
    audio.addEventListener("ended", clear);
    audio.addEventListener("error", clear);
    audioRef.current = audio;
    return () => {
      audio.pause();
      audioRef.current = null;
    };
  }, []);

  const toggle = (url: string) => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playingUrl === url) {
      audio.pause();
      setPlayingUrl(null);
      return;
    }
    audio.src = url;
    void audio.play().catch(() => setPlayingUrl(null));
    setPlayingUrl(url);
  };

  return (
    <PlayerContext.Provider value={{ playingUrl, toggle }}>{children}</PlayerContext.Provider>
  );
}

export function usePlayer() {
  return useContext(PlayerContext);
}

/**
 * One take row with play/pause, driven by the page's PlayerProvider. When
 * audioUrl is null (the take exists in the log but its audio hasn't been
 * mirrored yet) the row renders disabled.
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
  const { playingUrl, toggle } = usePlayer();
  const playing = audioUrl !== null && playingUrl === audioUrl;

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
        onClick={() => audioUrl && toggle(audioUrl)}
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
    </div>
  );
}
