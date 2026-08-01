"use client";

import Link from "next/link";
import { useState } from "react";
import { WorldPane } from "@/components/world/WorldPane";
import { loadRail, saveRail, toggleRail, type RailState } from "@/lib/world/rail";

/** Must mirror rail.ts — inlined so first paint has the right state. */
const PRE_HYDRATION = `(function(){try{var d=document.currentScript.parentElement;var v=localStorage.getItem("afar.rail.v2");if(v!=="open"&&v!=="closed")v="open";d.dataset.rail=v}catch(e){}})()`;

/**
 * The split screen's client shell: world left, catalogue rail right, and
 * a hairline tab on the seam that opens/closes the rail. State persists
 * in localStorage; first visit defaults open on every viewport (on mobile
 * the open rail overlays the full-bleed world as a paper panel). An
 * inline script applies the stored state before hydration so a returning
 * visitor never sees the wrong layout flash. The world pane also carries
 * the way home: a fixed "← AFAR.MUSIC" chip over the canvas, so the split
 * screen always has an exit even with the rail closed.
 */
export function SplitShell({ children }: { children: React.ReactNode }) {
  // Lazy init: on the client this reads the stored state at first render,
  // matching what the pre-hydration script already stamped on the SSR HTML
  // (the suppressed-warning glyph is the only spot that can differ).
  const [rail, setRail] = useState<RailState | null>(() =>
    typeof window === "undefined" ? null : loadRail(window.localStorage),
  );
  const state = rail ?? "open";

  const onToggle = () => {
    const next = toggleRail(state);
    setRail(next);
    saveRail(window.localStorage, next);
  };

  return (
    <div className="app-split" data-rail={state} suppressHydrationWarning>
      <script dangerouslySetInnerHTML={{ __html: PRE_HYDRATION }} />
      <aside className="world-pane">
        <WorldPane />
        <Link href="/" className="world-home">
          ← AFAR.MUSIC
        </Link>
        <button
          type="button"
          className="rail-toggle mono"
          onClick={onToggle}
          aria-expanded={state === "open"}
          aria-controls="catalogue-rail"
          aria-label={state === "open" ? "Close the catalogue rail" : "Open the catalogue rail"}
          suppressHydrationWarning
        >
          {state === "open" ? "⟩" : "⟨"}
        </button>
      </aside>
      <div className="right-pane" id="catalogue-rail">
        {children}
      </div>
    </div>
  );
}
