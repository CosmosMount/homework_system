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

export function RenderedMarkdown({
  sanitizedHtml,
  emptyMessage = "保存后可查看内容。",
}: Readonly<{
  sanitizedHtml: string | null;
  emptyMessage?: string;
}>) {
  return sanitizedHtml ? (
    <SafeHtml sanitizedHtml={sanitizedHtml} />
  ) : (
    <p className="text-sm text-[var(--color-text-muted)]">{emptyMessage}</p>
  );
}
