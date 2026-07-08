"use client";

import { useStore } from "zustand";
import { createStore } from "zustand/vanilla";

const initialState = {
  sessionCredential: null,
  username: null,
  isAuthenticated: false,
  threads: [],
  activeThreadId: null,
  messages: [],
  currentRunId: null,
  currentRunStatus: "idle",
  activeProcessingStep: null,
  streamError: null,
  activeRequestId: null,
};

export function createStudioStore() {
  return createStore((set) => ({
    ...initialState,
    setSession: ({ sessionCredential, username }) => {
      if (!sessionCredential || !username) {
        throw new Error("Session data is incomplete.");
      }
      set({
        sessionCredential,
        username,
        isAuthenticated: true,
        streamError: null,
      });
    },
    clearSession: () => set({ ...initialState }),
    setThreads: (threads) => set({ threads: [...threads] }),
<<<<<<< Updated upstream
=======
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
>>>>>>> Stashed changes
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
