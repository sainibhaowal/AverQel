import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  output: process.env.BUILD_TARGET === "desktop" ? "export" : "standalone",
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
