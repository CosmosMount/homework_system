export function formatDateTime(value: string | null): string {
  if (value === null) {
    return "—";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return bytes + " B";
  }
  if (bytes < 1024 * 1024) {
    return (bytes / 1024).toFixed(1) + " KiB";
  }
  return (bytes / (1024 * 1024)).toFixed(1) + " MiB";
}
