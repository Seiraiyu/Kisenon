import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The app talks to /api/<name>/graphql; Vite proxies each name to a PostGraphile
// server, so there is no CORS setup. `?api=fork` switches to the preview server.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/main": { target: "http://localhost:5678", rewrite: (p) => p.replace("/api/main", "") },
      "/api/fork": { target: "http://localhost:5679", rewrite: (p) => p.replace("/api/fork", "") },
    },
  },
  test: { environment: "jsdom" },
});
