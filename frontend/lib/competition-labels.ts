import type {
  CompetitionStatus,
  RegistrationStatus,
  TeamStatus,
} from "@/lib/api/types";

const competitionLabels: Record<CompetitionStatus, string> = {
  draft: "草稿",
  registration_open: "报名中",
  registration_closed: "报名已结束",
  submission_open: "赛事进行中",
  submission_closed: "赛事已结束",
  archived: "已归档",
};

const registrationLabels: Record<RegistrationStatus, string> = {
  registered: "已报名",
  withdrawn: "已撤回",
  disqualified: "已取消资格",
};

const teamLabels: Record<TeamStatus, string> = {
  forming: "组队中",
  dissolved: "已解散",
  locked: "有效且已锁定",
  invalid: "人数不足",
  disqualified: "已取消资格",
  archived: "已归档",
};

export function competitionStatusLabel(status: CompetitionStatus): string {
  return competitionLabels[status];
}

export function registrationStatusLabel(
  status: RegistrationStatus | null,
): string {
  return status === null ? "未报名" : registrationLabels[status];
}

export function teamStatusLabel(status: TeamStatus | null): string {
  return status === null ? "尚未组队" : teamLabels[status];
}

export function statusTagClass(
  status: CompetitionStatus | TeamStatus | RegistrationStatus,
): string {
  if (["registration_open", "submission_open", "registered"].includes(status)) {
    return "border-[var(--color-info)] text-[var(--color-info)]";
  }
  if (["locked", "archived"].includes(status)) {
    return "border-[var(--color-success)] text-[var(--color-success)]";
  }
  if (["invalid", "disqualified"].includes(status)) {
    return "border-[var(--color-danger)] text-[var(--color-danger)]";
  }
  return "border-[var(--color-border-strong)] text-[var(--color-text-secondary)]";
}
