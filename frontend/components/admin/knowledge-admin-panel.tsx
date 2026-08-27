"use client";

import { useState } from "react";

import { ApiError, apiFetch, csrfFetch } from "@/lib/api/client";
import type {
  KnowledgeAdminStatus,
  KnowledgeSyncCreated,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

const statusLabels = {
  pending: "等待 Worker",
  running: "同步中",
  succeeded: "同步成功",
  failed: "同步失败",
} as const;

export function KnowledgeAdminPanel({
  initialStatus,
}: Readonly<{ initialStatus: KnowledgeAdminStatus }>) {
  const [status, setStatus] = useState(initialStatus);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function triggerSync() {
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const created = await csrfFetch<KnowledgeSyncCreated>(
        "/admin/knowledge/sync",
        { method: "POST" },
      );
      setStatus((current) => ({ ...current, latest_run: created.run }));
      setMessage("同步任务已提交给 Worker。学生继续读取当前成功快照。");
    } catch (nextError) {
      setError(
        nextError instanceof ApiError
          ? nextError.message
          : "无法创建同步任务，请稍后重试。",
      );
    } finally {
      setPending(false);
    }
  }

  async function refreshStatus() {
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      setStatus(await apiFetch<KnowledgeAdminStatus>("/admin/knowledge"));
      setMessage("同步状态已刷新。");
    } catch (nextError) {
      setError(
        nextError instanceof ApiError
          ? nextError.message
          : "无法刷新同步状态，请稍后重试。",
      );
    } finally {
      setPending(false);
    }
  }

  const active =
    status.latest_run?.status === "pending" ||
    status.latest_run?.status === "running";

  return (
    <div className="space-y-6">
      {message ? (
        <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-[var(--color-success)]" role="status">
          {message}
        </p>
      ) : null}
      {error ? (
        <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-[var(--color-danger)]" role="alert">
          {error}
        </p>
      ) : null}

      <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <p className="font-mono text-xs tracking-[0.14em] text-[var(--color-text-muted)]">
              FEISHU CONNECTOR
            </p>
            <h2 className="mt-2 text-xl font-semibold">飞书知识库同步</h2>
            <p className="mt-2 max-w-3xl text-sm text-[var(--color-text-secondary)]">
              Worker 异步读取飞书并生成全量只读快照。只有同步成功后，学生页面才会切换到新版本。
            </p>
          </div>
          <span
            className={
              "rounded-full px-3 py-1 text-xs " +
              (status.configured
                ? "bg-emerald-50 text-[var(--color-success)]"
                : "bg-amber-50 text-[var(--color-warning)]")
            }
          >
            {status.configured ? "已配置" : "未配置"}
          </span>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            className="inline-flex min-h-10 items-center rounded-lg border border-[var(--color-action-border)] bg-[var(--color-action-fill)] px-4 text-sm font-medium text-[var(--color-action-text)] shadow-[var(--shadow-button)] hover:bg-[var(--color-action-fill-hover)] disabled:cursor-not-allowed disabled:opacity-50"
            disabled={pending || active || !status.configured}
            onClick={triggerSync}
            type="button"
          >
            {active ? "同步进行中…" : pending ? "处理中…" : "立即同步"}
          </button>
          <button
            className="inline-flex min-h-10 items-center rounded-lg border border-[var(--color-border)] px-4 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
            disabled={pending}
            onClick={refreshStatus}
            type="button"
          >
            刷新状态
          </button>
        </div>
        {!status.configured ? (
          <p className="mt-4 text-sm text-[var(--color-warning)]">
            需要由部署管理员配置飞书应用凭证、知识空间 ID 和租户知识库地址；凭证不会保存到数据库。
          </p>
        ) : null}
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
          <h2 className="text-lg font-semibold">学生当前版本</h2>
          {status.current_snapshot ? (
            <dl className="mt-5 grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-[var(--color-text-muted)]">同步时间</dt>
                <dd className="mt-1 font-medium">
                  {formatDateTime(status.current_snapshot.synced_at)}
                </dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">文档</dt>
                <dd className="mt-1 font-medium">
                  {status.current_snapshot.document_count} 篇
                </dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">本地媒体</dt>
                <dd className="mt-1 font-medium">
                  {status.current_snapshot.asset_count} 项
                </dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">状态</dt>
                <dd className="mt-1 font-medium text-[var(--color-success)]">
                  可供学生阅读
                </dd>
              </div>
            </dl>
          ) : (
            <p className="mt-5 text-sm text-[var(--color-text-muted)]">
              尚无成功快照；学生页面会显示等待首次同步。
            </p>
          )}
        </section>

        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
          <h2 className="text-lg font-semibold">最近同步任务</h2>
          {status.latest_run ? (
            <div className="mt-5 space-y-3 text-sm">
              <div className="flex items-center justify-between gap-4">
                <span className="text-[var(--color-text-muted)]">状态</span>
                <span className="rounded-full bg-[var(--color-action-fill)] px-3 py-1 text-xs">
                  {statusLabels[status.latest_run.status]}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-[var(--color-text-muted)]">创建时间</span>
                <span>{formatDateTime(status.latest_run.created_at)}</span>
              </div>
              {status.latest_run.finished_at ? (
                <div className="flex items-center justify-between gap-4">
                  <span className="text-[var(--color-text-muted)]">完成时间</span>
                  <span>{formatDateTime(status.latest_run.finished_at)}</span>
                </div>
              ) : null}
              {status.latest_run.error_summary ? (
                <p className="rounded-xl bg-red-50 px-4 py-3 text-[var(--color-danger)]">
                  {status.latest_run.error_summary}
                  {status.latest_run.error_code
                    ? "（" + status.latest_run.error_code + "）"
                    : ""}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="mt-5 text-sm text-[var(--color-text-muted)]">
              还没有提交过同步任务。
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
