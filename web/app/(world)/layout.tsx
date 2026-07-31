import { WorldPane } from "@/components/world/WorldPane";

/**
 * The split screen (design frame 1a): left, the label building as a live
 * pixel world; right, the catalogue. Every route in this group — /world,
 * /act/*, /release/*, /staff/* — renders in the right pane while the world
 * persists across navigation; route changes only move its camera. The
 * player bar (each page renders its own) is fixed across the full width
 * underneath both panes.
 */
export default function WorldLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-split">
      <aside className="world-pane">
        <WorldPane />
      </aside>
      <div className="right-pane">{children}</div>
    </div>
  );
}
