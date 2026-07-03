import { describe, expect, it, vi } from "vitest";

import { createStudioStore } from "../src/components/store";
import { SsePayloadError } from "../src/lib/sse";
import { executePipelineStream } from "../src/lib/stream-client";

function responseFromChunks(chunks) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

function authenticatedStore() {
  const store = createStudioStore();
  store.getState().setSession({
    sessionCredential: "ephemeral-session",
    username: "developer",
  });
  store.getState().beginAssistantMessage("assistant-1");
  return store;
}

describe("pipeline transport", () => {
  it("reassembles fragmented terminal output", async () => {
    const store = authenticatedStore();
    const fetchImpl = vi.fn(async () =>
      responseFromChunks([
        'event: run_started\ndata: {"event":"run_started","run_id":4}\n\n',
        'event: token\ndata: {"event":"tok',
        'en","run_id":4,"step_name":"Terminal","token":"Sovereign"}\n\n',
        'event: run_completed\ndata: {"event":"run_completed","run_id":4}\n\n',
      ]),
    );

    await executePipelineStream({
      threadId: 1,
      prompt: "test prompt",
      signal: new AbortController().signal,
      requestId: "request-1",
      fetchImpl,
      store,
    });

    expect(store.getState().messages[0].content).toBe("Sovereign");
    expect(store.getState().currentRunStatus).toBe("completed");
  });

  it("retries only before a response is established", async () => {
    const store = authenticatedStore();
    const fetchImpl = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("connection unavailable"))
      .mockResolvedValueOnce(
        responseFromChunks([
          'event: run_completed\ndata: {"event":"run_completed","run_id":8}\n\n',
        ]),
      );

    await executePipelineStream({
      threadId: 1,
      prompt: "retry prompt",
      signal: new AbortController().signal,
      requestId: "request-retry",
      fetchImpl,
      store,
    });

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("clears session state after an unauthorized response", async () => {
    const store = authenticatedStore();
    const fetchImpl = vi.fn(async () => new Response(null, { status: 401 }));

    await expect(
      executePipelineStream({
        threadId: 1,
        prompt: "expired prompt",
        signal: new AbortController().signal,
        requestId: "request-expired",
        fetchImpl,
        store,
      }),
    ).rejects.toMatchObject({ code: "session_expired" });

    expect(store.getState().isAuthenticated).toBe(false);
    expect(store.getState().sessionCredential).toBeNull();
  });

  it("stops when cancellation aborts connection establishment", async () => {
    const store = authenticatedStore();
    const controller = new AbortController();
    const fetchImpl = vi.fn(
      (_url, options) =>
        new Promise((_resolve, reject) => {
          options.signal.addEventListener(
            "abort",
            () => reject(new DOMException("Cancelled", "AbortError")),
            { once: true },
          );
        }),
    );

    const pending = executePipelineStream({
      threadId: 1,
      prompt: "cancel prompt",
      signal: controller.signal,
      requestId: "request-cancelled",
      fetchImpl,
      store,
    });
    controller.abort();

    await expect(pending).rejects.toMatchObject({ code: "cancelled" });
    expect(store.getState().currentRunStatus).toBe("cancelled");
  });

  it("surfaces malformed complete frames", async () => {
    const store = authenticatedStore();
    const fetchImpl = vi.fn(async () => responseFromChunks(["data: {broken}\n\n"]));

    await expect(
      executePipelineStream({
        threadId: 1,
        prompt: "malformed prompt",
        signal: new AbortController().signal,
        requestId: "request-malformed",
        fetchImpl,
        store,
      }),
    ).rejects.toBeInstanceOf(SsePayloadError);

    expect(store.getState().currentRunStatus).toBe("failed");
  });
});
