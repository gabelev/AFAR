"use client";

import { useState } from "react";
import { WorldPane } from "@/components/world/WorldPane";
import { loadRail, saveRail, toggleRail, type RailState } from "@/lib/world/rail";

/** Must mirror rail.ts — inlined so first paint has the right state. */
const PRE_HYDRATION = `(function(){try{var d=document.currentScript.parentElement;var v=localStorage.getItem("afar.rail");if(v!=="open"&&v!=="closed")v=matchMedia("(max-width: 900px)").matches?"closed":"open";d.dataset.rail=v}catch(e){}})()`;

const isMobile = () =>
  typeof window !== "undefined" && window.matchMedia("(max-width: 900px)").matches;

/**
 * The split screen's client shell: world left, catalogue rail right, and
 * a hairline tab on the seam that opens/closes the rail. State persists
 * in localStorage; first visit defaults open on desktop, closed on mobile
 * (where the world runs full-bleed and the open rail overlays it). An
 * inline script applies the stored state before hydration so a returning
 * visitor never sees the wrong layout flash.
 */
export function SplitShell({ children }: { children: React.ReactNode }) {
  // Lazy init: on the client this reads the stored state at first render,
  // matching what the pre-hydration script already stamped on the SSR HTML
  // (the suppressed-warning glyph is the only spot that can differ).
  const [rail, setRail] = useState<RailState | null>(() =>
    typeof window === "undefined" ? null : loadRail(window.localStorage, isMobile()),
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
