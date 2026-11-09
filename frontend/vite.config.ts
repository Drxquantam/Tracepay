import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // In Docker on Windows/macOS, file-change events don't cross the bind mount, so
    // Vite polls for changes instead (set by docker-compose).
    watch: process.env.VITE_POLL === "true" ? { usePolling: true, interval: 300 } : undefined,
  },
  build: {
    // Big libraries in their own files: they change rarely, so browsers keep them cached
    // across deploys of our own code.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          motion: ["framer-motion"],
        },
      },
    },
  },
});
