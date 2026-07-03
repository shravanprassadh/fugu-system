import { describe, expect, it } from "vitest";

import { createStudioStore } from "../src/components/store";

describe("studio state isolation", () => {
  it("establishes and clears a complete in-memory session", () => {
    const store = createStudioStore();
    store.getState().setSession({
      sessionCredential: "ephemeral-session",
      username: "developer",
    });
    store.getState().setActiveThread(12);
    store.getState().appendMessage({ id: "m1", role: "user", content: "hello" });

    expect(store.getState().isAuthenticated).toBe(true);
    expect(store.getState().activeThreadId).toBe(12);

    store.getState().clearSession();
    expect(store.getState()).toMatchObject({
      sessionCredential: null,
      username: null,
      isAuthenticated: false,
      activeThreadId: null,
      messages: [],
      currentRunStatus: "idle",
    });
  });

  it("ignores stream fragments from stale request identifiers", () => {
    const store = createStudioStore();
    store.getState().beginAssistantMessage("assistant-1");
    store.getState().startStream("request-current");

    store.getState().appendAssistantToken("request-stale", "ignored");
    store.getState().appendAssistantToken("request-current", "accepted");

    expect(store.getState().messages[0].content).toBe("accepted");
  });
});
