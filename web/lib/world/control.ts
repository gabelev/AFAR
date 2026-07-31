"use client";

/**
 * The rail ↔ world control bridge, same shape as the fly and now buses:
 * module-level pub/sub, no context, survives route changes.
 *
 * Commands flow rail → world (mode toggle, shelf play, picker jump);
 * state flows world → rail (current mode + the picker's entries), so the
 * rail's controls render only once a world is actually running and always
 * describe the catalogue that world is playing — including blocks the
 * live poll spliced in after load.
 */

import type { PickerEntry, WorldMode } from "@/lib/world/mode";

export type WorldCommand =
  | { kind: "mode"; mode: WorldMode }
  | { kind: "play-latest" }
  | { kind: "jump"; block: number };

type CommandListener = (cmd: WorldCommand) => void;
const commandListeners = new Set<CommandListener>();

export function onCommand(listener: CommandListener): () => void {
  commandListeners.add(listener);
  return () => {
    commandListeners.delete(listener);
  };
}

/** Send a control command to the world. Returns true if a world heard it. */
export function sendCommand(cmd: WorldCommand): boolean {
  for (const l of commandListeners) l(cmd);
  return commandListeners.size > 0;
}

/** What the rail needs to draw its controls. */
export interface RailWorldState {
  mode: WorldMode;
  entries: PickerEntry[];
  /** Index (into entries) of the newest block — the shelf record. */
  latest: number;
  /** REPLAY: the block currently playing (picker highlight); NOW: null. */
  playingBlock: number | null;
}

type StateListener = (state: RailWorldState | null) => void;
let currentState: RailWorldState | null = null;
const stateListeners = new Set<StateListener>();

export function publishRailState(state: RailWorldState | null): void {
  currentState = state;
  for (const l of stateListeners) l(state);
}

/** Subscribe; the current value replays immediately. Returns unsubscribe. */
export function onRailState(listener: StateListener): () => void {
  stateListeners.add(listener);
  listener(currentState);
  return () => {
    stateListeners.delete(listener);
  };
}
