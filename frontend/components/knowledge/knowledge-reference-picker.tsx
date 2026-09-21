"use client";

import { useMemo, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api/client";
import { knowledgeDocumentReference } from "@/lib/knowledge-references";
import type { KnowledgeOverview } from "@/lib/api/types";

export function KnowledgeReferencePicker({
  disabled = false,
  onInsert,
}: Readonly<{
  disabled?: boolean;
  onInsert: (markdown: string) => void;
}>) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [overview, setOverview] = useState<KnowledgeOverview | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (overview !== null || pending) return;
    setPending(true);
    setError(null);
    try {
      setOverview(await apiFetch<KnowledgeOverview>("/knowledge"));
    } catch (nextError) {
      setError(
        nextError instanceof ApiError
          ? nextError.message
          : "知识库读取失败，请稍后重试。",
      );
    } finally {
      setPending(false);
    }
  }

  const documents = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("zh-CN");
    return (overview?.documents ?? []).filter((document) =>
      normalized
        ? document.title.toLocaleLowerCase("zh-CN").includes(normalized)
        : true,
    );
  }, [overview, query]);

  return (
    <div className="mt-2">
      <button
        className="text-xs font-medium text-[var(--color-accent-hover)] underline underline-offset-4 disabled:opacity-50"
        disabled={disabled || pending}
        onClick={toggle}
        type="button"
      >
        {pending ? "读取知识库…" : open ? "收起知识库文档" : "引用知识库文档"}
      </button>
      {open ? (
        <div
          aria-label="选择知识库文档"
          className="mt-3 space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3"
          role="dialog"
        >
          <input
            aria-label="搜索知识库文档"
            className="min-h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="按标题搜索"
            value={query}
          />
          {error ? <p className="text-xs text-[var(--color-danger)]">{error}</p> : null}
          {!error && overview?.snapshot === null ? (
            <p className="text-xs text-[var(--color-text-muted)]">暂无成功的知识库快照。</p>
          ) : null}
          {!error && overview?.snapshot !== null && documents.length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)]">没有匹配的文档。</p>
          ) : null}
          {documents.length > 0 ? (
            <div className="max-h-52 space-y-1 overflow-y-auto" role="list">
              {documents.map((document) => (
                <button
                  className="block w-full rounded-lg px-3 py-2 text-left text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
                  key={document.id}
                  onClick={() => {
                    onInsert(knowledgeDocumentReference(document));
                    setOpen(false);
                  }}
                  type="button"
                >
                  {document.title}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
