import { studioStore } from "../components/store";
import { apiUrl } from "./api-client";
import { createSseParser } from "./sse";

export class StreamClientError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "StreamClientError";
    this.code = code;
  }
}

function isAbortError(error) {
  return error?.name === "AbortError";
}

async function openStream({ threadId, prompt, signal, fetchImpl, credential }) {
  return fetchImpl(apiUrl(`/api/threads/${threadId}/execute`), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${credential}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ prompt }),
    cache: "no-store",
    signal,
  });
}

function applyEvent(store, requestId, event) {
  const payload = event.data;
  if (event.event === "done") {
    store.getState().finishStream(requestId, "completed");
    return true;
  }
  if (!payload || typeof payload !== "object") {
    throw new StreamClientError("The stream emitted an invalid event payload.", "invalid_event");
  }

  const eventType = payload.event ?? event.event;
  if (eventType === "run_started") {
    store.getState().updateExecution(requestId, {
      runId: payload.run_id,
      status: "running",
      stepName: null,
    });
  } else if (eventType === "step_started") {
    store.getState().updateExecution(requestId, {
      runId: payload.run_id,
      status: "running",
      stepName: payload.step_name ?? null,
    });
  } else if (eventType === "token") {
    store.getState().appendAssistantToken(requestId, payload.token ?? "");
  } else if (eventType === "step_completed") {
    store.getState().updateExecution(requestId, {
      runId: payload.run_id,
      stepName: null,
    });
  } else if (eventType === "run_completed") {
    store.getState().finishStream(requestId, "completed");
    return true;
  } else if (eventType === "error") {
    const message = payload.error || "The pipeline reported an execution failure.";
    store.getState().updateExecution(requestId, {
      runId: payload.run_id,
      status: "failed",
      stepName: payload.step_name ?? null,
      error: message,
    });
    throw new StreamClientError(message, "pipeline_failure");
  }
  return false;
}

export async function executePipelineStream({
  threadId,
  prompt,
  signal,
  requestId,
  fetchImpl = fetch,
  store = studioStore,
  maxConnectionAttempts = 2,
}) {
  const credential = store.getState().sessionCredential;
  if (!credential) {
    throw new StreamClientError("An authenticated session is required.", "authentication_required");
  }

  store.getState().startStream(requestId);
  let response;
  for (let attempt = 1; attempt <= maxConnectionAttempts; attempt += 1) {
    try {
      response = await openStream({
        threadId,
        prompt,
        signal,
        fetchImpl,
        credential,
      });
      break;
    } catch (error) {
      if (isAbortError(error) || signal.aborted) {
        store.getState().finishStream(requestId, "cancelled");
        throw new StreamClientError("The stream request was cancelled.", "cancelled");
      }
      if (attempt === maxConnectionAttempts) {
        store.getState().updateExecution(requestId, {
          status: "failed",
          error: "Unable to establish the execution stream.",
        });
        throw new StreamClientError(
          "Unable to establish the execution stream.",
          "connection_failure",
        );
      }
    }
  }

  if (response.status === 401) {
    store.getState().clearSession();
    throw new StreamClientError("The session has expired or was rejected.", "session_expired");
  }
  if (!response.ok) {
    store.getState().updateExecution(requestId, {
      status: "failed",
      error: `The server returned status ${response.status}.`,
    });
    throw new StreamClientError(
      `The server returned status ${response.status}.`,
      "http_failure",
    );
  }
  if (!response.body) {
    throw new StreamClientError("The server returned no streaming response body.", "missing_body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let completed = false;
  const parser = createSseParser((event) => {
    completed = applyEvent(store, requestId, event) || completed;
  });

  try {
    while (!completed) {
      const { done, value } = await reader.read();
      if (done) {
        parser.finish();
        break;
      }
      parser.feed(decoder.decode(value, { stream: true }));
    }
  } catch (error) {
    if (isAbortError(error) || signal.aborted) {
      store.getState().finishStream(requestId, "cancelled");
      throw new StreamClientError("The stream request was cancelled.", "cancelled");
    }
    if (error instanceof StreamClientError) {
      throw error;
    }
    store.getState().updateExecution(requestId, {
      status: "failed",
      error: error.message || "The stream terminated unexpectedly.",
    });
    throw error;
  } finally {
    reader.releaseLock();
  }

  if (!completed) {
    store.getState().updateExecution(requestId, {
      status: "failed",
      error: "The stream ended before a completion event was received.",
    });
    throw new StreamClientError(
      "The stream ended before a completion event was received.",
      "unexpected_end",
    );
  }
}
