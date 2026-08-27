const DOCUMENT_MARKERS = new Set(["wiki", "docx", "document", "docs"]);

export function feishuDocumentToken(value: string | null | undefined): string | null {
  if (!value) return null;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return null;
  }
  const hostname = parsed.hostname.toLowerCase();
  const isFeishuHost =
    hostname === "feishu.cn" ||
    hostname.endsWith(".feishu.cn") ||
    hostname === "larksuite.com" ||
    hostname.endsWith(".larksuite.com");
  if (!isFeishuHost) return null;
  const segments = parsed.pathname.split("/").filter(Boolean);
  const markerIndex = segments.findIndex((segment) =>
    DOCUMENT_MARKERS.has(segment.toLowerCase()),
  );
  const rawToken = markerIndex >= 0 ? segments[markerIndex + 1] : undefined;
  if (!rawToken || rawToken.toLowerCase() === "space") return null;
  try {
    return decodeURIComponent(rawToken);
  } catch {
    return rawToken;
  }
}
