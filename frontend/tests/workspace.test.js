import { describe, expect, it } from "vitest";

import { createStudioStore } from "../src/components/store";
import { normalizeThemeMode, resolveTheme } from "../src/lib/theme";
import {
  createThreadFromPrompt,
  deleteThreadEverywhere,
  deriveThreadTitle,
  refreshThreads,
} from "../src/lib/workspace";

function jsonResponse(payload, status = 200) {
  return { ok: status < 400, status, json: async () => payload };
}

function authenticatedStore() {
  const store = createStudioStore();
  store.getState().setSession({ sessionCredential: "test-token", username: "developer" });
  return store;
}

describe("thread title derivation", () => {
  it("uses the first line and collapses whitespace", () => {
    expect(deriveThreadTitle("  Compare   options\nsecond line ignored")).toBe("Compare options");
  });

  it("truncates long prompts on a word boundary with an ellipsis", () => {
    const title = deriveThreadTitle(
      "Summarize the quarterly revenue projections for every region and flag anomalies",
    );
    expect(title.length).toBeLessThanOrEqual(49);
    expect(title.endsWith("…")).toBe(true);
  });

  it("falls back to a default for empty prompts", () => {
    expect(deriveThreadTitle("   \n  ")).toBe("New chat");
  });
});

describe("workspace thread coordination", () => {
  it("creates a thread from a prompt and activates it", async () => {
    const store = authenticatedStore();
    const requests = [];
    const fetchImpl = async (url, init) => {
      requests.push({ url, init });
      return jsonResponse({ id: 7, name: "Compare options", created_at: "2026-01-01T00:00:00Z" }, 201);
    };

    const thread = await createThreadFromPrompt("Compare options", { store, fetchImpl });

    expect(thread.id).toBe(7);
    expect(requests[0].init.method).toBe("POST");
    expect(requests[0].init.headers.Authorization).toBe("Bearer test-token");
    expect(store.getState().activeThreadId).toBe(7);
    expect(store.getState().threads[0].name).toBe("Compare options");
  });

  it("loads the thread list into the store", async () => {
    const store = authenticatedStore();
    const fetchImpl = async () =>
      jsonResponse([
        { id: 2, name: "Newest", created_at: "2026-01-02T00:00:00Z" },
        { id: 1, name: "Older", created_at: "2026-01-01T00:00:00Z" },
      ]);

    await refreshThreads({ store, fetchImpl });

    expect(store.getState().threads.map((thread) => thread.name)).toEqual(["Newest", "Older"]);
  });

  it("clears active conversation state when the active thread is deleted", async () => {
    const store = authenticatedStore();
    store.getState().setThreads([{ id: 3, name: "Doomed", created_at: "2026-01-01T00:00:00Z" }]);
    store.getState().setActiveThread(3);
    store.getState().appendMessage({ id: "m1", role: "user", content: "hello" });
    const fetchImpl = async () => ({ ok: true, status: 204, json: async () => null });

    await deleteThreadEverywhere(3, { store, fetchImpl });

    expect(store.getState().threads).toEqual([]);
    expect(store.getState().activeThreadId).toBeNull();
    expect(store.getState().messages).toEqual([]);
  });

  it("clears the session when the backend rejects the token", async () => {
    const store = authenticatedStore();
    const fetchImpl = async () => jsonResponse({ detail: "expired" }, 401);

    await expect(refreshThreads({ store, fetchImpl })).rejects.toMatchObject({ status: 401 });
    expect(store.getState().isAuthenticated).toBe(false);
  });
});

describe("theme resolution", () => {
  it("defaults unknown stored values to light", () => {
    expect(normalizeThemeMode("neon")).toBe("light");
    expect(normalizeThemeMode(null)).toBe("light");
    expect(normalizeThemeMode("dark")).toBe("dark");
  });

  it("resolves the system mode from the OS preference", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });
});
