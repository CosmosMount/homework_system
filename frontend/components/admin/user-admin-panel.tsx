"use client";

import Link from "next/link";
import { type FormEvent, useMemo, useState } from "react";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { AdminUser, Direction, UserStatus } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

const accountStatusPresentation: Record<
  UserStatus,
  { label: string; badgeClassName: string; dotClassName: string }
> = {
  active: {
    label: "正常",
    badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-800",
    dotClassName: "bg-emerald-500",
  },
  pending_email: {
    label: "待验证",
    badgeClassName: "border-amber-200 bg-amber-50 text-amber-800",
    dotClassName: "bg-amber-500",
  },
  disabled: {
    label: "已禁用",
    badgeClassName: "border-rose-200 bg-rose-50 text-rose-700",
    dotClassName: "bg-rose-500",
  },
};

function AccountStatusBadge({ status }: Readonly<{ status: UserStatus }>) {
  const presentation = accountStatusPresentation[status];
  return (
    <span
      aria-label={`账号状态：${presentation.label}`}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 font-medium ${presentation.badgeClassName}`}
    >
      <span
        aria-hidden="true"
        className={`size-1.5 rounded-full ${presentation.dotClassName}`}
      />
      {presentation.label}
    </span>
  );
}

function replaceUser(users: AdminUser[], nextUser: AdminUser): AdminUser[] {
  return users.map((user) => (user.id === nextUser.id ? nextUser : user));
}

export function UserAdminPanel({
  initialUsers,
  initialTotal,
  activity,
  directions,
}: Readonly<{
  initialUsers: AdminUser[];
  initialTotal: number;
  activity: "inactive" | null;
  directions: Direction[];
}>) {
  const [users, setUsers] = useState(initialUsers);
  const [total, setTotal] = useState(initialTotal);
  const [query, setQuery] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const visibleUsers = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return users;
    return users.filter((user) =>
      [
        user.full_name,
        user.email,
        user.student_number,
        user.role,
        user.role === "admin" ? "管理员" : "学生",
        user.status,
        accountStatusPresentation[user.status].label,
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalized),
    );
  }, [query, users]);

  async function run(
    user: AdminUser,
    path: string,
    body: Record<string, unknown>,
    method = "POST",
  ) {
    setPendingId(user.id);
    setMessage(null);
    setError(null);
    try {
      const updated = await csrfFetch<AdminUser>(path, {
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
    user: AdminUser,
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
    user: AdminUser,
  ) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const reason = String(data.get("reason") ?? "").trim();
    const submitter = (event.nativeEvent as SubmitEvent).submitter;
    const intent = submitter?.getAttribute("value") ?? "";
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
    } else if (intent === "delete" && user.is_inactive) {
      const confirmed = window.confirm(
        "永久删除 " +
          user.full_name +
          "（" +
          user.email +
          "）后只能通过备份恢复。系统不会删除必须保留的正式业务数据；如存在此类数据，操作会被拒绝。确认继续？",
      );
      if (!confirmed) return;
      setPendingId(user.id);
      setMessage(null);
      setError(null);
      try {
        await csrfFetch<void>("/admin/users/" + user.id, {
          method: "DELETE",
          body: JSON.stringify({ reason }),
        });
        setUsers((current) => current.filter((item) => item.id !== user.id));
        setTotal((current) => Math.max(0, current - 1));
        setMessage("已永久删除账号 " + user.full_name + "。");
      } catch (nextError) {
        setError(
          nextError instanceof ApiError
            ? nextError.message
            : "永久删除失败，请稍后重试。",
        );
      } finally {
        setPendingId(null);
      }
    }
  }

  return (
    <div className="mt-8">
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
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
        <nav aria-label="账号活跃度筛选" className="flex flex-wrap gap-2">
          <Link
            aria-current={activity === null ? "page" : undefined}
            className="min-h-11 border border-[var(--color-border-strong)] px-4 py-2 text-sm"
            href="/admin/users"
          >
            全部账号
          </Link>
          <Link
            aria-current={activity === "inactive" ? "page" : undefined}
            className="min-h-11 border border-[var(--color-warning)] px-4 py-2 text-sm"
            href="/admin/users?activity=inactive"
          >
            超过 10 天未进入
          </Link>
        </nav>
      </div>
      <div className="mt-5 space-y-3">
        {message ? <FormMessage tone="success">{message}</FormMessage> : null}
        {error ? <FormMessage>{error}</FormMessage> : null}
      </div>
      <p className="mt-5 text-sm text-[var(--color-text-muted)]">
        显示 {visibleUsers.length} / {total} 个账号
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
              <div className="flex flex-wrap items-center justify-end gap-2 text-xs">
                <span
                  className={
                    user.role === "admin"
                      ? "inline-flex whitespace-nowrap rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 font-medium text-blue-800"
                      : "inline-flex whitespace-nowrap rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 font-medium text-slate-700"
                  }
                >
                  {user.role === "admin" ? "管理员" : "学生"}
                </span>
                <AccountStatusBadge status={user.status} />
                {user.is_inactive ? (
                  <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 font-medium text-amber-900">
                    <svg
                      aria-hidden="true"
                      className="size-3.5"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        cx="12"
                        cy="12"
                        r="8"
                        stroke="currentColor"
                        strokeWidth="1.8"
                      />
                      <path
                        d="M12 7.5v5l3 1.75"
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.8"
                      />
                    </svg>
                    {user.inactive_days} 天未登录
                  </span>
                ) : null}
              </div>
            </div>
            <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-[var(--color-text-muted)]">方向</dt>
                <dd>{user.direction?.name ?? "未设置"}</dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">最近进入系统</dt>
                <dd>
                  {user.last_active_at ? (
                    <time dateTime={user.last_active_at}>
                      {formatDateTime(user.last_active_at)}
                    </time>
                  ) : (
                    "从未进入系统"
                  )}
                </dd>
              </div>
            </dl>
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
                    {user.is_inactive ? (
                      <button
                        className="min-h-11 border border-[var(--color-danger)] px-5 text-[var(--color-danger)] disabled:opacity-50"
                        disabled={pendingId === user.id}
                        name="intent"
                        type="submit"
                        value="delete"
                      >
                        永久删除账号
                      </button>
                    ) : null}
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    邮箱、角色或禁用状态变更会立即撤销该用户 Session；系统拒绝禁用或降级最后一个激活管理员。
                  </p>
                  {user.is_inactive ? (
                    <p className="text-xs text-[var(--color-danger)]">
                      永久删除不可撤销且必须填写原因；当前账号、最后一名激活管理员或仍有关联正式业务数据的账号会被服务端拒绝。
                    </p>
                  ) : null}
                </form>
              </div>
            </details>
          </article>
        ))}
        {visibleUsers.length === 0 ? (
          <p className="border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
            没有符合当前筛选条件的账号。
          </p>
        ) : null}
      </div>
    </div>
  );
}
