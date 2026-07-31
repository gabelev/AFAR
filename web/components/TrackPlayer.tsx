"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";

/**
 * One shared audio element per page — the archive's single <audio> owner
 * (web convention: exactly one owner; the world renderer never originates
 * sound). Take rows toggle through the provider, so starting one take
 * silently stops whichever other was playing. The provider also carries a
 * display label for whatever is playing, which the page's player bar shows.
 */

interface PlayerState {
  playingUrl: string | null;
  playingLabel: string | null;
  toggle: (url: string, label: string) => void;
}

const PlayerContext = createContext<PlayerState>({
  playingUrl: null,
  playingLabel: null,
  toggle: () => {},
});

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<{ url: string; label: string } | null>(null);

  useEffect(() => {
    const audio = new Audio();
    audio.preload = "none";
    const clear = () => setPlaying(null);
    audio.addEventListener("ended", clear);
    audio.addEventListener("error", clear);
    audioRef.current = audio;
    return () => {
      audio.pause();
      audioRef.current = null;
    };
  }, []);

  const toggle = (url: string, label: string) => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing?.url === url) {
      audio.pause();
      setPlaying(null);
      return;
    }
    audio.src = url;
    void audio.play().catch(() => setPlaying(null));
    setPlaying({ url, label });
  };

  return (
    <PlayerContext.Provider
      value={{ playingUrl: playing?.url ?? null, playingLabel: playing?.label ?? null, toggle }}
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
export function PlayButton({ audioUrl, label }: { audioUrl: string | null; label: string }) {
  const { playingUrl, toggle } = usePlayer();
  const playing = audioUrl !== null && playingUrl === audioUrl;

  return (
    <button
      type="button"
      className="playbtn"
      onClick={() => audioUrl && toggle(audioUrl, label)}
      disabled={!audioUrl}
      aria-label={playing ? `Pause ${label}` : `Play ${label}`}
      title={audioUrl ? undefined : "audio not yet archived"}
    >
      {playing ? "❚❚" : "▶"}
    </button>
  );
}
