/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
    proxy: {
      "/v1": {
        target: process.env.VITE_DEV_API_PROXY || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  // Skip PostCSS during test runs. The iCloud-synced Desktop folder
  // intermittently ECANCELs the postcss.config.js read, which hangs Vitest.
  // Production builds (mode !== "test") still load it normally.
  css: mode === "test" ? { postcss: { plugins: [] } } : undefined,
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "@tanstack/react-query", "@tanstack/query-core"],
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
  },
}));
