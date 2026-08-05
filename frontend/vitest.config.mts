import { defineConfig } from "vitest/config";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [tsconfigPaths()],
  cacheDir: "./.local/cache/vite",
  test: {
    environment: "jsdom",
    globals: true,
    // Mermaid and the browser DOM are process-global in jsdom. Serializing
    // files keeps renderer/theme state isolated and prevents flaky cross-file
    // races while preserving the same assertions and production code paths.
    fileParallelism: false,
    setupFiles: ["./vitest.setup.ts"],
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    coverage: {
      reportsDirectory: "./.local/coverage",
    },
  },
});
