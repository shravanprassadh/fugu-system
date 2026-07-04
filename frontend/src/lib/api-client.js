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
