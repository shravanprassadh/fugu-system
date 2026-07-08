import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

const config = defineConfig({
  resolve: {
    alias: {
      "@/components/store": fileURLToPath(
        new URL("./src/components/store.js", import.meta.url),
      ),
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.js"],
    restoreMocks: true,
  },
});

export default config;
