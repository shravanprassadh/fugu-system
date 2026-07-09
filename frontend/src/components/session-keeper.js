"use client";

import { useEffect } from "react";

import { SESSION_STORAGE_KEY, studioStore } from "./store";

const ACTIVITY_EVENTS = ["pointerdown", "keydown", "touchstart", "focus"];
const SESSION_CHECK_INTERVAL_MS = 60_000;

function markActivityIfFresh() {
  const state = studioStore.getState();
  if (!state.isAuthenticated) {
    return;
  }
  if (state.enforceSessionFreshness()) {
    state.touchSession();
  }
}

function enforceFreshness() {
  studioStore.getState().enforceSessionFreshness();
}

export function SessionKeeper() {
  useEffect(() => {
    const initialCheck = window.setTimeout(enforceFreshness, 0);
    const activityOptions = { passive: true };
    const handleStorage = (event) => {
      if (event.key === SESSION_STORAGE_KEY && event.newValue === null) {
        studioStore.getState().clearSession();
      }
    };

    ACTIVITY_EVENTS.forEach((eventName) => {
      window.addEventListener(eventName, markActivityIfFresh, activityOptions);
    });
    window.addEventListener("visibilitychange", enforceFreshness);
    window.addEventListener("storage", handleStorage);

    const timer = window.setInterval(enforceFreshness, SESSION_CHECK_INTERVAL_MS);

    return () => {
      window.clearTimeout(initialCheck);
      ACTIVITY_EVENTS.forEach((eventName) => {
        window.removeEventListener(eventName, markActivityIfFresh, activityOptions);
      });
      window.removeEventListener("visibilitychange", enforceFreshness);
      window.removeEventListener("storage", handleStorage);
      window.clearInterval(timer);
    };
  }, []);

  return null;
}
