import type { NextConfig } from "next";

// The stable public entity ids (CLAUDE.md: never rename). URLs are public
// and permanent: every generation of routes redirects forward — the
// original /agent/[id] pages, the /act catalogue, and the pre-streaming-IA
// /release + /tape pages all land on today's /artist and /album routes.
const ACT_IDS = ["silt", "rust", "keep"];
const STAFF_IDS = ["muse", "producer", "critic", "listener", "archivist"];

const nextConfig: NextConfig = {
  async redirects() {
    return [
      ...ACT_IDS.map((id) => ({
        source: `/agent/${id}`,
        destination: `/artist/${id}`,
        permanent: true,
      })),
      ...STAFF_IDS.map((id) => ({
        source: `/agent/${id}`,
        destination: `/staff/${id}`,
        permanent: true,
      })),
      // The streaming IA: artists and albums (DECISIONS 2026-07-31).
      { source: "/act/:slug", destination: "/artist/:slug", permanent: true },
      { source: "/release/:id", destination: "/album/afar-:id", permanent: true },
      { source: "/tape/:id", destination: "/album/tape-:id", permanent: true },
    ];
  },
};

export default nextConfig;
