import type { NextConfig } from "next";

// The stable public entity ids (CLAUDE.md: never rename). The /agent/[id]
// URLs they used to live at redirect permanently to the catalogue's
// /act and /staff routes — old links keep working forever.
const ACT_IDS = ["silt", "rust", "keep"];
const STAFF_IDS = ["muse", "producer", "critic", "listener"];

const nextConfig: NextConfig = {
  async redirects() {
    return [
      ...ACT_IDS.map((id) => ({
        source: `/agent/${id}`,
        destination: `/act/${id}`,
        permanent: true,
      })),
      ...STAFF_IDS.map((id) => ({
        source: `/agent/${id}`,
        destination: `/staff/${id}`,
        permanent: true,
      })),
    ];
  },
};

export default nextConfig;
