/**
 * Tauri environment detection utilities.
 * Import from this module instead of duplicating the check across components.
 */

/**
 * Returns true when the frontend is running inside a Tauri desktop
 * webview (i.e. `window.__TAURI_INTERNALS__` is present).
 */
export function isTauriEnvironment(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}
