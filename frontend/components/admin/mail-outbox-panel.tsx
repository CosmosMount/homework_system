"use client";

import { useMemo, useState } from "react";

import { FormMessage, inputClassName } from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { OutboxJob } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

export function MailOutboxPanel({
  initialJobs,
}: Readonly<{ initialJobs: OutboxJob[] }>) {
  const [jobs, setJobs] = useState(initialJobs);
  const [status, setStatus] = useState("all");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const visible = useMemo(
    () => jobs.filter((job) => status === "all" || job.status === status),
    [jobs, status],
  );

  async function retry(job: OutboxJob) {
    setPendingId(job.id);
    setMessage(null);
    try {
      const updated = await csrfFetch<OutboxJob>(
        "/admin/mail-outbox/" + job.id + "/retry",
        { method: "POST" },
      );
      setJobs((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setMessage("任务已经重新进入发送队列。");
    } catch (error) {
      setMessage(
        error instanceof ApiError ? error.message : "重试失败，请稍后再试。",
      );
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="mt-8">
      <label className="block max-w-xs text-sm font-medium">
        任务状态
        <select
          className={inputClassName}
          onChange={(event) => setStatus(event.target.value)}
          value={status}
        >
          <option value="all">全部状态</option>
          <option value="pending">等待</option>
          <option value="processing">处理中</option>
          <option value="retry">待重试</option>
          <option value="sent">已发送</option>
          <option value="dead">已停止</option>
        </select>
      </label>
      {message ? (
        <div className="mt-4">
          <FormMessage tone="info">{message}</FormMessage>
        </div>
      ) : null}
      <div className="mt-5 overflow-x-auto border border-[var(--color-border)]">
        <table className="w-full min-w-[58rem] border-collapse text-left text-sm">
          <thead className="bg-[var(--color-surface-raised)] text-[var(--color-text-muted)]">
            <tr>
              <th className="p-3 font-medium">类型 / 收件人</th>
              <th className="p-3 font-medium">状态</th>
              <th className="p-3 font-medium">尝试</th>
              <th className="p-3 font-medium">可用时间</th>
              <th className="p-3 font-medium">脱敏错误</th>
              <th className="p-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((job) => (
              <tr className="border-t border-[var(--color-border)]" key={job.id}>
                <td className="p-3">
                  <p>{job.job_type}</p>
                  <p className="font-mono text-xs text-[var(--color-text-muted)]">
                    {job.recipient_masked}
                  </p>
                </td>
                <td className="p-3 font-mono text-xs">{job.status}</td>
                <td className="p-3">
                  {job.attempt_count} / {job.max_attempts}
                </td>
                <td className="p-3">{formatDateTime(job.available_at)}</td>
                <td className="max-w-sm p-3 text-xs text-[var(--color-text-muted)]">
                  {job.last_error_code ?? "—"}
                  {job.last_error_summary ? " · " + job.last_error_summary : ""}
                </td>
                <td className="p-3">
                  {job.status === "dead" ? (
                    <button
                      className="min-h-10 border border-[var(--color-border-strong)] px-3 disabled:opacity-55"
                      disabled={pendingId === job.id}
                      onClick={() => retry(job)}
                      type="button"
                    >
                      人工重试
                    </button>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
