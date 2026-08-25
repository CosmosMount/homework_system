export function SafeHtml({
  sanitizedHtml,
}: Readonly<{ sanitizedHtml: string }>) {
  return (
    <div
      className="safe-rich-text"
      // 此属性只接受后端 Markdown 允许列表清洗后返回的 body_html。
      dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
    />
  );
}

export function MarkdownPreview({
  sanitizedHtml,
  emptyMessage = "保存后会在这里显示渲染结果。",
}: Readonly<{
  sanitizedHtml: string | null;
  emptyMessage?: string;
}>) {
  return (
    <section
      aria-label="Markdown 渲染预览"
      className="mt-4 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] shadow-[var(--shadow-soft)]"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-hover)] px-4 py-3">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Markdown 渲染预览
        </h3>
        <span className="font-mono text-[0.65rem] uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
          已清洗 HTML
        </span>
      </div>
      <div className="p-4 sm:p-5">
        {sanitizedHtml ? (
          <SafeHtml sanitizedHtml={sanitizedHtml} />
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">{emptyMessage}</p>
        )}
      </div>
    </section>
  );
}
