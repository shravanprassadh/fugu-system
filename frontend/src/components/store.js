"use client";

import { useStore } from "zustand";
import { createStore } from "zustand/vanilla";

export const SESSION_IDLE_TIMEOUT_MS = 48 * 60 * 60 * 1_000;
export const SESSION_STORAGE_KEY = "fugu:session:v1";

const transientState = {
  threads: [],
  activeThreadId: null,
  messages: [],
  currentRunId: null,
  currentRunStatus: "idle",
  activeProcessingStep: null,
  streamError: null,
  activeRequestId: null,
};

const unauthenticatedState = {
  sessionCredential: null,
  username: null,
  userRole: null,
  userId: null,
  isAuthenticated: false,
  sessionLastActiveAt: null,
  ...transientState,
};

function nowTimestamp() {
  return Date.now();
}

function hasBrowserStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function isSessionFresh(lastActiveAt, now = nowTimestamp()) {
  return Number.isFinite(lastActiveAt) && now - lastActiveAt <= SESSION_IDLE_TIMEOUT_MS;
}

function readStoredSession() {
  if (!hasBrowserStorage()) {
    return null;
  }
  try {
    const rawSession = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!rawSession) {
      return null;
    }
    const parsedSession = JSON.parse(rawSession);
    if (!parsedSession?.sessionCredential || !parsedSession?.username) {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
      return null;
    }
    const sessionLastActiveAt = Number(parsedSession.sessionLastActiveAt);
    if (!isSessionFresh(sessionLastActiveAt)) {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
      return null;
    }
    return {
      sessionCredential: parsedSession.sessionCredential,
      username: parsedSession.username,
      userRole: parsedSession.userRole ?? null,
      userId: parsedSession.userId ?? null,
      isAuthenticated: true,
      sessionLastActiveAt,
    };
  } catch {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
}

function persistSession({ sessionCredential, username, userRole, userId, sessionLastActiveAt }) {
  if (!hasBrowserStorage() || !sessionCredential || !username || !sessionLastActiveAt) {
    return;
  }
  window.localStorage.setItem(
    SESSION_STORAGE_KEY,
    JSON.stringify({
      sessionCredential,
      username,
      userRole: userRole ?? null,
      userId: userId ?? null,
      sessionLastActiveAt,
    }),
  );
}

function clearStoredSession() {
  if (!hasBrowserStorage()) {
    return;
  }
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
}

function initialState() {
  const storedSession = readStoredSession();
  if (!storedSession) {
    return { ...unauthenticatedState };
  }
  return {
    ...unauthenticatedState,
    ...storedSession,
    ...transientState,
  };
}

export function createStudioStore() {
  return createStore((set, get) => ({
    ...initialState(),
    setSession: ({ sessionCredential, username, userRole = null, userId = null }) => {
      if (!sessionCredential || !username) {
        throw new Error("Session data is incomplete.");
      }
      const sessionLastActiveAt = nowTimestamp();
      const sessionState = {
        sessionCredential,
        username,
        userRole,
        userId,
        isAuthenticated: true,
        sessionLastActiveAt,
        streamError: null,
      };
      persistSession(sessionState);
      set(sessionState);
    },
    touchSession: () => {
      const current = get();
      if (!current.isAuthenticated || !current.sessionCredential || !current.username) {
        return false;
      }
      const sessionLastActiveAt = nowTimestamp();
      const sessionState = {
        sessionCredential: current.sessionCredential,
        username: current.username,
        userRole: current.userRole,
        userId: current.userId,
        sessionLastActiveAt,
      };
      persistSession(sessionState);
      set({ sessionLastActiveAt });
      return true;
    },
    enforceSessionFreshness: () => {
      const current = get();
      if (!current.isAuthenticated) {
        return true;
      }
      if (isSessionFresh(Number(current.sessionLastActiveAt))) {
        return true;
      }
      clearStoredSession();
      set({ ...unauthenticatedState });
      return false;
    },
    clearSession: () => {
      clearStoredSession();
      set({ ...unauthenticatedState });
    },
    setThreads: (threads) => set({ threads: [...threads] }),
    upsertThread: (thread) =>
      set((state) => {
        const existingIndex = state.threads.findIndex((candidate) => candidate.id === thread.id);
        if (existingIndex === -1) {
          return { threads: [{ ...thread }, ...state.threads] };
        }
        const threads = [...state.threads];
        threads[existingIndex] = { ...threads[existingIndex], ...thread };
        return { threads };
      }),
    removeThread: (threadId) =>
      set((state) => {
        const threads = state.threads.filter((candidate) => candidate.id !== threadId);
        if (state.activeThreadId !== threadId) {
          return { threads };
        }
        return {
          threads,
          activeThreadId: null,
          messages: [],
          currentRunId: null,
          currentRunStatus: "idle",
          activeProcessingStep: null,
          streamError: null,
          activeRequestId: null,
        };
      }),
    hydrateMessages: (threadId, messages) =>
      set((state) => {
        if (state.activeThreadId !== threadId) {
          return state;
        }
        return {
          messages: messages.map((message) => ({
            id: String(message.id),
            role: message.role,
            content: message.content,
          })),
        };
      }),
    setActiveThread: (threadId) =>
      set({
        activeThreadId: threadId,
        messages: [],
        currentRunId: null,
        currentRunStatus: "idle",
        activeProcessingStep: null,
        streamError: null,
        activeRequestId: null,
      }),
    appendMessage: (message) =>
      set((state) => ({ messages: [...state.messages, { ...message }] })),
    beginAssistantMessage: (messageId) =>
      set((state) => ({
        messages: [
          ...state.messages,
          { id: messageId, role: "assistant", content: "" },
        ],
      })),
    appendAssistantToken: (requestId, text) =>
      set((state) => {
        if (state.activeRequestId !== requestId || !text) {
          return state;
        }
        const messages = [...state.messages];
        const index = messages.length - 1;
        const current = messages[index];
        if (!current || current.role !== "assistant") {
          return state;
        }
        messages[index] = { ...current, content: `${current.content}${text}` };
        return { messages };
      }),
    startStream: (requestId) =>
      set({
        activeRequestId: requestId,
        currentRunId: null,
        currentRunStatus: "connecting",
        activeProcessingStep: null,
        streamError: null,
      }),
    updateExecution: (requestId, update) =>
      set((state) => {
        if (state.activeRequestId !== requestId) {
          return state;
        }
        return {
          currentRunId: update.runId ?? state.currentRunId,
          currentRunStatus: update.status ?? state.currentRunStatus,
          activeProcessingStep:
            update.stepName === undefined
              ? state.activeProcessingStep
              : update.stepName,
          streamError:
            update.error === undefined ? state.streamError : update.error,
        };
      }),
    finishStream: (requestId, status = "completed") =>
      set((state) => {
        if (state.activeRequestId !== requestId) {
          return state;
        }
        return {
          currentRunStatus: status,
          activeProcessingStep: null,
          activeRequestId: null,
        };
      }),
  }));
}

export const studioStore = createStudioStore();

export function useStudioStore(selector) {
  return useStore(studioStore, selector);
}
