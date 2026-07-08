import { studioStore } from "@/components/store";

const API_BASE_URL = (process.env.NEXT_PUBLIC_FUGU_API_BASE_URL ?? "").replace(/\/+$/, "");

export class ApiRequestError extends Error {
  constructor(message, status = null) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

function buildUrl(path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
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

export async function login(username, password, fetchImpl = fetch) {
  const response = await fetchImpl(buildUrl("/api/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiRequestError(await parseError(response), response.status);
  }
  const payload = await response.json();
  if (!payload.access_token) {
    throw new ApiRequestError("The authentication response did not contain a session credential.");
  }
  return payload.access_token;
}

export async function loadProfile(sessionCredential, fetchImpl = fetch) {
  const response = await fetchImpl(buildUrl("/api/auth/me"), {
    headers: { Authorization: `Bearer ${sessionCredential}` },
    cache: "no-store",
  });
  if (response.status === 401) {
    studioStore.getState().clearSession();
  }
  if (!response.ok) {
    throw new ApiRequestError(await parseError(response), response.status);
  }
  return response.json();
}

export async function logout(fetchImpl = fetch) {
  const sessionCredential = studioStore.getState().sessionCredential;
  try {
    if (sessionCredential) {
      await fetchImpl(buildUrl("/api/auth/logout"), {
        method: "POST",
        headers: { Authorization: `Bearer ${sessionCredential}` },
        cache: "no-store",
      });
    }
  } finally {
    studioStore.getState().clearSession();
  }
}

export function apiUrl(path) {
  return buildUrl(path);
}

const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]"]);

/*
 * Detects the API base misconfigurations that previously surfaced only as a
 * confusing 404 on /api/auth/login. Returns a human-readable problem
 * description, or null when the configuration is usable.
 */
export function getApiConfigurationProblem() {
  if (API_BASE_URL.endsWith("/api")) {
    return (
      "NEXT_PUBLIC_FUGU_API_BASE_URL must not end with /api — the app already calls /api/… paths. " +
      "Remove the /api suffix and redeploy the frontend."
    );
  }
  if (API_BASE_URL) {
    return null;
  }
  if (typeof window === "undefined" || LOCAL_HOSTNAMES.has(window.location.hostname)) {
    // Same-origin calls are a legitimate local-development setup.
    return null;
  }
  return (
    "NEXT_PUBLIC_FUGU_API_BASE_URL is not set, so sign-in requests would go to this frontend domain " +
    "and fail with 404. Set it to the backend origin (for example https://your-backend.onrender.com, " +
    "without a trailing /api) in the deployment environment, then redeploy."
  );
}

function requireSessionCredential(store) {
  const sessionCredential = store.getState().sessionCredential;
  if (!sessionCredential) {
    throw new ApiRequestError("An authenticated session is required.", 401);
  }
  return sessionCredential;
}

async function authorizedRequest(path, { method = "GET", body, fetchImpl = fetch, store = studioStore } = {}) {
  const sessionCredential = requireSessionCredential(store);
  const headers = { Authorization: `Bearer ${sessionCredential}` };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetchImpl(buildUrl(path), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (response.status === 401) {
    store.getState().clearSession();
    throw new ApiRequestError("The session has expired or was rejected.", 401);
  }
  if (!response.ok) {
    throw new ApiRequestError(await parseError(response), response.status);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export function listThreads(options) {
  return authorizedRequest("/api/threads", options);
}

export function createThread(name, options = {}) {
  return authorizedRequest("/api/threads", { ...options, method: "POST", body: { name } });
}

export function fetchThreadMessages(threadId, options) {
  return authorizedRequest(`/api/threads/${threadId}/messages`, options);
}

export function renameThread(threadId, name, options = {}) {
  return authorizedRequest(`/api/threads/${threadId}`, { ...options, method: "PATCH", body: { name } });
}

export function deleteThread(threadId, options = {}) {
  return authorizedRequest(`/api/threads/${threadId}`, { ...options, method: "DELETE" });
}

export function listAdminUsers(options) {
  return authorizedRequest("/api/admin/users", options);
}

export function createAdminUser({ username, password, role = "user", isActive = true }, options = {}) {
  return authorizedRequest("/api/admin/users", {
    ...options,
    method: "POST",
    body: { username, password, role, is_active: isActive },
  });
}

export function updateAdminUser(userId, { role, isActive }, options = {}) {
  const body = {};
  if (role !== undefined) {
    body.role = role;
  }
  if (isActive !== undefined) {
    body.is_active = isActive;
  }
  return authorizedRequest(`/api/admin/users/${userId}`, { ...options, method: "PATCH", body });
}

export function resetAdminUserPassword(userId, password, options = {}) {
  return authorizedRequest(`/api/admin/users/${userId}/password`, { ...options, method: "POST", body: { password } });
}

export function deleteAdminUser(userId, options = {}) {
  return authorizedRequest(`/api/admin/users/${userId}`, { ...options, method: "DELETE" });
}
