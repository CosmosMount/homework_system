"use client";

import { type FormEvent, useMemo, useState } from "react";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { Direction, User } from "@/lib/api/types";

function replaceUser(users: User[], nextUser: User): User[] {
  return users.map((user) => (user.id === nextUser.id ? nextUser : user));
}

export function UserAdminPanel({
  initialUsers,
  directions,
}: Readonly<{
  initialUsers: User[];
  directions: Direction[];
}>) {
  const [users, setUsers] = useState(initialUsers);
  const [query, setQuery] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const visibleUsers = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return users;
    return users.filter((user) =>
      [user.full_name, user.email, user.student_number, user.role, user.status]
        .join(" ")
        .toLowerCase()
        .includes(normalized),
    );
  }, [query, users]);

  async function run(
    user: User,
    path: string,
    body: Record<string, unknown>,
    method = "POST",
  ) {
    setPendingId(user.id);
    setMessage(null);
    setError(null);
    try {
      const updated = await csrfFetch<User>(path, {
        method,
        body: JSON.stringify(body),
      });
      setUsers((current) => replaceUser(current, updated));
      setMessage("用户资料已更新。");
    } catch (nextError) {
      setError(
        nextError instanceof ApiError
          ? nextError.message
          : "操作失败，请稍后重试。",
      );
    } finally {
      setPendingId(null);
    }
  }

  async function submitProfile(
    event: FormEvent<HTMLFormElement>,
    user: User,
  ) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const patch: Record<string, unknown> = { revision: user.revision };
    const fullName = String(data.get("full_name") ?? "").trim();
    const studentNumber = String(data.get("student_number") ?? "").trim();
    const email = String(data.get("email") ?? "").trim();
    const directionId = String(data.get("direction_id") ?? "");
    if (fullName !== user.full_name) patch.full_name = fullName;
    if (studentNumber !== user.student_number) {
      patch.student_number = studentNumber;
    }
    if (email.toLowerCase() !== user.email.toLowerCase()) patch.email = email;
    if (directionId !== (user.direction?.id ?? "")) {
      patch.direction_id = directionId || null;
    }
    if (Object.keys(patch).length === 1) {
      setMessage("没有需要保存的变更。");
      return;
    }
    await run(user, "/admin/users/" + user.id, patch, "PATCH");
  }

  async function submitRiskAction(
    event: FormEvent<HTMLFormElement>,
    user: User,
  ) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const reason = String(data.get("reason") ?? "").trim();
    const intent = String(data.get("intent") ?? "");
    if (reason.length < 3) {
      setError("高风险操作原因至少需要 3 个字符。");
      return;
    }
    if (intent === "disable") {
      await run(user, "/admin/users/" + user.id + "/disable", { reason });
    } else if (intent === "restore") {
      await run(user, "/admin/users/" + user.id + "/restore", { reason });
    } else if (intent === "role") {
      await run(user, "/admin/users/" + user.id + "/role", {
        role: user.role === "admin" ? "student" : "admin",
        reason,
      });
    }
  }

  return (
    <div className="mt-8">
      <label className="block max-w-xl text-sm font-medium" htmlFor="user-search">
        搜索用户
        <input
          className={inputClassName}
          id="user-search"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="姓名、邮箱、学号、角色或状态"
          type="search"
          value={query}
        />
      </label>
      <div className="mt-5 space-y-3">
        {message ? <FormMessage tone="success">{message}</FormMessage> : null}
        {error ? <FormMessage>{error}</FormMessage> : null}
      </div>
      <p className="mt-5 text-sm text-[var(--color-text-muted)]">
        显示 {visibleUsers.length} / {users.length} 个账号
      </p>
      <div className="mt-4 space-y-4">
        {visibleUsers.map((user) => (
          <article
            className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
            key={user.id}
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-medium">{user.full_name}</h2>
                <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
                  {user.student_number} · {user.email}
                </p>
              </div>
              <div className="flex gap-2 text-xs">
                <span className="border border-[var(--color-border-strong)] px-2 py-1">
                  {user.role === "admin" ? "管理员" : "学生"}
                </span>
                <span
                  className={
                    user.status === "active"
                      ? "bg-[var(--color-success)] px-2 py-1 text-black"
                      : "bg-[var(--color-warning)] px-2 py-1 text-black"
                  }
                >
                  {user.status}
                </span>
              </div>
            </div>
            <div className="mt-5 text-sm">
              <span className="text-[var(--color-text-muted)]">方向：</span>
              {user.direction?.name ?? "未设置"}
            </div>
            <details className="mt-5 border-t border-[var(--color-border)] pt-4">
              <summary className="cursor-pointer font-medium">编辑与高风险操作</summary>
              <div className="mt-5 grid gap-6 xl:grid-cols-2">
                <form
                  className="grid gap-4"
                  onSubmit={(event) => submitProfile(event, user)}
                >
                  <label className="text-sm">
                    姓名
                    <input
                      className={inputClassName}
                      defaultValue={user.full_name}
                      name="full_name"
                      required
                    />
                  </label>
                  <label className="text-sm">
                    学号
                    <input
                      className={inputClassName}
                      defaultValue={user.student_number}
                      name="student_number"
                      required
                    />
                  </label>
                  <label className="text-sm">
                    校园邮箱
                    <input
                      className={inputClassName}
                      defaultValue={user.email}
                      name="email"
                      required
                      type="email"
                    />
                  </label>
                  <label className="text-sm">
                    方向
                    <select
                      className={inputClassName}
                      defaultValue={user.direction?.id ?? ""}
                      name="direction_id"
                    >
                      <option value="">未设置</option>
                      {directions.map((direction) => (
                        <option key={direction.id} value={direction.id}>
                          {direction.name}
                          {direction.is_active ? "" : "（停用）"}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className={buttonClassName}
                    disabled={pendingId === user.id}
                    type="submit"
                  >
                    保存资料
                  </button>
                </form>
                <form
                  className="space-y-4 border-l-2 border-[var(--color-danger)] pl-4"
                  onSubmit={(event) => submitRiskAction(event, user)}
                >
                  <label className="block text-sm">
                    操作原因
                    <input
                      className={inputClassName}
                      minLength={3}
                      name="reason"
                      placeholder="原因将写入审计日志"
                      required
                    />
                  </label>
                  <div className="flex flex-wrap gap-3">
                    <button
                      className={buttonClassName}
                      disabled={pendingId === user.id}
                      name="intent"
                      type="submit"
                      value={user.status === "disabled" ? "restore" : "disable"}
                    >
                      {user.status === "disabled" ? "恢复账号" : "禁用账号"}
                    </button>
                    <button
                      className="min-h-11 border border-[var(--color-border-strong)] px-5 disabled:opacity-50"
                      disabled={pendingId === user.id}
                      name="intent"
                      type="submit"
                      value="role"
                    >
                      {user.role === "admin" ? "改为学生" : "设为管理员"}
                    </button>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    邮箱、角色或禁用状态变更会立即撤销该用户 Session；系统拒绝禁用或降级最后一个激活管理员。
                  </p>
                </form>
              </div>
            </details>
          </article>
        ))}
      </div>
    </div>
  );
}
