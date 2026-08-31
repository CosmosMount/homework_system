import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";
import RegisterPage from "@/app/register/page";
import { ResetPasswordForm } from "@/components/auth/auth-forms";
import { ApiError } from "@/lib/api/client";
import { safeReturnPath } from "@/lib/safe-return-path";

const { apiFetchMock, clearCsrfTokenMock, refreshMock, replaceMock } =
  vi.hoisted(() => ({
    apiFetchMock: vi.fn(),
    clearCsrfTokenMock: vi.fn(),
    refreshMock: vi.fn(),
    replaceMock: vi.fn(),
  }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ refresh: refreshMock, replace: replaceMock }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
    clearCsrfToken: clearCsrfTokenMock,
  };
});

describe("login page", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    clearCsrfTokenMock.mockReset();
    refreshMock.mockReset();
    replaceMock.mockReset();
  });

  it("shows an accessible login form", async () => {
    render(await LoginPage());

    expect(
      screen.getByRole("heading", { name: "登录训练平台" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("用户名或校园邮箱")).toHaveAttribute(
      "placeholder",
      "name 或 name@connect.hkust-gz.edu.cn",
    );
    expect(
      screen.getByText(
        "新注册账号需先完成邮箱验证；验证后可填写邮箱前缀或完整邮箱",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("密码")).toHaveAttribute("type", "password");
    expect(
      screen.getByRole("checkbox", { name: "记住登录状态" }),
    ).not.toBeChecked();
    expect(screen.getByText(/最多 30 天免重复登录/)).toHaveTextContent(
      "系统不会保存你的密码",
    );
    expect(screen.getByRole("link", { name: "重新发送验证邮件" })).toHaveAttribute(
      "href", "/resend-verification",
    );
    expect(screen.getByRole("button", { name: "登录" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "注册账号" })).toHaveAttribute(
      "href",
      "/register",
    );
  });

  it("submits credentials and routes an administrator", async () => {
    apiFetchMock.mockResolvedValue({ user: { role: "admin" } });
    render(await LoginPage());

    fireEvent.change(screen.getByLabelText("用户名或校园邮箱"), {
      target: { value: "admin" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          identifier: "admin",
          password: "correct-password",
          remember_me: false,
        }),
      });
    });
    expect(clearCsrfTokenMock).toHaveBeenCalledOnce();
    expect(replaceMock).toHaveBeenCalledWith("/admin/dashboard");
    expect(refreshMock).toHaveBeenCalledOnce();
  });

  it("requests a persistent login only when explicitly checked", async () => {
    apiFetchMock.mockResolvedValue({ user: { role: "student" } });
    render(await LoginPage());

    fireEvent.change(screen.getByLabelText("用户名或校园邮箱"), {
      target: { value: "student" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "记住登录状态" }));
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          identifier: "student",
          password: "correct-password",
          remember_me: true,
        }),
      });
    });
  });

  it("shows the message from a local runtime error", async () => {
    apiFetchMock.mockRejectedValue(new Error("服务暂时不可用。"));
    render(await LoginPage());

    fireEvent.change(screen.getByLabelText("用户名或校园邮箱"), {
      target: { value: "admin@connect.hkust-gz.edu.cn" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "服务暂时不可用。",
    );
  });

  it("returns to a same-origin intention form after login", async () => {
    apiFetchMock.mockResolvedValue({ user: { role: "student" } });
    const returnTo = "/intentions/survey-1?token=qr-token";
    render(
      await LoginPage({
        searchParams: Promise.resolve({ next: returnTo }),
      }),
    );

    fireEvent.change(screen.getByLabelText("用户名或校园邮箱"), {
      target: { value: "student" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith(returnTo));
  });

  it("rejects external and recursive login return paths", () => {
    expect(safeReturnPath("https://evil.invalid/steal")).toBeNull();
    expect(safeReturnPath("//evil.invalid/steal")).toBeNull();
    expect(safeReturnPath("/login?next=/dashboard")).toBeNull();
    expect(safeReturnPath("/login/?next=/dashboard")).toBeNull();
    expect(safeReturnPath("/intentions/survey-1?token=safe")).toBe(
      "/intentions/survey-1?token=safe",
    );
  });

  it("shows the derived username and verification requirement after registration", async () => {
    apiFetchMock.mockResolvedValue({
      verification_expires_at: "2026-08-26T10:00:00+08:00",
    });
    render(<RegisterPage />);

    fireEvent.change(screen.getByLabelText("真实姓名"), {
      target: { value: "测试学生" },
    });
    fireEvent.change(screen.getByLabelText("学号"), {
      target: { value: "20260001" },
    });
    fireEvent.change(screen.getByLabelText("校园邮箱"), {
      target: { value: "New.Student@connect.hkust-gz.edu.cn" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "safe-test-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建账号" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "你的用户名是 new.student",
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "完成邮箱验证前，用户名和完整邮箱都不能登录",
    );
    expect(apiFetchMock).toHaveBeenCalledWith("/auth/register", {
      method: "POST",
      body: expect.stringContaining(
        '"email":"new.student@connect.hkust-gz.edu.cn"',
      ),
    });
  });

  it("shows a duplicate registration email as a field error", async () => {
    apiFetchMock.mockRejectedValue(
      new ApiError(new Response(null, { status: 400 }), {
        error: {
          code: "VALIDATION_ERROR",
          message: "请求参数不符合要求。",
          request_id: "registration-request-id",
          details: [
            { field: "email", reason: "EMAIL_ALREADY_REGISTERED" },
          ],
        },
      }),
    );
    render(<RegisterPage />);

    fireEvent.change(screen.getByLabelText("真实姓名"), {
      target: { value: "测试学生" },
    });
    fireEvent.change(screen.getByLabelText("学号"), {
      target: { value: "20260001" },
    });
    fireEvent.change(screen.getByLabelText("校园邮箱"), {
      target: { value: "existing@connect.hkust-gz.edu.cn" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "safe-test-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建账号" }));

    expect(await screen.findByText("该邮箱已注册。")).toBeInTheDocument();
    expect(screen.getByLabelText("校园邮箱")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.queryByText("服务暂时无法处理请求")).not.toBeInTheDocument();
  });

  it("uses an eight-character minimum for registration and password reset", () => {
    const registration = render(<RegisterPage />);

    expect(screen.getByLabelText("密码")).toHaveAttribute("minlength", "8");
    expect(screen.getByText(/8～128 个字符/)).toBeInTheDocument();

    registration.unmount();
    render(<ResetPasswordForm token="test-reset-token" />);

    expect(screen.getByLabelText("新密码")).toHaveAttribute("minlength", "8");
    expect(screen.getByLabelText("再次输入新密码")).toHaveAttribute(
      "minlength",
      "8",
    );
    expect(screen.getByText(/8～128 个字符/)).toBeInTheDocument();
  });
});
