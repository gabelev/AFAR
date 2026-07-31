"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";

/**
 * One shared audio element per page — the archive's single <audio> owner
 * (web convention: exactly one owner; the world renderer never originates
 * sound). Take rows toggle through the provider, so starting one take
 * silently stops whichever other was playing. The provider also carries a
 * display label for whatever is playing, which the page's player bar shows.
 *
 * Play-all: a page can hand the provider an ordered queue (an album's
 * tracklist); when a queued track ends the next one starts. Toggling any
 * single track clears the queue — a direct pick always wins.
 */

export interface QueueItem {
  url: string;
  label: string;
}

interface PlayerState {
  playingUrl: string | null;
  playingLabel: string | null;
  toggle: (url: string, label: string) => void;
  playAll: (items: QueueItem[]) => void;
}

const PlayerContext = createContext<PlayerState>({
  playingUrl: null,
  playingLabel: null,
  toggle: () => {},
  playAll: () => {},
});

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const queueRef = useRef<QueueItem[]>([]);
  const [playing, setPlaying] = useState<QueueItem | null>(null);

  useEffect(() => {
    const audio = new Audio();
    audio.preload = "none";
    const advance = () => {
      const next = queueRef.current.shift();
      if (next && audioRef.current) {
        audioRef.current.src = next.url;
        void audioRef.current.play().catch(() => setPlaying(null));
        setPlaying(next);
      } else {
        setPlaying(null);
      }
    };
    const clear = () => {
      queueRef.current = [];
      setPlaying(null);
    };
    audio.addEventListener("ended", advance);
    audio.addEventListener("error", clear);
    audioRef.current = audio;
    return () => {
      audio.pause();
      audioRef.current = null;
    };
  }, []);

  const play = (item: QueueItem) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.src = item.url;
    void audio.play().catch(() => setPlaying(null));
    setPlaying(item);
  };

  const toggle = (url: string, label: string) => {
    const audio = audioRef.current;
    if (!audio) return;
    queueRef.current = []; // a direct pick always wins over a queue
    if (playing?.url === url) {
      audio.pause();
      setPlaying(null);
      return;
    }
    play({ url, label });
  };

  const playAll = (items: QueueItem[]) => {
    const playable = items.filter((i) => i.url);
    if (playable.length === 0) return;
    queueRef.current = playable.slice(1);
    play(playable[0]);
  };

  return (
    <PlayerContext.Provider
      value={{
        playingUrl: playing?.url ?? null,
        playingLabel: playing?.label ?? null,
        toggle,
        playAll,
      }}
    >
      {children}
    </PlayerContext.Provider>
  );
}

export function usePlayer() {
  return useContext(PlayerContext);
}

/**
 * A take's play/pause control, driven by the page's PlayerProvider. When
 * audioUrl is null (the take exists in the log but its audio hasn't been
 * mirrored yet) the button renders disabled.
 */
export function PlayButton({
  audioUrl,
  label,
  size,
}: {
  audioUrl: string | null;
  label: string;
  /** Side length in px; the featured single uses a big one. Default 28. */
  size?: number;
}) {
  const { playingUrl, toggle } = usePlayer();
  const playing = audioUrl !== null && playingUrl === audioUrl;

  return (
    <button
      type="button"
      className="playbtn"
      style={size ? { width: size, height: size, fontSize: Math.round(size * 0.36) } : undefined}
      onClick={() => audioUrl && toggle(audioUrl, label)}
      disabled={!audioUrl}
      aria-label={playing ? `Pause ${label}` : `Play ${label}`}
      title={audioUrl ? undefined : "audio not yet archived"}
    >
      {playing ? "❚❚" : "▶"}
    </button>
  );
}

/** "▶ PLAY ALL" — queues an album's whole tracklist through the provider. */
export function PlayAllButton({ items }: { items: QueueItem[] }) {
  const { playAll } = usePlayer();
  const playable = items.filter((i) => i.url);
  return (
    <button
      type="button"
      className="btn-outline mono"
      style={{ fontSize: 11, letterSpacing: "0.14em", padding: "8px 14px" }}
      onClick={() => playAll(items)}
      disabled={playable.length === 0}
      title={playable.length === 0 ? "audio not yet archived" : undefined}
    >
      ▶ PLAY ALL
    </button>
  );
}
