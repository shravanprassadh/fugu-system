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
    enforceFreshness();

    const activityOptions = { passive: true };
    ACTIVITY_EVENTS.forEach((eventName) => {
      window.addEventListener(eventName, markActivityIfFresh, activityOptions);
    });
    window.addEventListener("visibilitychange", enforceFreshness);
    window.addEventListener("storage", (event) => {
      if (event.key === SESSION_STORAGE_KEY && event.newValue === null) {
        studioStore.getState().clearSession();
      }
    });

    const timer = window.setInterval(enforceFreshness, SESSION_CHECK_INTERVAL_MS);

    return () => {
      ACTIVITY_EVENTS.forEach((eventName) => {
        window.removeEventListener(eventName, markActivityIfFresh, activityOptions);
      });
      window.removeEventListener("visibilitychange", enforceFreshness);
      window.clearInterval(timer);
    };
  }, []);

  return null;
}
