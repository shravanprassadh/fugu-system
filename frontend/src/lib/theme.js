export const THEME_STORAGE_KEY = "fugu-theme-mode";
export const THEME_MODES = ["light", "dark", "system"];
export const DEFAULT_THEME_MODE = "light";

const DARK_QUERY = "(prefers-color-scheme: dark)";

const themeListeners = new Set();

export function normalizeThemeMode(candidate) {
  return THEME_MODES.includes(candidate) ? candidate : DEFAULT_THEME_MODE;
}

export function resolveTheme(mode, prefersDark) {
  if (mode === "dark") {
    return "dark";
  }
  if (mode === "system") {
    return prefersDark ? "dark" : "light";
  }
  return "light";
}

export function readStoredThemeMode() {
  if (typeof window === "undefined") {
    return DEFAULT_THEME_MODE;
  }
  try {
    return normalizeThemeMode(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return DEFAULT_THEME_MODE;
  }
}

export function getServerThemeMode() {
  return DEFAULT_THEME_MODE;
}

export function systemPrefersDark() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia(DARK_QUERY).matches;
}

function paintTheme(theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
}

function notifyThemeListeners() {
  themeListeners.forEach((listener) => listener());
}

export function applyThemeMode(mode) {
  const normalized = normalizeThemeMode(mode);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, normalized);
  } catch {
    // Persistence is best-effort; the current tab still themes correctly.
  }
  paintTheme(resolveTheme(normalized, systemPrefersDark()));
  notifyThemeListeners();
  return normalized;
}

/*
 * External-store subscription used with useSyncExternalStore. Every mounted
 * theme control shares one source of truth, so the sidebar toggle and the
 * settings picker never drift apart, and changes made in another browser tab
 * are picked up through the storage event.
 */
export function subscribeThemeMode(onChange) {
  themeListeners.add(onChange);
  const onStorage = (event) => {
    if (event.key === THEME_STORAGE_KEY || event.key === null) {
      paintTheme(resolveTheme(readStoredThemeMode(), systemPrefersDark()));
      onChange();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    themeListeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

export function watchSystemTheme(onSystemChange) {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {};
  }
  const media = window.matchMedia(DARK_QUERY);
  const handler = (event) => onSystemChange(event.matches);
  media.addEventListener("change", handler);
  return () => media.removeEventListener("change", handler);
}

// Runs before hydration so the first paint already uses the saved mode.
// This string is a build-time constant and never includes user input.
export const themeInitScript = `(function () {
  var mode = "light";
  try {
    var stored = window.localStorage.getItem("${THEME_STORAGE_KEY}");
    if (stored === "dark" || stored === "system") { mode = stored; }
  } catch (error) {}
  var dark = mode === "dark" || (mode === "system" &&
    window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  var root = document.documentElement;
  root.dataset.theme = dark ? "dark" : "light";
  root.style.colorScheme = dark ? "dark" : "light";
})();`;
