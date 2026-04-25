import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import path from "node:path";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // `selfDestroying: true` ships a service worker whose only job is to
      // unregister ALL previously installed CRUZ service workers. This
      // unblocks users who are stuck on stale JS cached by an older SW.
      // Flip to `false` + keep registerType once the UI stabilises.
      selfDestroying: true,
      registerType: "autoUpdate",
      workbox: {
        // If the SW is kept, new versions take over immediately — no more
        // "30 min debugging stale cache" episodes.
        skipWaiting: true,
        clientsClaim: true,
      },
      manifest: {
        name: "CRUZ",
        short_name: "CRUZ",
        description: "FRIDAY-style AI command center",
        theme_color: "#0a0a0a",
        background_color: "#0a0a0a",
        display: "standalone",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/icon-512-maskable.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
    }),
  ],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:3000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
