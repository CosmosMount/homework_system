import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnnouncementEditor } from "@/components/admin/announcement-editor";
import { AnnouncementListPanel } from "@/components/admin/announcement-list-panel";
import { SafeHtml } from "@/components/announcements/safe-html";
import { AppShell } from "@/components/layout/app-shell";
import type { AnnouncementAdmin, User } from "@/lib/api/types";

const { csrfFetchMock, refreshMock, replaceMock } = vi.hoisted(() => ({
  csrfFetchMock: vi.fn(),
  refreshMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/announcements",
  useRouter: () => ({ refresh: refreshMock, replace: replaceMock }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  csrfFetch: csrfFetchMock,
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
  beforeEach(() => {
    csrfFetchMock.mockReset();
    refreshMock.mockReset();
    replaceMock.mockReset();
  });

  it("shows the unread badge and student navigation", () => {
    render(
      <AppShell
        unreadCounts={{
          announcements: 2,
          assignments: 3,
          competitions: 0,
          help_requests: 1,
        }}
        user={student}
      >
        <p>内容</p>
      </AppShell>,
    );
    expect(screen.getByRole("link", { name: /通知/ })).toHaveAttribute(
      "href",
      "/announcements",
    );
    expect(screen.getByRole("link", { name: /通知/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "通知，2 条未读" })).toHaveAttribute(
      "href",
      "/announcements",
    );
    expect(screen.getByRole("link", { name: "作业，3 条未读" })).toHaveAttribute(
      "href",
      "/assignments",
    );
    expect(screen.getByRole("link", { name: "反馈答疑，1 条未读" })).toHaveAttribute(
      "href",
      "/help",
    );
    expect(screen.queryByRole("link", { name: "用户管理" })).not.toBeInTheDocument();
    expect(screen.getByTestId("app-shell-sidebar")).toHaveAttribute(
      "data-state",
      "expanded",
    );

    fireEvent.click(screen.getByRole("button", { name: "折叠主要导航" }));
    expect(screen.getByTestId("app-shell-sidebar")).toHaveAttribute(
      "data-state",
      "collapsed",
    );
    expect(screen.getByRole("button", { name: "展开主要导航" })).toBeInTheDocument();
  });

  it("opens the sidebar drawer on narrow layouts", () => {
    render(
      <AppShell user={student}>
        <p>内容</p>
      </AppShell>,
    );

    fireEvent.click(screen.getByRole("button", { name: "打开主要导航" }));
    expect(screen.getAllByRole("complementary", { name: "主要导航侧栏" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "关闭主要导航" })).toHaveLength(2);
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

  it("keeps the announcement when delete confirmation is cancelled", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(
      <AnnouncementEditor
        directions={[]}
        initialAnnouncement={announcement("announcement-1", "已发布通知", "published")}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "删除通知" }));

    expect(confirm).toHaveBeenCalledOnce();
    expect(csrfFetchMock).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("confirms and deletes a published announcement before returning to the list", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValue(undefined);

    render(
      <AnnouncementEditor
        directions={[]}
        initialAnnouncement={announcement("announcement-1", "已发布通知", "published")}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "删除通知" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("学生和管理页面隐藏"));
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/announcements/announcement-1",
      { method: "DELETE" },
    );
    expect(replaceMock).toHaveBeenCalledWith("/admin/announcements");
  });
  it("allows a manually archived announcement to be deleted", async () => {
    const archived: AnnouncementAdmin = {
      ...announcement("announcement-archived", "已归档通知", "archived"),
      published_at: "2026-08-24T00:00:00Z",
      archived_at: "2026-08-25T00:00:00Z",
    };
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValue(undefined);

    render(
      <AnnouncementEditor
        directions={[]}
        initialAnnouncement={archived}
      />,
    );

    expect(screen.getByRole("button", { name: "删除通知" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存草稿" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "保存并立即发布" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "保存并发送更新提醒" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "删除通知" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("学生和管理页面隐藏"));
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/announcements/announcement-archived",
      { method: "DELETE" },
    );
    expect(replaceMock).toHaveBeenCalledWith("/admin/announcements");
  });
});
