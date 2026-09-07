export const APP_SHELL_COLLAPSE_EVENT = "pnx:app-shell-collapse";
export const NOTIFICATIONS_READ_EVENT = "pnx:notifications-read";

export function requestAppShellCollapse(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(APP_SHELL_COLLAPSE_EVENT));
  }
}

export function notifyNotificationsRead(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(NOTIFICATIONS_READ_EVENT));
  }
}
