import { SplitShell } from "@/components/world/SplitShell";

/**
 * The split screen (design frame 1a): left, the world as a live pixel
 * street; right, the catalogue rail. Every route in this group — /world,
 * /music, /artist/*, /album/*, /staff/* — renders in the right pane while
 * the world persists across navigation; route changes only move its camera. The
 * rail collapses behind a tab on the seam (SplitShell); the player bar
 * (each page renders its own) is fixed across the full width underneath.
 */
export default function WorldLayout({ children }: { children: React.ReactNode }) {
  return <SplitShell>{children}</SplitShell>;
}
