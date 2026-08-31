"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode, SVGProps } from "react";

import { KnowledgeBlocks } from "@/components/knowledge/knowledge-blocks";
import { ApiError, apiFetch } from "@/lib/api/client";
import { requestAppShellCollapse } from "@/lib/app-shell-events";
import type {
  KnowledgeBlock,
  KnowledgeDocument,
  KnowledgeNode,
  KnowledgeOverview,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { feishuDocumentToken } from "@/lib/knowledge-links";

type KnowledgeReaderProps = Readonly<{
  overview: KnowledgeOverview;
  initialDocument: KnowledgeDocument | null;
  allowFeishuSourceLinks?: boolean;
}>;

type TocItem = { id: string; label: string; level: number };
type IconName =
  | "chevron-down"
  | "chevron-right"
  | "chevrons-left"
  | "chevrons-right"
  | "download"
  | "file"
  | "folder"
  | "list"
  | "search"
  | "x";

function Icon({
  name,
  size = 18,
  ...props
}: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  let shape: ReactNode;
  switch (name) {
    case "chevron-down":
      shape = <path d="m6 9 6 6 6-6" />;
      break;
    case "download":
      shape = <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" /></>;
      break;
    case "chevron-right":
      shape = <path d="m9 18 6-6-6-6" />;
      break;
    case "chevrons-left":
      shape = <><path d="m11 17-5-5 5-5" /><path d="m18 17-5-5 5-5" /></>;
      break;
    case "chevrons-right":
      shape = <><path d="m13 17 5-5-5-5" /><path d="m6 17 5-5-5-5" /></>;
      break;
    case "file":
      shape = <><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5Z" /><polyline points="14 2 14 8 20 8" /><path d="M8 13h8M8 17h8" /></>;
      break;
    case "folder":
      shape = <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />;
      break;
    case "list":
      shape = <><path d="M8 6h13M8 12h13M8 18h13" /><path d="M3 6h.01M3 12h.01M3 18h.01" /></>;
      break;
    case "search":
      shape = <><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></>;
      break;
    case "x":
      shape = <path d="M18 6 6 18M6 6l12 12" />;
      break;
  }
  return <svg aria-hidden="true" fill="none" focusable="false" height={size} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width={size} {...props}>{shape}</svg>;
}

function textOf(block: KnowledgeBlock): string {
  return (block.segments ?? []).map((segment) => segment.text).join("").trim();
}

function collectToc(blocks: KnowledgeBlock[]): TocItem[] {
  const result: TocItem[] = [];
  function visit(items: KnowledgeBlock[]) {
    for (const block of items) {
      if (block.type === "heading" && textOf(block)) {
        result.push({ id: "kb-" + block.id, label: textOf(block), level: Math.max(1, Math.min(block.level ?? 2, 6)) });
      }
      if (block.children) visit(block.children);
      for (const row of block.rows ?? []) {
        for (const cell of row) visit(Array.isArray(cell) ? cell : cell.blocks);
      }
    }
  }
  visit(blocks);
  return result;
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "文档加载失败，请稍后重试。";
}

function assetUrl(assetId: string): string {
  return "/api/v1/knowledge/assets/" + encodeURIComponent(assetId) + "/content";
}

function formatFileSize(size: number | null): string {
  if (!size || size < 1) return "";
  if (size < 1024) return size + " B";
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
  return (size / 1024 / 1024).toFixed(1) + " MB";
}

function followedNodeIds(
  nodeById: ReadonlyMap<string, KnowledgeNode>,
  nodeByDocumentId: ReadonlyMap<string, KnowledgeNode>,
  documentId: string | undefined,
): Set<string> {
  const next = new Set<string>();
  const visited = new Set<string>();
  let node = documentId ? nodeByDocumentId.get(documentId) : undefined;
  while (node?.parent_id && !visited.has(node.parent_id)) {
    visited.add(node.parent_id);
    next.add(node.parent_id);
    node = nodeById.get(node.parent_id);
  }
  return next;
}

const directoryIconButtonClassName =
  "grid size-9 shrink-0 place-items-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] text-[var(--color-accent)] transition-all outline-none hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-accent-hover)] focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] active:translate-y-px";

const directoryHeaderClassName =
  "mb-3 flex items-center justify-between gap-3 border-b border-[var(--color-border)] pb-3";

function DocumentBody({ allowFeishuSourceLinks, document, onOpenDocument, tokenToDocument }: Readonly<{
  allowFeishuSourceLinks: boolean;
  document: KnowledgeDocument;
  onOpenDocument: (documentId: string) => void;
  tokenToDocument: ReadonlyMap<string, string>;
}>) {
  const [tocOpen, setTocOpen] = useState(true);
  const toc = useMemo(() => collectToc(document.blocks), [document.blocks]);
  const [activeTocId, setActiveTocId] = useState<string | null>(toc[0]?.id ?? null);

  useEffect(() => {
    function synchronizeActiveHeading() {
      if (toc.length === 0) {
        setActiveTocId(null);
        return;
      }
      let active = toc[0].id;
      for (const item of toc) {
        const heading = window.document.getElementById(item.id);
        if (!heading || heading.getBoundingClientRect().top > 144) break;
        active = item.id;
      }
      setActiveTocId(active);
    }

    const initialFrame = window.requestAnimationFrame(synchronizeActiveHeading);
    window.addEventListener("scroll", synchronizeActiveHeading, { passive: true });
    window.addEventListener("resize", synchronizeActiveHeading);
    return () => {
      window.cancelAnimationFrame(initialFrame);
      window.removeEventListener("scroll", synchronizeActiveHeading);
      window.removeEventListener("resize", synchronizeActiveHeading);
    };
  }, [document.id, toc]);
  return (
    <div className={"grid " + (tocOpen ? "gap-5 lg:grid-cols-[minmax(0,1fr)_180px] lg:gap-10" : "gap-0 lg:grid-cols-[minmax(0,1fr)_40px]")}>
      <div className="min-w-0 space-y-5 text-slate-700" data-testid="knowledge-document-content"><KnowledgeBlocks allowFeishuSourceLinks={allowFeishuSourceLinks} blocks={document.blocks} onOpenDocument={onOpenDocument} tokenToDocument={tokenToDocument} /></div>
      <aside className={"hidden lg:sticky lg:top-6 lg:block lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto " + (tocOpen ? "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 shadow-[var(--shadow-card)]" : "w-10")} data-testid="knowledge-page-toc">
        {tocOpen ? <>
          <div className={directoryHeaderClassName}>
            <span className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[0.16em] text-[var(--color-accent)]"><Icon name="list" size={15} />本文目录</span>
            <button aria-label="收起本文目录" className={directoryIconButtonClassName} onClick={() => setTocOpen(false)} title="收起本文目录" type="button"><Icon name="chevrons-right" /></button>
          </div>
          <nav aria-label="本文目录" className="space-y-1">
            {toc.map((item) => <a aria-current={item.id === activeTocId ? "location" : undefined} className={"block rounded-lg px-2 py-1.5 text-sm leading-6 transition " + (item.id === activeTocId ? "bg-[var(--color-surface-hover)] font-semibold text-[var(--color-accent-hover)]" : item.level > 1 ? "pl-5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-accent)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-accent)]")} href={"#" + item.id} key={item.id}>{item.label}</a>)}
          </nav>
        </> : <button aria-label="展开本文目录" className={directoryIconButtonClassName} onClick={() => setTocOpen(true)} title="展开本文目录" type="button"><Icon name="chevrons-left" /></button>}
      </aside>
    </div>
  );
}

export function KnowledgeReader({
  allowFeishuSourceLinks = false,
  overview,
  initialDocument,
}: KnowledgeReaderProps) {
  const [document, setDocument] = useState(initialDocument);
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mobileDirectoryOpen, setMobileDirectoryOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const documentDirectoryRef = useRef<HTMLElement>(null);

  const tokenToDocument = useMemo(() => {
    const result = new Map(
      overview.documents.map((item) => [item.source_token, item.id]),
    );
    for (const item of overview.documents) {
      const token = feishuDocumentToken(item.source_url);
      if (token) result.set(token, item.id);
    }
    for (const node of overview.nodes) {
      const token = feishuDocumentToken(node.source_url);
      if (token && node.document_id) result.set(token, node.document_id);
    }
    return result;
  }, [overview.documents, overview.nodes]);
  const nodeById = useMemo(() => new Map(overview.nodes.map((node) => [node.id, node])), [overview.nodes]);
  const nodeByDocumentId = useMemo(
    () => new Map(
      overview.nodes
        .filter((node): node is KnowledgeNode & { document_id: string } => Boolean(node.document_id))
        .map((node) => [node.document_id, node]),
    ),
    [overview.nodes],
  );
  const documentById = useMemo(() => new Map(overview.documents.map((item) => [item.id, item])), [overview.documents]);
  const nodeIds = useMemo(() => new Set(overview.nodes.map((node) => node.id)), [overview.nodes]);
  const childrenByParent = useMemo(() => {
    const result = new Map<string | null, KnowledgeNode[]>();
    for (const node of overview.nodes) {
      const items = result.get(node.parent_id) ?? [];
      items.push(node);
      result.set(node.parent_id, items);
    }
    return result;
  }, [overview.nodes]);
  const rootNodes = useMemo(() => overview.nodes.filter((node) => !node.parent_id || !nodeIds.has(node.parent_id)), [nodeIds, overview.nodes]);
  const followedExpanded = useMemo(
    () => followedNodeIds(
      nodeById,
      nodeByDocumentId,
      document?.id,
    ),
    [document?.id, nodeByDocumentId, nodeById],
  );
  const expansionScope = overview.snapshot?.run_id ?? "none";
  const expansionKey = expansionScope + ":" + (document?.id ?? "none");
  const [directoryExpansion, setDirectoryExpansion] = useState(() => ({
    key: expansionKey,
    nodeIds: followedExpanded,
  }));
  const expanded = directoryExpansion.key === expansionKey
    ? directoryExpansion.nodeIds
    : followedExpanded;
  const filteredDocuments = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("zh-CN");
    return normalized ? overview.documents.filter((item) => item.title.toLocaleLowerCase("zh-CN").includes(normalized)) : overview.documents;
  }, [overview.documents, query]);
  const toc = useMemo(() => collectToc(document?.blocks ?? []), [document]);

  const followDocumentPath = useCallback((documentId: string) => {
    setDirectoryExpansion({
      key: expansionScope + ":" + documentId,
      nodeIds: followedNodeIds(nodeById, nodeByDocumentId, documentId),
    });
  }, [expansionScope, nodeByDocumentId, nodeById]);

  const openDocument = useCallback(async (documentId: string, writeHistory = true) => {
    setMobileDirectoryOpen(false);
    if (document?.id === documentId) {
      followDocumentPath(documentId);
      requestAppShellCollapse();
      if (writeHistory) {
        const url = new URL(window.location.href);
        url.searchParams.set("doc", documentId);
        window.history.pushState({}, "", url);
      }
      return;
    }
    setPending(true);
    setError(null);
    try {
      const next = await apiFetch<KnowledgeDocument>("/knowledge/documents/" + encodeURIComponent(documentId));
      setDocument(next);
      followDocumentPath(next.id);
      requestAppShellCollapse();
      if (writeHistory) {
        const url = new URL(window.location.href);
        url.searchParams.set("doc", documentId);
        window.history.pushState({}, "", url);
      }
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }, [document?.id, followDocumentPath]);

  useEffect(() => {
    function synchronizeFromHistory() {
      const requested = new URLSearchParams(window.location.search).get("doc");
      const selected = requested && overview.documents.some((item) => item.id === requested)
        ? requested
        : undefined;
      if (selected) {
        void openDocument(selected, false);
        return;
      }
      setMobileDirectoryOpen(false);
      setPending(false);
      setError(null);
      setDocument(null);
      setDirectoryExpansion({
        key: expansionScope + ":none",
        nodeIds: new Set(),
      });
    }
    window.addEventListener("popstate", synchronizeFromHistory);
    return () => window.removeEventListener("popstate", synchronizeFromHistory);
  }, [expansionScope, openDocument, overview.documents]);


  useEffect(() => {
    const activeItem = documentDirectoryRef.current?.querySelector<HTMLElement>(
      '[data-knowledge-document-id][aria-current="page"]',
    );
    activeItem?.scrollIntoView?.({ block: "nearest" });
  }, [document?.id, expanded, query, sidebarOpen]);

  function toggleNode(nodeId: string) {
    setDirectoryExpansion((current) => {
      const next = new Set(
        current.key === expansionKey ? current.nodeIds : followedExpanded,
      );
      if (next.has(nodeId)) next.delete(nodeId); else next.add(nodeId);
      return { key: expansionKey, nodeIds: next };
    });
  }

  function renderDocumentButton(documentId: string, title: string, depth = 0, onSelect?: () => void) {
    const active = documentId === document?.id;
    return <button aria-current={active ? "page" : undefined} className={"flex min-w-0 w-full items-start gap-2 rounded-xl border px-3 py-2 text-left text-sm leading-6 transition-all outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] " + (active ? "border-[var(--color-border)] bg-[var(--color-surface-hover)] font-medium text-[var(--color-accent-hover)] shadow-[var(--shadow-card)]" : "border-transparent text-[var(--color-text-secondary)] hover:border-[var(--color-border)] hover:bg-[var(--color-surface-raised)] hover:text-[var(--color-text-primary)]")} data-knowledge-document-id={documentId} key={documentId} onClick={() => { void openDocument(documentId); onSelect?.(); }} style={{ paddingLeft: 8 + Math.min(depth, 5) * 12 }} type="button"><Icon className="mt-1 shrink-0 text-[var(--color-accent)]" name="file" size={15} /><span className="min-w-0 break-words">{title}</span></button>;
  }

  function renderNode(node: KnowledgeNode, onSelect?: () => void): ReactNode {
    const children = childrenByParent.get(node.id) ?? [];
    const summary = node.document_id ? documentById.get(node.document_id) : undefined;
    const isExpanded = expanded.has(node.id);
    return <div key={node.id}>
      <div className="flex items-start">
        {children.length > 0 ? <button aria-label={(isExpanded ? "收起" : "展开") + node.title} className="mt-2 grid size-6 shrink-0 place-items-center rounded-md text-[var(--color-text-muted)] transition hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-accent)] focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]" onClick={() => toggleNode(node.id)} type="button"><Icon name={isExpanded ? "chevron-down" : "chevron-right"} size={15} /></button> : <span className="w-5 shrink-0" />}
        {node.document_id && summary
          ? renderDocumentButton(node.document_id, summary.title, node.depth, onSelect)
          : node.node_type === "file"
            ? <div className="flex min-w-0 flex-1 items-start gap-2 rounded-xl px-3 py-2 text-sm leading-6 text-[var(--color-text-secondary)]" style={{ paddingLeft: 8 + Math.min(node.depth, 5) * 12 }}><Icon className="mt-1 shrink-0 text-[var(--color-accent)]" name="file" size={15} /><div className="min-w-0 flex-1"><p className="break-words font-semibold">{node.title}</p>{formatFileSize(node.file_size) || node.mime_type ? <p className="mt-0.5 break-words text-xs font-normal text-[var(--color-text-muted)]">{[formatFileSize(node.file_size), node.mime_type].filter(Boolean).join(" · ")}</p> : null}</div>{node.asset_id ? <a aria-label={"下载 " + node.title} className="inline-flex min-h-8 shrink-0 items-center gap-1 rounded-lg border border-[var(--color-action-border)] px-2 py-1 text-xs font-semibold text-[var(--color-accent)] transition hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-accent-hover)] focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]" download={node.title} href={assetUrl(node.asset_id)} onClick={onSelect}><Icon name="download" size={14} />下载</a> : <span className="shrink-0 text-xs font-normal text-[var(--color-text-muted)]">暂不可下载</span>}</div>
            : <div className="flex min-w-0 items-start gap-2 rounded-xl px-3 py-2 text-sm font-semibold leading-6 text-[var(--color-text-secondary)]" style={{ paddingLeft: 8 + Math.min(node.depth, 5) * 12 }}><Icon className="mt-1 shrink-0 text-[var(--color-accent)]" name="folder" size={15} /><span className="break-words">{node.title}</span></div>}
      </div>
      {children.length > 0 && isExpanded ? <div>{children.map((child) => renderNode(child, onSelect))}</div> : null}
    </div>;
  }

  function directory(onSelect?: () => void, desktop = false) {
    return <>
      <label className="flex min-h-11 items-center gap-2 rounded-xl border border-[var(--color-border-strong)] bg-[var(--color-surface-raised)] px-3 text-sm text-[var(--color-text-muted)] transition hover:border-[var(--color-accent)] focus-within:border-[var(--focus-ring)] focus-within:ring-2 focus-within:ring-[var(--focus-ring)]/15"><Icon name="search" size={16} /><input aria-label="搜索文档标题" className="min-w-0 flex-1 bg-transparent text-base text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)] sm:text-sm" onChange={(event) => setQuery(event.target.value)} placeholder="搜索文档" type="search" value={query} /></label>
      <nav aria-label="培训文档目录" className={"mt-4 space-y-1 " + (desktop ? "max-h-[calc(100vh-150px)] overflow-y-auto pr-2" : "")}>{query.trim() ? filteredDocuments.map((item) => renderDocumentButton(item.id, item.title, 0, onSelect)) : rootNodes.map((node) => renderNode(node, onSelect))}</nav>
    </>;
  }

  if (!overview.snapshot) return <section className="relative min-h-screen overflow-hidden bg-white px-4 py-12 text-slate-950 sm:px-6 lg:px-8"><div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_8%,rgba(54,183,255,0.08),transparent_26rem)]" /><div className="relative border border-dashed border-slate-300 bg-slate-50 p-6 text-sm leading-7 text-slate-600" style={{ borderRadius: 0 }}><h1 className="text-xl font-semibold text-slate-950">培训文档尚未同步</h1><p className="mt-3">管理员完成首次飞书知识库同步后，文档会显示在这里。</p></div></section>;

  return <main className="relative min-h-screen overflow-x-clip bg-white text-slate-950" data-testid="knowledge-reader">
    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_8%,rgba(54,183,255,0.08),transparent_26rem)]" />
    <article className="relative w-full min-w-0 overflow-x-clip px-4 pb-20 pt-7 sm:px-6 lg:px-8">
      <header className="mb-8 border-b border-slate-200 pb-8" style={{ borderRadius: 0 }}><p className="text-[0.72rem] font-bold uppercase tracking-[0.18em] text-[#1687c9]">PNX Knowledge Base</p><h1 className="mt-3 text-3xl font-black text-slate-950 sm:text-5xl">PNX 培训知识库</h1><p className="mt-3 text-sm text-slate-500">{overview.snapshot.document_count} 篇文档 · 最近同步 {formatDateTime(overview.snapshot.synced_at)}</p></header>
      {!mobileDirectoryOpen ? <button aria-label="打开目录" className="fixed bottom-4 right-4 z-40 inline-flex min-h-11 items-center gap-2 rounded-xl border border-[var(--color-action-border)] bg-[var(--color-action-fill)] px-4 py-2 text-sm font-semibold text-[var(--color-action-text)] shadow-[var(--shadow-button)] transition hover:bg-[var(--color-action-fill-hover)] focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] lg:hidden" onClick={() => setMobileDirectoryOpen(true)} title="打开目录" type="button"><Icon name="list" size={17} />目录</button> : null}
      {mobileDirectoryOpen ? <div aria-label="移动端目录" aria-modal="true" className="fixed inset-0 z-50 bg-[var(--color-text-primary)]/25 p-4 backdrop-blur-sm lg:hidden" role="dialog"><div className="mx-auto flex h-full max-w-lg flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-soft)]"><div className="flex min-h-14 items-center justify-between border-b border-[var(--color-border)] px-4"><span className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.16em] text-[var(--color-accent)]"><Icon name="list" size={17} />目录</span><button aria-label="关闭目录" className={directoryIconButtonClassName} onClick={() => setMobileDirectoryOpen(false)} title="关闭目录" type="button"><Icon name="x" size={20} /></button></div><div className="min-h-0 flex-1 overflow-y-auto p-4">{directory(() => setMobileDirectoryOpen(false))}{document && toc.length > 0 ? <div className="mt-8 border-t border-[var(--color-border)] pt-5"><p className="mb-3 text-xs font-bold uppercase tracking-[0.16em] text-[var(--color-accent)]">本文目录</p><nav aria-label="移动端本文目录" className="space-y-1">{toc.map((item) => <a className={"block rounded-lg px-2 py-1.5 text-sm leading-6 text-[var(--color-text-secondary)] transition hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-accent)] " + (item.level > 1 ? "pl-5" : "")} href={"#" + item.id} key={item.id} onClick={() => setMobileDirectoryOpen(false)}>{item.label}</a>)}</nav></div> : null}</div></div></div> : null}
      <div className={"grid " + (sidebarOpen ? "gap-4 lg:grid-cols-[280px_minmax(0,1fr)] lg:gap-8" : "gap-4 lg:grid-cols-[40px_minmax(0,1fr)] lg:gap-8")}>
        <aside className={"hidden lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start " + (sidebarOpen ? "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 shadow-[var(--shadow-card)] lg:block" : "w-10 lg:block")} data-testid="knowledge-document-directory" ref={documentDirectoryRef}>
          {sidebarOpen ? <><div className={directoryHeaderClassName}><span className="text-xs font-bold uppercase tracking-[0.16em] text-[var(--color-accent)]">文档目录</span><button aria-label="收起文档目录" className={directoryIconButtonClassName} onClick={() => setSidebarOpen(false)} title="收起文档目录" type="button"><Icon name="chevrons-left" /></button></div>{directory(undefined, true)}</> : <button aria-label="展开文档目录" className={directoryIconButtonClassName} onClick={() => setSidebarOpen(true)} title="展开文档目录" type="button"><Icon name="chevrons-right" /></button>}
        </aside>
        <section className="min-w-0" data-testid="knowledge-document">{error ? <p className="mb-5 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert" style={{ borderRadius: 0 }}>{error}</p> : null}<span aria-live="polite" className="sr-only" role="status">{pending ? "正在加载文档" : ""}</span>{document ? <><header className="mb-8 border-b border-slate-200 pb-6" style={{ borderRadius: 0 }}><h2 className="text-3xl font-black text-slate-950 sm:text-4xl">{document.title}</h2>{allowFeishuSourceLinks ? <a className="mt-3 inline-block break-words text-sm text-[#1687c9] transition hover:text-slate-950" href={document.source_url} rel="noreferrer" target="_blank">在飞书中打开原文 ↗</a> : null}</header><DocumentBody allowFeishuSourceLinks={allowFeishuSourceLinks} document={document} onOpenDocument={(documentId) => { void openDocument(documentId); }} tokenToDocument={tokenToDocument} />{document.blocks.length === 0 ? <p className="py-12 text-center text-sm text-slate-400">这篇文档当前没有可展示的内容。</p> : null}</> : <p className="py-16 text-center text-sm text-slate-400">从目录选择一篇培训文档。</p>}</section>
      </div>
    </article>
  </main>;
}
