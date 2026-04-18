import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    // Playwright e2e specs live under e2e/ and use @playwright/test — don't
    // let vitest pick them up.
    exclude: ["node_modules/**", "dist/**", "e2e/**", ".superpowers/**"],
  },
});
