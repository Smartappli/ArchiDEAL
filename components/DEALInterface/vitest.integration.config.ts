import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    clearMocks: true,
    environment: "jsdom",
    globals: false,
    include: ["src/**/*.integration.test.ts", "src/**/*.integration.test.tsx"],
    mockReset: true,
    restoreMocks: true,
    setupFiles: "./src/test/setup.ts",
  },
});
