import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HelpRequestResolutionForm } from "@/components/admin/help-request-resolution-form";
import { HelpRequestCreateForm } from "@/components/help/help-request-create-form";
import { AppShell } from "@/components/layout/app-shell";
import { MarkNotificationsRead } from "@/components/notifications/mark-notifications-read";
import { ApiError } from "@/lib/api/client";
import type {
  AdminHelpRequestDetail,
  HelpRequestDetail,
  User,
} from "@/lib/api/types";

const { csrfFetchMock, pushMock, refreshMock, replaceMock } = vi.hoisted(() => ({
  csrfFetchMock: vi.fn(),
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/help",
  useRouter: () => ({
    push: pushMock,
    refresh: refreshMock,
    replace: replaceMock,
  }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  csrfFetch: csrfFetchMock,
}));

const student: User = {
  id: "student-1",
  email: "student@connect.hkust-gz.edu.cn",
  student_number: "20260001",
  full_name: "测试学生",
  role: "student",
  status: "active",
  cohort: null,
  direction: null,
  email_verified_at: "2026-08-28T00:00:00Z",
  created_at: "2026-08-28T00:00:00Z",
  revision: 1,
};

const admin: User = {
  ...student,
  id: "admin-1",
  email: "admin@connect.hkust-gz.edu.cn",
  full_name: "测试管理员",
  role: "admin",
};

function studentDetail(
  overrides: Partial<HelpRequestDetail> = {},
): HelpRequestDetail {
  return {
    id: "help-1",
    request_type: "system_feedback",
    status: "open",
    title: "移动端按钮无法使用",
    content_html: "<p>复现步骤</p>",
    resolution_html: null,
    notification_ids: [],
    created_at: "2026-08-28T01:00:00Z",
    updated_at: "2026-08-28T01:00:00Z",
    resolved_at: null,
    revision: 1,
    ...overrides,
  };
}

function adminDetail(
  overrides: Partial<AdminHelpRequestDetail> = {},
): AdminHelpRequestDetail {
  return {
    ...studentDetail(),
    content_markdown: "复现步骤",
    resolution_markdown: null,
    resolved_by: null,
    created_by: {
      id: student.id,
      full_name: student.full_name,
      student_number: student.student_number,
      email: student.email,
    },
    ...overrides,
  };
}

describe("feedback and help request UI", () => {
  beforeEach(() => {
    csrfFetchMock.mockReset();
    pushMock.mockReset();
    refreshMock.mockReset();
    replaceMock.mockReset();
  });

  it("submits a normalized student help request and opens its private detail", async () => {
    csrfFetchMock.mockResolvedValue(studentDetail());
    render(<HelpRequestCreateForm />);

    fireEvent.change(screen.getByLabelText("类型"), {
      target: { value: "question" },
    });
    fireEvent.change(screen.getByLabelText("标题"), {
      target: { value: "  如何选择培训方向？  " },
    });
    fireEvent.change(screen.getByLabelText("详情"), {
      target: { value: "  请说明不同方向的培训内容。  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交反馈答疑" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    expect(csrfFetchMock).toHaveBeenCalledWith("/help-requests", {
      method: "POST",
      body: JSON.stringify({
        request_type: "question",
        title: "  如何选择培训方向？  ",
        content_markdown: "  请说明不同方向的培训内容。  ",
      }),
    });
    expect(pushMock).toHaveBeenCalledWith("/help/help-1");
    expect(refreshMock).toHaveBeenCalledOnce();
  });

  it("explains when feedback stays private and questions become public", () => {
    const { unmount } = render(<HelpRequestCreateForm />);

    expect(
      screen.getByText(/系统反馈始终仅本人和管理员可见/),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("类型"), {
      target: { value: "question" },
    });
    expect(
      screen.getByText(/问题解答前仅本人和管理员可见，管理员解答后将匿名公开/),
    ).toBeInTheDocument();
    unmount();

    render(
      <HelpRequestResolutionForm
        initialRequest={adminDetail({ request_type: "question" })}
      />,
    );
    expect(
      screen.getByText(
        /问题答疑保存后会向所有登录用户匿名公开，并向提问学生发送不含正文的站内提醒/,
      ),
    ).toBeInTheDocument();
  });

  it("disables the create action while a request is pending", async () => {
    csrfFetchMock.mockImplementation(() => new Promise(() => undefined));
    render(<HelpRequestCreateForm />);

    fireEvent.change(screen.getByLabelText("标题"), {
      target: { value: "系统反馈" },
    });
    fireEvent.change(screen.getByLabelText("详情"), {
      target: { value: "按钮没有反应" },
    });
    const submit = screen.getByRole("button", { name: "提交反馈答疑" });
    fireEvent.click(submit);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "提交中…" })).toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "提交中…" }));
    expect(csrfFetchMock).toHaveBeenCalledTimes(1);
  });

  it("submits an administrator resolution with the current revision", async () => {
    csrfFetchMock.mockResolvedValue(
      adminDetail({
        status: "resolved",
        resolution_markdown: "已修复，请刷新后重试。",
        resolution_html: "<p>已修复，请刷新后重试。</p>",
        resolved_by: admin.id,
        resolved_at: "2026-08-28T02:00:00Z",
        revision: 2,
      }),
    );
    render(<HelpRequestResolutionForm initialRequest={adminDetail()} />);

    fireEvent.change(screen.getByLabelText("处理结果或答复"), {
      target: { value: "已修复，请刷新后重试。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存并通知学生" }));

    await screen.findByText("处理结果已保存，学生已收到站内提醒。");
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/help-requests/help-1/resolution",
      {
        method: "PUT",
        body: JSON.stringify({
          resolution_markdown: "已修复，请刷新后重试。",
          revision: 1,
        }),
      },
    );
    expect(refreshMock).toHaveBeenCalledOnce();
    expect(screen.getByText(/当前版本 2/)).toBeInTheDocument();
  });

  it("shows a stable revision conflict message", async () => {
    csrfFetchMock.mockRejectedValue(
      new ApiError(
        new Response(null, { status: 409 }),
        {
          error: {
            code: "REVISION_CONFLICT",
            message: "记录已更新。",
            request_id: "request-1",
          },
        },
      ),
    );
    render(
      <HelpRequestResolutionForm
        initialRequest={
          adminDetail({
            status: "resolved",
            resolution_markdown: "旧答复",
            resolution_html: "<p>旧答复</p>",
            resolved_by: admin.id,
            resolved_at: "2026-08-28T02:00:00Z",
            revision: 2,
          })
        }
      />,
    );

    fireEvent.change(screen.getByLabelText("处理结果或答复"), {
      target: { value: "新的答复" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存并通知学生" }));

    expect(
      await screen.findByText("该记录已被更新，请刷新页面后再提交。"),
    ).toBeInTheDocument();
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("marks only the opened help request notifications as read", async () => {
    csrfFetchMock.mockResolvedValue(undefined);
    render(<MarkNotificationsRead notificationIds={["notice-1", "notice-2"]} />);

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(2));
    expect(csrfFetchMock).toHaveBeenNthCalledWith(
      1,
      "/notifications/notice-1/read",
      { method: "POST" },
    );
    expect(csrfFetchMock).toHaveBeenNthCalledWith(
      2,
      "/notifications/notice-2/read",
      { method: "POST" },
    );
    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
  });

  it("shows only the role-appropriate feedback navigation target", () => {
    const { unmount } = render(
      <AppShell
        unreadCounts={{
          announcements: 0,
          assignments: 0,
          competitions: 0,
          help_requests: 2,
        }}
        user={student}
      >
        <p>学生内容</p>
      </AppShell>,
    );
    expect(screen.getByRole("link", { name: "反馈答疑，2 条未读" })).toHaveAttribute(
      "href",
      "/help",
    );
    expect(
      screen.queryByRole("link", { name: "用户管理" }),
    ).not.toBeInTheDocument();
    unmount();

    render(
      <AppShell user={admin}>
        <p>管理内容</p>
      </AppShell>,
    );
    expect(screen.getByRole("link", { name: "反馈答疑" })).toHaveAttribute(
      "href",
      "/admin/help",
    );
    expect(
      screen.queryByRole("link", { name: "培训文档" }),
    ).not.toBeInTheDocument();
  });
});
describe("administrator help request deletion", () => {
  beforeEach(() => {
    csrfFetchMock.mockReset();
    pushMock.mockReset();
    refreshMock.mockReset();
    replaceMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("confirms and deletes a resolved public question", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValue(undefined);
    render(
      <HelpRequestResolutionForm
        initialRequest={adminDetail({
          request_type: "question",
          status: "resolved",
          resolution_markdown: "已解答",
          resolution_html: "<p>已解答</p>",
          resolved_by: admin.id,
          resolved_at: "2026-08-28T02:00:00Z",
          revision: 2,
        })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "删除问题答疑" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    expect(confirm).toHaveBeenCalledWith(
      "确认永久删除这条问题答疑？删除后将从学生本人记录和匿名公开答疑移除，且无法由应用恢复。",
    );
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/help-requests/help-1",
      { method: "DELETE" },
    );
    expect(replaceMock).toHaveBeenCalledWith("/admin/help");
  });

  it("does not request deletion when confirmation is cancelled", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<HelpRequestResolutionForm initialRequest={adminDetail()} />);

    fireEvent.click(screen.getByRole("button", { name: "删除系统反馈" }));

    expect(csrfFetchMock).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("keeps the detail page and shows the API error when deletion fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockRejectedValue(
      new ApiError(
        new Response(null, { status: 404 }),
        {
          error: {
            code: "RESOURCE_NOT_FOUND",
            message: "反馈答疑记录不存在或当前不可见。",
            request_id: "request-delete",
          },
        },
      ),
    );
    render(<HelpRequestResolutionForm initialRequest={adminDetail()} />);

    fireEvent.click(screen.getByRole("button", { name: "删除系统反馈" }));

    expect(
      await screen.findByText("反馈答疑记录不存在或当前不可见。"),
    ).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
