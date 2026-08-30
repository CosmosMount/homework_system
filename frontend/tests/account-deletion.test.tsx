import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccountDeletion } from "@/components/profile/account-deletion";
import { ApiError } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

const { clearCsrfTokenMock, csrfFetchMock, refreshMock, replaceMock } =
  vi.hoisted(() => ({
    clearCsrfTokenMock: vi.fn(),
    csrfFetchMock: vi.fn(),
    refreshMock: vi.fn(),
    replaceMock: vi.fn(),
  }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: refreshMock,
    replace: replaceMock,
  }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  clearCsrfToken: clearCsrfTokenMock,
  csrfFetch: csrfFetchMock,
}));

const student: User = {
  id: "student-id",
  email: "student@connect.hkust-gz.edu.cn",
  student_number: "S001",
  full_name: "测试学生",
  role: "student",
  status: "active",
  cohort: null,
  direction: null,
  email_verified_at: "2026-08-01T00:00:00Z",
  created_at: "2026-08-01T00:00:00Z",
  revision: 1,
};

describe("self-service account deletion", () => {
  beforeEach(() => {
    clearCsrfTokenMock.mockReset();
    csrfFetchMock.mockReset();
    refreshMock.mockReset();
    replaceMock.mockReset();
  });

  it("requires password, exact email and explicit irreversible confirmation", async () => {
    csrfFetchMock.mockResolvedValue(undefined);
    render(<AccountDeletion user={student} />);

    fireEvent.change(screen.getByLabelText("当前密码"), {
      target: { value: "current-password" },
    });
    fireEvent.change(screen.getByLabelText("输入当前账号邮箱以确认"), {
      target: { value: student.email },
    });
    fireEvent.click(
      screen.getByLabelText(/我理解注销会直接删除 测试学生 的账号与个人数据/),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "永久注销我的账号" }),
    );

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(csrfFetchMock).toHaveBeenCalledWith("/auth/account", {
      method: "DELETE",
      body: JSON.stringify({
        current_password: "current-password",
        confirmation_email: student.email,
      }),
    });
    expect(clearCsrfTokenMock).toHaveBeenCalledOnce();
    expect(replaceMock).toHaveBeenCalledWith("/login?account_deleted=1");
    expect(refreshMock).toHaveBeenCalledOnce();
  });

  it("rejects a mismatched email before sending a destructive request", () => {
    render(<AccountDeletion user={student} />);

    fireEvent.change(screen.getByLabelText("当前密码"), {
      target: { value: "current-password" },
    });
    fireEvent.change(screen.getByLabelText("输入当前账号邮箱以确认"), {
      target: { value: "other@connect.hkust-gz.edu.cn" },
    });
    fireEvent.click(
      screen.getByLabelText(/我理解注销会直接删除 测试学生 的账号与个人数据/),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "永久注销我的账号" }),
    );

    expect(
      screen.getByText("确认邮箱必须与当前账号邮箱完全一致。"),
    ).toBeInTheDocument();
    expect(csrfFetchMock).not.toHaveBeenCalled();
  });

  it("keeps the form on backend denial and clears the password", async () => {
    csrfFetchMock.mockRejectedValue(
      new ApiError(new Response(null, { status: 409 }), {
        error: {
          code: "STATE_CONFLICT",
          message: "不能删除系统中最后一个激活管理员。",
          request_id: "request-id",
        },
      }),
    );
    render(
      <AccountDeletion
        user={{
          email: "admin@connect.hkust-gz.edu.cn",
          full_name: "测试管理员",
        }}
      />,
    );

    const password = screen.getByLabelText("当前密码");
    fireEvent.change(password, { target: { value: "current-password" } });
    fireEvent.change(screen.getByLabelText("输入当前账号邮箱以确认"), {
      target: { value: "admin@connect.hkust-gz.edu.cn" },
    });
    fireEvent.click(
      screen.getByLabelText(/我理解注销会直接删除 测试管理员 的账号与个人数据/),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "永久注销我的账号" }),
    );

    expect(
      await screen.findByText("不能删除系统中最后一个激活管理员。"),
    ).toBeInTheDocument();
    expect(password).toHaveValue("");
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
