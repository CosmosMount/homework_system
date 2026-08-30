"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import {
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, clearCsrfToken, csrfFetch } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

export function AccountDeletion({
  user,
}: Readonly<{
  user: Pick<User, "email" | "full_name">;
}>) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const currentPassword = String(data.get("current_password") ?? "");
    const confirmationEmail = String(data.get("confirmation_email") ?? "").trim();
    if (confirmationEmail.toLowerCase() !== user.email.toLowerCase()) {
      setError("确认邮箱必须与当前账号邮箱完全一致。");
      return;
    }

    setPending(true);
    setError(null);
    try {
      await csrfFetch<void>("/auth/account", {
        method: "DELETE",
        body: JSON.stringify({
          current_password: currentPassword,
          confirmation_email: confirmationEmail,
        }),
      });
      clearCsrfToken();
      router.replace("/login?account_deleted=1");
      router.refresh();
    } catch (nextError) {
      setError(
        nextError instanceof ApiError
          ? nextError.message
          : "账号注销失败，请稍后重试。",
      );
      const passwordInput = form.elements.namedItem("current_password");
      if (passwordInput instanceof HTMLInputElement) passwordInput.value = "";
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mt-8 max-w-2xl border border-[var(--color-danger)] bg-[var(--color-surface)] p-5 sm:p-6">
      <h2 className="text-xl font-semibold text-[var(--color-danger)]">
        注销账号
      </h2>
      <p className="mt-3 text-sm text-[var(--color-text-secondary)]">
        注销会立即物理删除账号、全部登录状态及个人作业提交、问卷回答、反馈答疑和个人文件。平台共享记录与团队赛事作品会保留并去除你的账号归属，对象存储随后由可靠任务清理。
      </p>
      <p className="mt-2 text-xs text-[var(--color-text-muted)]">
        此操作不可撤销；备份保留期内仍可能存在历史副本。管理员账号也受最后一名激活管理员保护。
      </p>
      {error ? (
        <div className="mt-4">
          <FormMessage>{error}</FormMessage>
        </div>
      ) : null}
      <form className="mt-5 space-y-4" onSubmit={submit}>
        <label className="block text-sm font-medium">
          当前密码
          <input
            autoComplete="current-password"
            className={inputClassName}
            maxLength={128}
            name="current_password"
            required
            type="password"
          />
        </label>
        <label className="block text-sm font-medium">
          输入当前账号邮箱以确认
          <input
            autoComplete="off"
            className={inputClassName}
            name="confirmation_email"
            placeholder={user.email}
            required
            spellCheck={false}
            type="email"
          />
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input
            className="mt-1"
            name="understood"
            required
            type="checkbox"
          />
          <span>
            我理解注销会直接删除 {user.full_name} 的账号与个人数据，且不能通过界面恢复。
          </span>
        </label>
        <button
          className="min-h-11 border border-[var(--color-danger)] px-5 text-[var(--color-danger)] disabled:opacity-50"
          disabled={pending}
          type="submit"
        >
          {pending ? "正在注销…" : "永久注销我的账号"}
        </button>
      </form>
    </section>
  );
}
