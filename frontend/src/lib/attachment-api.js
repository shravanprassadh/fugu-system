import { studioStore } from "../components/store";
import { apiUrl, ApiRequestError } from "./api-client";

function requireCredential(store = studioStore) {
  const state = store.getState();
  if (!state.sessionCredential || !state.enforceSessionFreshness()) {
    state.clearSession();
    throw new ApiRequestError("An authenticated session is required.", 401);
  }
  return state.sessionCredential;
}

async function parseError(response) {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
      return payload.detail.map((item) => item?.msg || item?.detail || JSON.stringify(item)).join("; ");
    }
  } catch {
    // Use a stable status-based fallback.
  }
  return `Attachment request failed with status ${response.status}.`;
}

async function attachmentRequest(path, { method = "GET", fetchImpl = fetch, store = studioStore } = {}) {
  const credential = requireCredential(store);
  const response = await fetchImpl(apiUrl(path), {
    method,
    headers: { Authorization: `Bearer ${credential}` },
    cache: "no-store",
  });
  if (response.status === 401) {
    store.getState().clearSession();
  }
  if (!response.ok) {
    throw new ApiRequestError(await parseError(response), response.status);
  }
  store.getState().touchSession();
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export function getAttachmentCapabilities(options) {
  return attachmentRequest("/api/attachments/capabilities", options);
}

export function listThreadAttachments(threadId, options) {
  return attachmentRequest(`/api/threads/${threadId}/attachments`, options);
}

export function deleteAttachment(attachmentId, options = {}) {
  return attachmentRequest(`/api/attachments/${encodeURIComponent(attachmentId)}`, {
    ...options,
    method: "DELETE",
  });
}

export function reprocessAttachment(attachmentId, options = {}) {
  return attachmentRequest(`/api/attachments/${encodeURIComponent(attachmentId)}/process`, {
    ...options,
    method: "POST",
  });
}

export async function downloadAttachment(
  attachmentId,
  { fetchImpl = fetch, store = studioStore } = {},
) {
  const credential = requireCredential(store);
  const response = await fetchImpl(apiUrl(`/api/attachments/${encodeURIComponent(attachmentId)}/content`), {
    headers: { Authorization: `Bearer ${credential}` },
    cache: "no-store",
  });
  if (response.status === 401) {
    store.getState().clearSession();
  }
  if (!response.ok) {
    throw new ApiRequestError(await parseError(response), response.status);
  }
  store.getState().touchSession();
  return response.blob();
}

export function uploadAttachment(
  threadId,
  file,
  {
    onProgress = () => {},
    store = studioStore,
    xhrFactory = () => new XMLHttpRequest(),
  } = {},
) {
  const credential = requireCredential(store);
  return new Promise((resolve, reject) => {
    const request = xhrFactory();
    request.open("POST", apiUrl(`/api/threads/${threadId}/attachments`));
    request.setRequestHeader("Authorization", `Bearer ${credential}`);
    request.responseType = "json";
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });
    request.addEventListener("load", () => {
      if (request.status === 401) {
        store.getState().clearSession();
      }
      if (request.status < 200 || request.status >= 300) {
        const detail = request.response?.detail;
        reject(
          new ApiRequestError(
            typeof detail === "string" ? detail : `Attachment upload failed with status ${request.status}.`,
            request.status,
          ),
        );
        return;
      }
      store.getState().touchSession();
      resolve(request.response);
    });
    request.addEventListener("error", () => {
      reject(new ApiRequestError("The attachment upload connection failed."));
    });
    request.addEventListener("abort", () => {
      reject(new ApiRequestError("The attachment upload was cancelled."));
    });
    const form = new FormData();
    form.append("file", file, file.name);
    request.send(form);
  });
}
