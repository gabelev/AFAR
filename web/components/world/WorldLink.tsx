"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { CSSProperties, ReactNode } from "react";
import { fly } from "@/lib/world/bus";
import { resolveWorld } from "@/lib/world/resolve";

/**
 * A right-pane link that flies the world camera to its subject BEFORE
 * navigating (~400ms overlap with the 700ms glide), then lets the route
 * change land while the camera is still moving. Falls back to a plain
 * navigation when there is no world (mobile, world still loading) or for
 * modified clicks (new tab etc.).
 */
export function WorldLink({
  id,
  href,
  children,
  className,
  style,
  ...rest
}: {
  id: string;
  href: string;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
} & Record<`data-${string}`, string>) {
  const router = useRouter();

  return (
    <Link
      href={href}
      className={className}
      style={style}
      {...rest}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        const entry = resolveWorld(id);
        if (!entry) return;
        e.preventDefault();
        const flew = fly(entry.target);
        window.setTimeout(() => router.push(href), flew ? 400 : 0);
      }}
    >
      {children}
    </Link>
  );
}
