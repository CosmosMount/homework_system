"use client";

import { useMemo, useState } from "react";

import { inputClassName } from "@/components/ui/form-controls";
import type { AuditLog } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

export function AuditLogPanel({
  initialLogs,
}: Readonly<{ initialLogs: AuditLog[] }>) {
  const [query, setQuery] = useState("");
  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return initialLogs;
    return initialLogs.filter((entry) =>
      [
        entry.action,
        entry.target_type,
        entry.target_id,
        entry.request_id,
        entry.result,
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalized),
    );
  }, [initialLogs, query]);

  return (
    <div className="mt-8">
      <label className="block max-w-xl text-sm font-medium">
        筛选审计记录
        <input
          className={inputClassName}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="动作、目标、request ID 或结果"
          type="search"
          value={query}
        />
      </label>
      <div className="mt-5 space-y-3">
        {visible.map((entry) => (
          <details
            className="border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
            key={entry.id}
          >
            <summary className="cursor-pointer list-none">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="font-medium">{entry.action}</p>
                  <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                    {entry.target_type} / {entry.target_id}
                  </p>
                </div>
                <div className="text-right text-xs text-[var(--color-text-muted)]">
                  <p>{formatDateTime(entry.created_at)}</p>
                  <p className="mt-1">{entry.result}</p>
                </div>
              </div>
            </summary>
            <dl className="mt-4 grid gap-3 border-t border-[var(--color-border)] pt-4 text-xs md:grid-cols-2">
              <div>
                <dt className="text-[var(--color-text-muted)]">操作者</dt>
                <dd className="mt-1 font-mono">{entry.actor_user_id ?? "system"}</dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">请求</dt>
                <dd className="mt-1 font-mono">{entry.request_id}</dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">来源网段</dt>
                <dd className="mt-1 font-mono">{entry.ip_prefix}</dd>
              </div>
            </dl>
            <pre className="mt-4 overflow-x-auto border border-[var(--color-border)] bg-[var(--color-bg)] p-3 text-xs text-[var(--color-text-secondary)]">
              {JSON.stringify(entry.change_summary, null, 2)}
            </pre>
          </details>
        ))}
      </div>
    </div>
  );
}
