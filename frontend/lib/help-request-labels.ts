import type {
  HelpRequestStatus,
  HelpRequestType,
} from "@/lib/api/types";

const typeLabels: Record<HelpRequestType, string> = {
  system_feedback: "系统反馈",
  question: "问题答疑",
};

const statusLabels: Record<HelpRequestStatus, string> = {
  open: "待处理",
  resolved: "已解决",
};

export function helpRequestTypeLabel(value: HelpRequestType): string {
  return typeLabels[value];
}

export function helpRequestStatusLabel(value: HelpRequestStatus): string {
  return statusLabels[value];
}
