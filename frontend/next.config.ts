import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  output: process.env.BUILD_TARGET === "desktop" ? "export" : "standalone",
  images: {
    unoptimized: true,
  },
  // Playwright's local browser uses the loopback origin for Next assets.
  allowedDevOrigins: ["127.0.0.1"],
  // Explicitly opt in to the Next 16 default bundler while retaining the
  // webpack fallback used by the desktop build and CI compatibility checks.
  turbopack: {
    root: path.resolve(__dirname),
  },
  // Vega renders charts in the browser. Its optional Node canvas adapter is not
  // needed in the server bundle and is intentionally unavailable in production.
  webpack: (config) => {
    config.resolve ??= {};
    config.resolve.alias = {
      ...(config.resolve.alias ?? {}),
      canvas: false,
    };
    return config;
  },
};

export default nextConfig;
