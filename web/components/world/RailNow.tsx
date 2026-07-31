"use client";

import { useEffect, useState } from "react";
import { onNow } from "@/lib/world/now";

/**
 * The rail's NOW line: one line of current world activity, published by
 * the Phaser world over the now bus. Before the world loads (or with no
 * timeline) the server-rendered fallback holds the line.
 */
export function RailNow({ fallback }: { fallback: string }) {
  const [line, setLine] = useState<string | null>(null);
  useEffect(() => onNow(setLine), []);
  return <>{line ?? fallback}</>;
}
