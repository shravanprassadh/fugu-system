import { studioStore } from "@/components/store";

import { ApiRequestError, apiUrl } from "./api-client";

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

async function providerRequest(path, { method = "GET", body, fetchImpl = fetch } = {}) {
  const store = studioStore.getState();
  const sessionCredential = store.sessionCredential;
  if (!sessionCredential || !store.enforceSessionFreshness()) {
    throw new ApiRequestError("An authenticated session is required.", 401);
  }

  const headers = { Authorization: `Bearer ${sessionCredential}` };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetchImpl(apiUrl(path), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (response.status === 401) {
    studioStore.getState().clearSession();
  }
  if (!response.ok) {
    throw new ApiRequestError(await parseError(response), response.status);
  }
  studioStore.getState().touchSession();
  return response.status === 204 ? null : response.json();
}

export function testCandidateProviderCredential(providerName, secret, options = {}) {
  return providerRequest(
    `/api/admin/provider-credentials/${encodeURIComponent(providerName)}/candidate/test`,
    { ...options, method: "POST", body: { secret } },
  );
}

export function testActiveProviderCredential(providerName, options = {}) {
  return providerRequest(
    `/api/admin/provider-credentials/${encodeURIComponent(providerName)}/test`,
    { ...options, method: "POST" },
  );
}

export function replaceProviderCredential(providerName, secret, options = {}) {
  return providerRequest(
    `/api/admin/provider-credentials/${encodeURIComponent(providerName)}`,
    { ...options, method: "PUT", body: { secret } },
  );
}
