import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    exclude: ["**/* 2.*", "**/* 3.*", "node_modules/**"],
    setupFiles: ["src/test/setup.ts"],
  },
});
