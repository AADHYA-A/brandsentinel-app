import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  // Vercel deploys the frontend service separately; Docker still bundles it
  // into the FastAPI app's static directory.
  build: { outDir: process.env.VERCEL ? "dist" : "../backend/static", emptyOutDir: true },
});
