import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    clearMocks: true,
    coverage: {
      exclude: ["src/**/*.test.{ts,tsx}", "src/**/*.d.ts", "src/main.tsx", "src/test/**"],
      include: ["src/**/*.{ts,tsx}"],
      provider: "v8",
      reporter: ["text", "html"],
      thresholds: {
        branches: 91,
        functions: 91,
        lines: 91,
        statements: 91,
      },
    },
    environment: "jsdom",
    globals: false,
    include: ["src/**/*.unit.test.ts", "src/**/*.unit.test.tsx", "src/**/*.integration.test.ts", "src/**/*.integration.test.tsx"],
    mockReset: true,
    restoreMocks: true,
    setupFiles: "./src/test/setup.ts",
  },
});
