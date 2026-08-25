"use client";

import { type FormEvent, useState } from "react";

import { buttonClassName, FormMessage, inputClassName } from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

export function ProfileEditor({ initialUser }: Readonly<{ initialUser: User }>) {
  const [user, setUser] = useState(initialUser);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const fullName = String(data.get("full_name") ?? "").trim();
    const studentNumber = String(data.get("student_number") ?? "").trim();
    const email = String(data.get("email") ?? "").trim();
    const patch: Record<string, unknown> = { revision: user.revision };
    if (fullName !== user.full_name) patch.full_name = fullName;
    if (studentNumber !== user.student_number) patch.student_number = studentNumber;
    if (email.toLowerCase() !== user.email.toLowerCase()) patch.email = email;
    if (Object.keys(patch).length === 1) {
      setMessage("没有需要保存的变更。");
      setError(null);
      return;
    }

    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await csrfFetch<User>("/admin/users/" + user.id, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setUser(updated);
      setMessage(
        updated.status === "pending_email"
          ? "邮箱已更新。当前会话已撤销，请完成新邮箱验证后重新登录。"
          : "个人资料已保存。",
      );
    } catch (nextError) {
      setError(nextError instanceof ApiError ? nextError.message : "保存失败，请稍后重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="mt-8 max-w-2xl space-y-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6" onSubmit={save}>
      <h2 className="text-xl font-semibold">编辑个人资料</h2>
      {message ? <FormMessage tone="success">{message}</FormMessage> : null}
      {error ? <FormMessage>{error}</FormMessage> : null}
      <label className="block text-sm font-medium">
        真实姓名
        <input className={inputClassName} defaultValue={user.full_name} name="full_name" required />
      </label>
      <label className="block text-sm font-medium">
        学号
        <input className={inputClassName} defaultValue={user.student_number} name="student_number" required />
      </label>
      <label className="block text-sm font-medium">
        校园邮箱
        <input className={inputClassName} defaultValue={user.email} name="email" required type="email" />
      </label>
      <p className="text-xs text-[var(--color-text-muted)]">
        修改邮箱会立即撤销当前登录，并向新校园邮箱发送验证邮件。
      </p>
      <button className={buttonClassName} disabled={pending} type="submit">
        {pending ? "保存中…" : "保存个人资料"}
      </button>
    </form>
  );
}
