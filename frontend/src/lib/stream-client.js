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

async function openStream({ threadId, prompt, modelPreference, signal, fetchImpl, credential }) {
  const body = { prompt };
  if (modelPreference?.providerType && modelPreference?.modelIdentifier) {
    body.provider_type = modelPreference.providerType;
    body.model_identifier = modelPreference.modelIdentifier;
  }
  return fetchImpl(apiUrl(`/api/threads/${threadId}/execute`), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${credential}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
    signal,
  });
}

function pipelineErrorMessage(payload) {
  const error = payload.error || "The pipeline reported an execution failure.";
  return payload.error_type ? `${payload.error_type}: ${error}` : error;
}

function validationDetailMessage(detail) {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item?.msg) {
          const location = Array.isArray(item.loc) ? item.loc.join(".") : item.loc;
          return location ? `${location}: ${item.msg}` : item.msg;
        }
        if (item?.detail) {
          return item.detail;
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    return detail.message || detail.error || JSON.stringify(detail);
  }
  return null;
}

async function httpErrorMessage(response) {
  try {
    const payload = await response.json();
    const detail = validationDetailMessage(payload.detail);
    if (detail) {
      return detail;
    }
  } catch {
    // Fall through to generic status text.
  }
  return `The server returned status ${response.status}.`;
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
    const message = pipelineErrorMessage(payload);
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
  modelPreference,
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
        modelPreference,
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
    const message = await httpErrorMessage(response);
    store.getState().updateExecution(requestId, {
      status: "failed",
      error: message,
    });
    throw new StreamClientError(message, "http_failure");
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
