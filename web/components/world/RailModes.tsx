"use client";

import { useEffect, useState } from "react";
import { onRailState, sendCommand, type RailWorldState } from "@/lib/world/control";

/**
 * The rail's watching controls, in the follow/roam chip's mono register:
 * a NOW / REPLAY toggle, a play control for the shelf record (NOW), and
 * a compact release picker that jumps the loop to a block (REPLAY).
 * Renders nothing until a world is running and has a catalogue — the
 * state comes over the control bus, so the picker always lists exactly
 * what the world is playing, spliced arrivals included.
 */
export function RailModes() {
  const [state, setState] = useState<RailWorldState | null>(null);
  useEffect(() => onRailState(setState), []);
  if (!state) return null;

  const { mode, entries, latest, playingBlock } = state;
  const shelf = entries[latest];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          type="button"
          className="mode-chip"
          aria-pressed={mode === "now"}
          onClick={() => sendCommand({ kind: "mode", mode: "now" })}
        >
          {mode === "now" ? "●" : "○"} NOW
        </button>
        <button
          type="button"
          className="mode-chip"
          aria-pressed={mode === "replay"}
          onClick={() => sendCommand({ kind: "mode", mode: "replay" })}
        >
          {mode === "replay" ? "●" : "○"} REPLAY
        </button>
      </div>
      {mode === "now" && shelf && (
        <button
          type="button"
          className="mode-chip"
          style={{ alignSelf: "flex-start" }}
          onClick={() => sendCommand({ kind: "play-latest" })}
        >
          ▶ PLAY THE LAST RECORD — {shelf.catalogueNo}
        </button>
      )}
      {mode === "replay" && (
        <div className="rail-picker">
          {entries.map((e) => (
            <button
              key={e.block}
              type="button"
              aria-pressed={playingBlock === e.block}
              onClick={() => sendCommand({ kind: "jump", block: e.block })}
            >
              <span aria-hidden style={{ width: 10, flex: "none" }}>
                {playingBlock === e.block ? "▶" : ""}
              </span>
              <span style={{ flex: "none" }}>{e.catalogueNo}</span>
              <span style={{ opacity: 0.75 }}>{e.title}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
