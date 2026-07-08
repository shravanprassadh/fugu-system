"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

import {
  applyThemeMode,
  getServerThemeMode,
  readStoredThemeMode,
  resolveTheme,
  subscribeThemeMode,
  THEME_MODES,
  watchSystemTheme,
} from "../lib/theme";

const MODE_LABELS = { light: "Light", dark: "Dark", system: "System" };

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2.5M12 19.5V22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M2 12h2.5M19.5 12H22M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5Z" />
    </svg>
  );
}

function MonitorIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="4" width="18" height="13" rx="2" />
      <path d="M9 21h6M12 17v4" />
    </svg>
  );
}

const MODE_ICONS = { light: SunIcon, dark: MoonIcon, system: MonitorIcon };

export function useThemeMode() {
  // Shared external store: no state is set inside effects, hydration stays
  // consistent (the server snapshot is the light default), and every mounted
  // theme control reflects the same mode.
  const mode = useSyncExternalStore(subscribeThemeMode, readStoredThemeMode, getServerThemeMode);

  useEffect(() => {
    if (mode !== "system") {
      return undefined;
    }
    return watchSystemTheme((prefersDark) => {
      const root = document.documentElement;
      const theme = resolveTheme("system", prefersDark);
      root.dataset.theme = theme;
      root.style.colorScheme = theme;
    });
  }, [mode]);

  const selectMode = useCallback((nextMode) => {
    applyThemeMode(nextMode);
  }, []);

  return { mode, selectMode };
}

export function ThemeCycleButton() {
  const { mode, selectMode } = useThemeMode();
  const Icon = MODE_ICONS[mode] ?? SunIcon;
  const nextMode = THEME_MODES[(THEME_MODES.indexOf(mode) + 1) % THEME_MODES.length];

  return (
    <button
      type="button"
      className="icon-button"
      onClick={() => selectMode(nextMode)}
      title={`Theme: ${MODE_LABELS[mode]}. Switch to ${MODE_LABELS[nextMode].toLowerCase()}.`}
      aria-label={`Theme: ${MODE_LABELS[mode]}. Switch to ${MODE_LABELS[nextMode].toLowerCase()}.`}
    >
      <Icon />
    </button>
  );
}

export function ThemeModePicker() {
  const { mode, selectMode } = useThemeMode();

  return (
    <div className="segmented" role="radiogroup" aria-label="Theme mode">
      {THEME_MODES.map((candidate) => {
        const Icon = MODE_ICONS[candidate];
        const isActive = mode === candidate;
        return (
          <button
            key={candidate}
            type="button"
            role="radio"
            aria-checked={isActive}
            className={`segmented-option${isActive ? " segmented-option-active" : ""}`}
            onClick={() => selectMode(candidate)}
          >
            <Icon />
            {MODE_LABELS[candidate]}
          </button>
        );
      })}
    </div>
  );
}
