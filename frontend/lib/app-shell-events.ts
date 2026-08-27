export const APP_SHELL_COLLAPSE_EVENT = "pnx:app-shell-collapse";

export function requestAppShellCollapse(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(APP_SHELL_COLLAPSE_EVENT));
  }
}
