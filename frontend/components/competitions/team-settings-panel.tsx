"use client";

import { useState } from "react";

import { buttonClassName, FormMessage } from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { TeamSettings } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

export function TeamSettingsPanel({ initialSettings }: Readonly<{ initialSettings: TeamSettings }>) {
  const [settings, setSettings] = useState(initialSettings);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(field: "is_team_open" | "is_direction_change_open") {
    const nextOpen = !settings[field];
    const action = nextOpen ? "开放" : "关闭";
    const label = field === "is_team_open" ? "学生组队" : "学生自助修改技术方向";
    if (!window.confirm(`确认${action}${label}？`)) return;
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await csrfFetch<TeamSettings>("/admin/team-settings", {
        method: "PATCH",
        body: JSON.stringify({
          [field]: nextOpen,
          revision: settings.revision,
        }),
      });
      setSettings(updated);
      setMessage(field === "is_team_open"
        ? (nextOpen ? "已向学生开放组队。" : "已关闭学生组队；个人简介仍可填写和浏览。")
        : `已${action}学生自助修改技术方向。`);
    } catch (nextError) {
      setError(nextError instanceof ApiError ? nextError.message : "保存失败，请稍后重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mb-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
      <p className="text-xs font-medium tracking-[0.14em] text-[var(--color-text-muted)]">
        STUDENT TEAM ACCESS
      </p>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">学生组队开关</h2>
          <p className="mt-2 max-w-3xl text-sm text-[var(--color-text-secondary)]">
            {settings.is_team_open
              ? "当前已开放：学生可创建、加入、邀请、调整和解散队伍。"
              : "当前未开放：学生仍可填写个人简介、查看他人简介和按技术组筛选，但不能进行任何组队操作。"}
          </p>
          <p className="mt-2 font-mono text-xs text-[var(--color-text-muted)]">
            更新于 {formatDateTime(settings.updated_at)} · revision {settings.revision}
          </p>
        </div>
        <button className={buttonClassName} disabled={pending} onClick={() => save("is_team_open")} type="button">
          {pending ? "保存中…" : settings.is_team_open ? "关闭学生组队" : "开放学生组队"}
        </button>
      </div>
      <div className="mt-6 flex flex-wrap items-start justify-between gap-4 border-t border-[var(--color-border)] pt-5">
        <div>
          <h2 className="text-xl font-semibold">学生自助修改方向开关</h2>
          <p className="mt-2 max-w-3xl text-sm text-[var(--color-text-secondary)]">
            {settings.is_direction_change_open ? "当前已开放：学生可在个人资料选择启用中的技术方向。" : "当前已关闭：学生不能自行修改技术方向。"}
            此权限独立于组队开关；管理员仍可调整方向，所有改组均校验队伍名额。
          </p>
        </div>
        <button className={buttonClassName} disabled={pending} onClick={() => save("is_direction_change_open")} type="button">
          {settings.is_direction_change_open ? "关闭学生修改方向" : "开放学生修改方向"}
        </button>
      </div>
      {message ? <div className="mt-4"><FormMessage tone="success">{message}</FormMessage></div> : null}
      {error ? <div className="mt-4"><FormMessage>{error}</FormMessage></div> : null}
    </section>
  );
}
