import type { TeamStatus } from "@/lib/api/types";

const teamLabels: Record<TeamStatus, string> = {
  forming: "组队中",
  dissolved: "已解散",
};

export function teamStatusLabel(status: TeamStatus | null): string {
  return status === null ? "尚未组队" : teamLabels[status];
}

export function statusTagClass(status: TeamStatus): string {
  if (status === "forming") {
    return "border-[var(--color-info)] text-[var(--color-info)]";
  }
  return "border-[var(--color-border-strong)] text-[var(--color-text-secondary)]";
}
