"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  type FormEvent,
  useState,
} from "react";

import {
  buttonClassName,
  Field,
  FormMessage,
} from "@/components/ui/form-controls";
import {
  ApiError,
  apiFetch,
  clearCsrfToken,
  fieldReason,
} from "@/lib/api/client";
import type { User } from "@/lib/api/types";
import { safeReturnPath } from "@/lib/safe-return-path";

const reasonMessages: Record<string, string> = {
  INVALID_CAMPUS_EMAIL: "请输入有效的 @connect.hkust-gz.edu.cn 校园邮箱。",
  EMAIL_ALREADY_REGISTERED: "该邮箱已注册。",
  STUDENT_NUMBER_ALREADY_REGISTERED: "该学号已注册。",
  PASSWORD_TOO_SHORT: "密码至少需要 8 个字符。",
  PASSWORD_TOO_LONG: "密码最多允许 128 个字符。",
  COMMON_PASSWORD: "该密码过于常见，请换一个更独特的密码。",
  PASSWORD_TOO_SIMILAR: "密码不能包含邮箱名或学号。",
};

function fieldMessage(error: unknown, field: string): string | undefined {
  const reason = fieldReason(error, field);
  return reason === undefined ? undefined : (reasonMessages[reason] ?? reason);
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "RATE_LIMITED" && error.retryAfter !== null) {
      return "请求过于频繁，请在 " + error.retryAfter + " 秒后重试。";
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "网络连接失败，请检查网络后重试。";
}

export function LoginForm({ returnTo = null }: Readonly<{ returnTo?: string | null }>) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const result = await apiFetch<{ user: User }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          identifier: form.get("identifier"),
          password: form.get("password"),
        }),
      });
      clearCsrfToken();
      router.replace(
        safeReturnPath(returnTo) ??
          (result.user.role === "admin" ? "/admin/dashboard" : "/dashboard"),
      );
      router.refresh();
    } catch (nextError) {
      setError(nextError);
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="space-y-6" onSubmit={submit}>
      <Field
        autoComplete="username"
        error={fieldMessage(error, "identifier")}
        hint="新注册账号需先完成邮箱验证；验证后可填写邮箱前缀或完整邮箱"
        label="用户名或校园邮箱"
        name="identifier"
        placeholder="name 或 name@connect.hkust-gz.edu.cn"
        required
        type="text"
      />
      <Field
        autoComplete="current-password"
        error={fieldMessage(error, "password")}
        label="密码"
        name="password"
        required
        type={showPassword ? "text" : "password"}
      >
        <button
          className="mt-2 text-sm text-[var(--color-text-secondary)] underline-offset-4 hover:underline"
          onClick={() => setShowPassword((visible) => !visible)}
          type="button"
        >
          {showPassword ? "隐藏密码" : "显示密码"}
        </button>
      </Field>
      {error ? <FormMessage>{errorMessage(error)}</FormMessage> : null}
      <button
        className={buttonClassName + " w-full"}
        disabled={pending}
        type="submit"
      >
        {pending ? "正在登录…" : "登录"}
      </button>
      <div className="flex flex-wrap justify-between gap-3 text-sm text-[var(--color-text-secondary)]">
        <Link className="hover:text-[var(--color-accent-hover)]" href="/register">
          注册账号
        </Link>
        <Link className="hover:text-[var(--color-accent-hover)]" href="/forgot-password">
          忘记密码
        </Link>
        <Link className="hover:text-[var(--color-accent-hover)]" href="/resend-verification">
          重新发送验证邮件
        </Link>
      </div>
    </form>
  );
}

export function RegisterForm() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [registeredUsername, setRegisteredUsername] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const registeredEmail = String(form.get("email") ?? "").trim().toLowerCase();
    try {
      const result = await apiFetch<{ verification_expires_at: string }>(
        "/auth/register",
        {
          method: "POST",
          body: JSON.stringify({
            full_name: form.get("full_name"),
            student_number: form.get("student_number"),
            email: registeredEmail,
            password: form.get("password"),
          }),
        },
      );
      setExpiresAt(result.verification_expires_at);
      setRegisteredUsername(registeredEmail.split("@", 1)[0]);
      event.currentTarget.reset();
    } catch (nextError) {
      setError(nextError);
    } finally {
      setPending(false);
    }
  }

  if (expiresAt !== null && registeredUsername !== null) {
    return (
      <div className="space-y-5">
        <FormMessage tone="success">
          注册成功。你的用户名是 {registeredUsername}。验证邮件已进入发送队列；完成邮箱验证前，用户名和完整邮箱都不能登录。验证后账号会直接激活；若这是空系统的首个激活账号，将自动获得管理员权限。
        </FormMessage>
        <p className="text-sm text-[var(--color-text-secondary)]">
          验证链接有效至 {new Date(expiresAt).toLocaleString("zh-CN")}。
        </p>
        <Link className="text-sm underline underline-offset-4" href="/login">
          返回登录
        </Link>
      </div>
    );
  }

  return (
    <form className="space-y-5" onSubmit={submit}>
      <Field
        autoComplete="name"
        error={fieldMessage(error, "full_name")}
        label="真实姓名"
        name="full_name"
        required
      />
      <Field
        autoComplete="username"
        error={fieldMessage(error, "student_number")}
        label="学号"
        name="student_number"
        required
      />
      <Field
        autoComplete="email"
        error={fieldMessage(error, "email")}
        hint="仅接受 @connect.hkust-gz.edu.cn，不接受旧域名、子域或相似域名。"
        label="校园邮箱"
        name="email"
        placeholder="name@connect.hkust-gz.edu.cn"
        required
        type="email"
      />
      <Field
        autoComplete="new-password"
        error={fieldMessage(error, "password")}
        hint="8～128 个字符；避免常见密码以及姓名、邮箱名或学号。"
        label="密码"
        minLength={8}
        name="password"
        required
        type="password"
      />
      {error ? <FormMessage>{errorMessage(error)}</FormMessage> : null}
      <button
        className={buttonClassName + " w-full"}
        disabled={pending}
        type="submit"
      >
        {pending ? "正在创建账号…" : "创建账号"}
      </button>
      <p className="text-sm text-[var(--color-text-secondary)]">
        已有账号？{" "}
        <Link className="text-[var(--color-info)] underline underline-offset-4 hover:text-[var(--color-accent-hover)]" href="/login">
          返回登录
        </Link>
      </p>
    </form>
  );
}

export function EmailRequestForm({
  mode,
}: Readonly<{ mode: "reset" | "resend" }>) {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const path =
      mode === "reset"
        ? "/auth/password-resets/request"
        : "/auth/email-verifications/resend";
    try {
      await apiFetch<void>(path, {
        method: "POST",
        body: JSON.stringify({ email: form.get("email") }),
      });
      setMessage(
        mode === "reset"
          ? "如果该邮箱对应可用账号，重置邮件已进入发送队列。"
          : "如果该邮箱存在待验证账号，新的验证邮件已进入发送队列。",
      );
    } catch (nextError) {
      setError(nextError);
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="space-y-6" onSubmit={submit}>
      <Field
        autoComplete="email"
        label="校园邮箱"
        name="email"
        placeholder="name@connect.hkust-gz.edu.cn"
        required
        type="email"
      />
      {message ? <FormMessage tone="success">{message}</FormMessage> : null}
      {error ? <FormMessage>{errorMessage(error)}</FormMessage> : null}
      <button
        className={buttonClassName + " w-full"}
        disabled={pending}
        type="submit"
      >
        {pending
          ? "正在提交…"
          : mode === "reset"
            ? "发送重置邮件"
            : "重新发送验证邮件"}
      </button>
      <Link
        className="block text-sm text-[var(--color-text-secondary)] underline underline-offset-4"
        href="/login"
      >
        返回登录
      </Link>
    </form>
  );
}

export function VerifyEmailForm({ token }: Readonly<{ token: string }>) {
  const [pending, setPending] = useState(false);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function verify() {
    setPending(true);
    setError(null);
    try {
      await apiFetch<{ status: "active" }>(
        "/auth/email-verifications/confirm",
        {
          method: "POST",
          body: JSON.stringify({ token }),
        },
      );
      setVerified(true);
    } catch (nextError) {
      setError(nextError);
    } finally {
      setPending(false);
    }
  }

  if (verified) {
    return (
      <div className="space-y-5">
        <FormMessage tone="success">
          邮箱验证成功，账号已直接激活。空系统的首个激活账号会自动成为管理员。
        </FormMessage>
        <Link className={buttonClassName + " inline-flex items-center"} href="/login">
          前往登录
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <FormMessage tone="info">
        点击下方按钮完成验证。本页面不会把令牌发送给第三方。
      </FormMessage>
      {error ? <FormMessage>{errorMessage(error)}</FormMessage> : null}
      <button
        className={buttonClassName + " w-full"}
        disabled={pending}
        onClick={verify}
        type="button"
      >
        {pending ? "正在验证…" : "验证邮箱并激活账号"}
      </button>
      {error instanceof ApiError &&
      ["TOKEN_EXPIRED", "TOKEN_ALREADY_USED"].includes(error.code) ? (
        <Link className="text-sm underline underline-offset-4" href="/resend-verification">
          重新发送验证邮件
        </Link>
      ) : null}
    </div>
  );
}

export function ResetPasswordForm({ token }: Readonly<{ token: string }>) {
  const [pending, setPending] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const password = String(form.get("new_password") ?? "");
    const confirmation = String(form.get("confirmation") ?? "");
    if (password !== confirmation) {
      setError(new Error("两次输入的密码不一致。"));
      setPending(false);
      return;
    }
    try {
      await apiFetch<void>("/auth/password-resets/confirm", {
        method: "POST",
        body: JSON.stringify({ token, new_password: password }),
      });
      setComplete(true);
    } catch (nextError) {
      setError(nextError);
    } finally {
      setPending(false);
    }
  }

  if (complete) {
    return (
      <div className="space-y-5">
        <FormMessage tone="success">
          密码已更新，原有登录设备均已退出。
        </FormMessage>
        <Link className={buttonClassName + " inline-flex items-center"} href="/login">
          使用新密码登录
        </Link>
      </div>
    );
  }

  return (
    <form className="space-y-6" onSubmit={submit}>
      <Field
        autoComplete="new-password"
        error={fieldMessage(error, "new_password")}
        hint="8～128 个字符，不能包含邮箱名或学号。"
        label="新密码"
        minLength={8}
        name="new_password"
        required
        type="password"
      />
      <Field
        autoComplete="new-password"
        label="再次输入新密码"
        minLength={8}
        name="confirmation"
        required
        type="password"
      />
      {error ? <FormMessage>{errorMessage(error)}</FormMessage> : null}
      <button
        className={buttonClassName + " w-full"}
        disabled={pending}
        type="submit"
      >
        {pending ? "正在更新密码…" : "更新密码并退出其他设备"}
      </button>
    </form>
  );
}
