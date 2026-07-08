import { studioStore } from "../components/store";
import {
  createThread,
  deleteThread,
  fetchThreadMessages,
  listThreads,
  renameThread,
} from "./api-client";

const MAX_GENERATED_TITLE_LENGTH = 48;

export function deriveThreadTitle(prompt) {
  const firstLine = String(prompt).trim().split("\n")[0].replace(/\s+/g, " ").trim();
  if (!firstLine) {
    return "New chat";
  }
  if (firstLine.length <= MAX_GENERATED_TITLE_LENGTH) {
    return firstLine;
  }
  const truncated = firstLine.slice(0, MAX_GENERATED_TITLE_LENGTH);
  const lastSpace = truncated.lastIndexOf(" ");
  return `${lastSpace > 24 ? truncated.slice(0, lastSpace) : truncated}…`;
}

export async function refreshThreads({ store = studioStore, fetchImpl } = {}) {
  const threads = await listThreads({ store, fetchImpl });
  store.getState().setThreads(threads);
  return threads;
}

export async function openThread(threadId, { store = studioStore, fetchImpl } = {}) {
  store.getState().setActiveThread(threadId);
  const history = await fetchThreadMessages(threadId, { store, fetchImpl });
  store.getState().hydrateMessages(threadId, history);
  return history;
}

export async function createThreadFromPrompt(prompt, { store = studioStore, fetchImpl } = {}) {
  const thread = await createThread(deriveThreadTitle(prompt), { store, fetchImpl });
  store.getState().upsertThread(thread);
  store.getState().setActiveThread(thread.id);
  return thread;
}

export async function renameThreadEverywhere(threadId, name, { store = studioStore, fetchImpl } = {}) {
  const thread = await renameThread(threadId, name, { store, fetchImpl });
  store.getState().upsertThread(thread);
  return thread;
}

export async function deleteThreadEverywhere(threadId, { store = studioStore, fetchImpl } = {}) {
  await deleteThread(threadId, { store, fetchImpl });
  store.getState().removeThread(threadId);
}
