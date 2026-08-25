"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { inputClassName } from "@/components/ui/form-controls";
import type {
  AnnouncementAdmin,
  AnnouncementStatus,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

const statusLabels: Record<AnnouncementStatus, string> = {
  draft: "草稿",
  scheduled: "定时",
  published: "已发布",
  archived: "已归档",
};

export function AnnouncementListPanel({
  initialAnnouncements,
}: Readonly<{ initialAnnouncements: AnnouncementAdmin[] }>) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<AnnouncementStatus | "all">("all");
  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return initialAnnouncements.filter((announcement) => {
      const statusMatches = status === "all" || announcement.status === status;
      const queryMatches =
        !normalized ||
        (announcement.title + " " + announcement.summary)
          .toLowerCase()
          .includes(normalized);
      return statusMatches && queryMatches;
    });
  }, [initialAnnouncements, query, status]);

  return (
    <div className="mt-8">
      <div className="grid gap-4 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 md:grid-cols-[minmax(0,1fr)_14rem]">
        <label className="text-sm font-medium">
          搜索通知
          <input
            className={inputClassName}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="标题或摘要"
            type="search"
            value={query}
          />
        </label>
        <label className="text-sm font-medium">
          状态
          <select
            className={inputClassName}
            onChange={(event) =>
              setStatus(event.target.value as AnnouncementStatus | "all")
            }
            value={status}
          >
            <option value="all">全部状态</option>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="mt-5 text-sm text-[var(--color-text-muted)]">
        显示 {visible.length} / {initialAnnouncements.length} 条通知
      </p>
      <div className="mt-4 space-y-3">
        {visible.map((announcement) => (
          <article
            className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
            key={announcement.id}
          >
            <div className="flex flex-wrap items-start justify-between gap-5">
              <div className="min-w-0">
                <div className="flex flex-wrap gap-2 font-mono text-xs">
                  <span className="border border-[var(--color-border-strong)] px-2 py-0.5">
                    {statusLabels[announcement.status]}
                  </span>
                  {announcement.send_email ? (
                    <span className="border border-[var(--color-info)] px-2 py-0.5 text-[var(--color-info)]">
                      邮件
                    </span>
                  ) : null}
                </div>
                <h2 className="mt-3 text-xl font-medium">{announcement.title}</h2>
                <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                  {announcement.summary}
                </p>
              </div>
              <Link
                className="min-h-10 border border-[var(--color-border-strong)] px-4 py-1.5 text-sm"
                href={"/admin/announcements/" + announcement.id + "/edit"}
              >
                查看与编辑
              </Link>
            </div>
            <dl className="mt-5 grid gap-4 border-t border-[var(--color-border)] pt-4 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-[var(--color-text-muted)]">预计 / 实际接收</dt>
                <dd className="mt-1">
                  {announcement.estimated_recipient_count} /{" "}
                  {announcement.actual_recipient_count}
                </dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">计划时间</dt>
                <dd className="mt-1">{formatDateTime(announcement.publish_at)}</dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">最后更新</dt>
                <dd className="mt-1">{formatDateTime(announcement.updated_at)}</dd>
              </div>
            </dl>
          </article>
        ))}
        {visible.length === 0 ? (
          <p className="border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
            没有符合筛选条件的通知。
          </p>
        ) : null}
      </div>
    </div>
  );
}
