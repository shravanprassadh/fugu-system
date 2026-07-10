import { studioStore } from "../components/store";
import { apiUrl, ApiRequestError } from "./api-client";

function requireCredential() {
  const state = studioStore.getState();
  if (!state.sessionCredential || !state.enforceSessionFreshness()) {
    state.clearSession();
    throw new ApiRequestError("An authenticated session is required.", 401);
  }
  return state.sessionCredential;
}

async function parseError(response) {
  try {
    const payload = await response.json();
    return typeof payload.detail === "string"
      ? payload.detail
      : `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

async function executionRequest(path, { method = "GET", fetchImpl = fetch } = {}) {
  const credential = requireCredential();
  const response = await fetchImpl(apiUrl(path), {
    method,
    headers: { Authorization: `Bearer ${credential}` },
    cache: "no-store",
  });
  if (response.status === 401) {
    studioStore.getState().clearSession();
  }
  if (!response.ok) {
    throw new ApiRequestError(await parseError(response), response.status);
  }
  studioStore.getState().touchSession();
  return response.json();
}

function appendFilter(params, key, value) {
  if (value !== undefined && value !== null && String(value).trim() !== "") {
    params.set(key, String(value).trim());
  }
}

export function listExecutionRuns(filters = {}, options = {}) {
  const params = new URLSearchParams();
  appendFilter(params, "status", filters.status);
  appendFilter(params, "user_id", filters.userId);
  appendFilter(params, "provider", filters.provider);
  appendFilter(params, "model", filters.model);
  appendFilter(params, "thread_id", filters.threadId);
  appendFilter(params, "date_from", filters.dateFrom);
  appendFilter(params, "date_to", filters.dateTo);
  appendFilter(params, "limit", filters.limit || 100);
  return executionRequest(`/api/admin/execution-runs?${params.toString()}`, options);
}

export function getExecutionRun(runId, options = {}) {
  return executionRequest(`/api/admin/execution-runs/${runId}`, options);
}

export function exportExecutionDiagnostics(runId, options = {}) {
  return executionRequest(`/api/admin/execution-runs/${runId}/diagnostics`, options);
}

export function cancelExecutionRun(runId, options = {}) {
  return executionRequest(`/api/admin/execution-runs/${runId}/cancel`, {
    ...options,
    method: "POST",
  });
}

export function retryExecutionRun(runId, options = {}) {
  return executionRequest(`/api/admin/execution-runs/${runId}/retry`, {
    ...options,
    method: "POST",
  });
}

export function retryExecutionStage(runId, stageName, options = {}) {
  return executionRequest(
    `/api/admin/execution-runs/${runId}/stages/${encodeURIComponent(stageName)}/retry`,
    { ...options, method: "POST" },
  );
}
