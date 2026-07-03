import { describe, expect, it } from "vitest";

import { createStudioStore } from "../src/components/store";

describe("transport state", () => {
  it("starts from an idle state", () => {
    const store = createStudioStore();
    expect(store.getState().currentRunStatus).toBe("idle");
  });
});
