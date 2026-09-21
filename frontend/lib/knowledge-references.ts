import type { KnowledgeDocumentSummary } from "@/lib/api/types";

export function escapeMarkdownLinkLabel(value: string): string {
  return value.replaceAll("\\", "\\\\").replaceAll("[", "\\[").replaceAll("]", "\\]");
}

export function knowledgeDocumentReference(
  document: Pick<KnowledgeDocumentSummary, "title" | "source_token">,
): string {
  return `[${escapeMarkdownLinkLabel(document.title)}](/knowledge?source=${encodeURIComponent(document.source_token)})`;
}

export function insertMarkdownAtSelection(
  value: string,
  insertion: string,
  start: number,
  end = start,
): { value: string; cursor: number } {
  const safeStart = Math.max(0, Math.min(start, value.length));
  const safeEnd = Math.max(safeStart, Math.min(end, value.length));
  const separatorBefore =
    safeStart > 0 && value[safeStart - 1] !== "\n" ? "\n\n" : "";
  const separatorAfter =
    safeEnd < value.length && value[safeEnd] !== "\n" ? "\n\n" : "";
  const nextValue =
    value.slice(0, safeStart) +
    separatorBefore +
    insertion +
    separatorAfter +
    value.slice(safeEnd);
  return {
    value: nextValue,
    cursor: safeStart + separatorBefore.length + insertion.length,
  };
}
