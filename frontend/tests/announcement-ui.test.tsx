import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AnnouncementListPanel } from "@/components/admin/announcement-list-panel";
import { SafeHtml } from "@/components/announcements/safe-html";
import { AppShell } from "@/components/layout/app-shell";
import type { AnnouncementAdmin, User } from "@/lib/api/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }),
}));

const student: User = {
  id: "student-id",
  email: "student@connect.hkust-gz.edu.cn",
  student_number: "20260001",
  full_name: "测试学生",
  role: "student",
  status: "active",
  cohort: null,
  direction: null,
  email_verified_at: "2026-08-24T00:00:00Z",
  created_at: "2026-08-24T00:00:00Z",
  revision: 1,
};

function announcement(
  id: string,
  title: string,
  status: AnnouncementAdmin["status"],
): AnnouncementAdmin {
  return {
    id,
    title,
    summary: title + "摘要",
    body_markdown: "正文",
    body_html: "<p>正文</p>",
    status,
    audience: {
      all_students: true,
      cohort_ids: [],
      direction_ids: [],
      match: "intersection",
    },
    attachment_file_ids: [],
    publish_at: null,
    published_at: status === "published" ? "2026-08-24T00:00:00Z" : null,
    pinned_until: null,
    send_email: false,
    archived_at: null,
    estimated_recipient_count: 10,
    actual_recipient_count: status === "published" ? 10 : 0,
    created_at: "2026-08-24T00:00:00Z",
    updated_at: "2026-08-24T00:00:00Z",
    revision: 1,
  };
}

describe("announcement UI", () => {
  it("shows the unread badge and student navigation", () => {
    render(
      <AppShell unreadCount={3} user={student}>
        <p>内容</p>
      </AppShell>,
    );
    expect(screen.getByRole("link", { name: /通知/ })).toHaveAttribute(
      "href",
      "/announcements",
    );
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "用户管理" })).not.toBeInTheDocument();
  });

  it("renders backend-sanitized HTML as document structure", () => {
    render(
      <SafeHtml sanitizedHtml={'<h2>安全标题</h2><p>正文 <a href="https://example.com">链接</a></p>'} />,
    );
    expect(screen.getByRole("heading", { name: "安全标题", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "链接" })).toHaveAttribute(
      "href",
      "https://example.com",
    );
  });

  it("filters the admin announcement list by status and query", () => {
    render(
      <AnnouncementListPanel
        initialAnnouncements={[
          announcement("one", "已发布通知", "published"),
          announcement("two", "草稿通知", "draft"),
        ]}
      />,
    );
    fireEvent.change(screen.getByLabelText("状态"), {
      target: { value: "draft" },
    });
    expect(screen.getByText("草稿通知")).toBeInTheDocument();
    expect(screen.queryByText("已发布通知")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("搜索通知"), {
      target: { value: "不存在" },
    });
    expect(screen.getByText("没有符合筛选条件的通知。")).toBeInTheDocument();
  });
});
