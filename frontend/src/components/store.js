"use client";

import { useStore } from "zustand";
import { createStore } from "zustand/vanilla";

export const studioStore = createStore(() => ({
  sessionCredential: null,
  username: null,
  messages: [],
}));

export function useStudioStore(selector) {
  return useStore(studioStore, selector);
}
