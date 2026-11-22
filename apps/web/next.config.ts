import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Playwright uses a separate directory so `next dev` cannot replace the chunks `next start` already loaded.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  output: process.env.NEXT_STANDALONE === "1" ? "standalone" : undefined,
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
