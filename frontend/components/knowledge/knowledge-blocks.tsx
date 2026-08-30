/* eslint-disable @next/next/no-img-element */
"use client";

import { useState } from "react";
import type { ReactNode, SVGProps } from "react";
import katex from "katex";

import type {
  KnowledgeBlock,
  KnowledgeRichSegment,
  KnowledgeTableCell,
} from "@/lib/api/types";
import { feishuDocumentToken } from "@/lib/knowledge-links";

type KnowledgeBlocksProps = Readonly<{
  blocks: KnowledgeBlock[];
  tokenToDocument: ReadonlyMap<string, string>;
  onOpenDocument: (documentId: string) => void;
}>;

type IconName = "check" | "copy" | "download" | "file";

function Icon({ name, size = 18, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  const shape = name === "check"
    ? <path d="m20 6-11 11-5-5" />
    : name === "copy"
      ? <><rect width="14" height="14" x="8" y="8" rx="2" /><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" /></>
      : name === "download"
        ? <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" /></>
        : <><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5Z" /><polyline points="14 2 14 8 20 8" /><path d="M8 13h8M8 17h8" /></>;
  return <svg aria-hidden="true" fill="none" focusable="false" height={size} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width={size} {...props}>{shape}</svg>;
}

function assetUrl(assetId: string): string {
  return "/api/v1/knowledge/assets/" + encodeURIComponent(assetId) + "/content";
}

function MathFormula({ latex, displayMode = false }: Readonly<{
  latex: string;
  displayMode?: boolean;
}>) {
  let html: string | undefined;
  try {
    html = katex.renderToString(latex, {
      displayMode,
      maxExpand: 1000,
      maxSize: 20,
      output: "htmlAndMathml",
      strict: (errorCode) => errorCode === "htmlExtension" ? "error" : "warn",
      throwOnError: true,
      trust: false,
    });
  } catch {
    html = undefined;
  }
  if (html !== undefined) {
    const className = displayMode
      ? "my-6 max-w-full overflow-x-auto py-2 text-center text-slate-900"
      : "inline-block max-w-full overflow-x-auto align-middle text-slate-900";
    const Tag = displayMode ? "div" : "span";
    return <Tag className={className} dangerouslySetInnerHTML={{ __html: html }} />;
  }
  const className = displayMode
    ? "my-6 max-w-full overflow-x-auto whitespace-pre-wrap rounded border border-amber-200 bg-amber-50 px-4 py-3 text-left font-mono text-sm text-amber-950"
    : "rounded bg-amber-50 px-1.5 py-0.5 font-mono text-[0.9em] text-amber-950";
  const Tag = displayMode ? "pre" : "code";
  return <Tag aria-label="公式解析失败" className={className}>{latex}</Tag>;
}

function RichText({ segments = [], tokenToDocument, onOpenDocument }: Readonly<{
  segments?: KnowledgeRichSegment[];
  tokenToDocument: ReadonlyMap<string, string>;
  onOpenDocument: (documentId: string) => void;
}>) {
  return segments.map((segment, index) => {
    let content: ReactNode = segment.equation
      ? <MathFormula latex={segment.text} />
      : segment.text;
    if (segment.inline_code) content = <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.9em] text-[#1687c9]">{content}</code>;
    if (segment.bold) content = <strong className="font-bold text-slate-900">{content}</strong>;
    if (segment.italic) content = <em>{content}</em>;
    if (segment.underline) content = <u>{content}</u>;
    if (segment.strikethrough) content = <s>{content}</s>;
    const documentToken =
      segment.document_token ?? feishuDocumentToken(segment.href);
    const documentId = documentToken
      ? tokenToDocument.get(documentToken)
      : undefined;
    if (documentId) return <a className="text-[#1687c9] underline decoration-[#1687c9]/50 underline-offset-2 transition hover:text-slate-950" href={"?doc=" + encodeURIComponent(documentId)} key={index} onClick={(event) => { event.preventDefault(); onOpenDocument(documentId); }}>{content}</a>;
    if (segment.href) return <a className="text-[#1687c9] underline decoration-[#1687c9]/50 underline-offset-2 transition hover:text-slate-950" href={segment.href} key={index} rel="noreferrer" target="_blank">{content}</a>;
    return <span key={index}>{content}</span>;
  });
}

const codeKeywords = new Set(["as", "async", "await", "break", "case", "catch", "class", "const", "continue", "def", "delete", "do", "else", "enum", "export", "extends", "finally", "for", "from", "fn", "function", "if", "import", "in", "interface", "let", "match", "namespace", "new", "of", "package", "private", "protected", "public", "return", "select", "static", "struct", "switch", "template", "this", "throw", "try", "type", "typename", "using", "var", "void", "while", "with", "yield"]);

function languageKey(language?: string): string {
  const normalized = (language ?? "").toLowerCase();
  if (!normalized || normalized.includes("plain") || normalized === "text") return "text";
  return normalized;
}

function highlightCode(source: string, language?: string): ReactNode {
  if (languageKey(language) === "text") return source;
  const pattern = /(\/\*[\s\S]*?\*\/|\/\/[^\n]*|#[^\n]*|`(?:\\.|[^`])*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b[A-Za-z_$][\w$]*\b)/g;
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source))) {
    const token = match[0];
    if (match.index > cursor) nodes.push(source.slice(cursor, match.index));
    const className = token.startsWith("//") || token.startsWith("/*") || token.startsWith("#")
      ? "text-slate-400 italic"
      : token.startsWith("\"") || token.startsWith("'") || token.startsWith("`")
        ? "text-emerald-700"
        : /^\d/.test(token)
          ? "text-amber-700"
          : codeKeywords.has(token)
            ? "text-[#1687c9]"
            : /^(true|false|null|None|undefined|True|False)$/.test(token)
              ? "text-fuchsia-700"
              : "text-cyan-700";
    nodes.push(<span className={className} key={"code-token-" + key++}>{token}</span>);
    cursor = match.index + token.length;
  }
  if (cursor < source.length) nodes.push(source.slice(cursor));
  return nodes;
}

async function copyCodeText(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function CodeBlock({ block }: Readonly<{ block: KnowledgeBlock }>) {
  const [copied, setCopied] = useState(false);
  const text = (block.segments ?? []).map((segment) => segment.text).join("");
  async function copy() {
    try {
      await copyCodeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }
  return <div className="my-6 min-w-0 overflow-hidden border border-slate-200 bg-slate-50" style={{ borderRadius: 4 }}>
    <div className="flex min-h-10 items-center justify-between gap-3 border-b border-slate-200 bg-slate-100 px-3 py-2 text-xs text-slate-500 sm:min-h-0" style={{ borderRadius: 0 }}><span>{block.language || "纯文本"}</span><button aria-label="复制代码" className="inline-flex min-h-8 shrink-0 items-center gap-1.5 text-slate-600 transition hover:text-[#1687c9]" onClick={() => { void copy(); }} type="button">{copied ? <Icon name="check" size={14} /> : <Icon name="copy" size={14} />}{copied ? "已复制" : "复制"}</button></div>
    <pre className={"overflow-x-auto p-3 text-[0.8rem] leading-6 text-slate-800 sm:p-4 sm:text-sm " + (block.wrap ? "whitespace-pre-wrap break-words" : "")}><code>{highlightCode(text, block.language)}</code></pre>
  </div>;
}

const calloutBackground: Record<number, string> = { 1: "bg-rose-400/[0.08]", 2: "bg-orange-400/[0.08]", 3: "bg-yellow-400/[0.08]", 4: "bg-emerald-400/[0.08]", 5: "bg-blue-400/[0.08]", 6: "bg-violet-400/[0.08]", 7: "bg-slate-50", 8: "bg-rose-400/[0.16]", 9: "bg-orange-400/[0.16]", 10: "bg-yellow-400/[0.16]", 11: "bg-emerald-400/[0.16]", 12: "bg-blue-400/[0.16]", 13: "bg-violet-400/[0.16]", 14: "bg-slate-100" };
const calloutBorder: Record<number, string> = { 1: "border-rose-300/45", 2: "border-orange-300/45", 3: "border-yellow-300/45", 4: "border-emerald-300/45", 5: "border-blue-300/45", 6: "border-violet-300/45", 7: "border-slate-300" };
const calloutText: Record<number, string> = { 1: "text-rose-800", 2: "text-orange-800", 3: "text-yellow-800", 4: "text-emerald-800", 5: "text-blue-800", 6: "text-violet-800", 7: "text-slate-700" };
const calloutEmoji: Record<string, string> = { bulb: "💡", check: "✅", exclamation: "❗", eyes: "👀", info: "ℹ️", link: "🔗", memo: "📝", paperclip: "📎", pin: "📌", pushpin: "📌", question: "❓", sparkles: "✨", tada: "🎉", thinking_face: "🤔", trophy: "🏆", warning: "⚠️", white_check_mark: "✅" };

function tone(value: number | string | undefined, fallback = 7): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function emoji(value?: string): string {
  if (!value) return "💡";
  return /[^\x00-\x7f]/.test(value) ? value : (calloutEmoji[value.toLowerCase()] ?? "💡");
}

function formatFileSize(size?: number): string {
  if (!size || size < 1) return "";
  if (size < 1024) return size + " B";
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
  return (size / 1024 / 1024).toFixed(1) + " MB";
}

function Nested({ block, tokenToDocument, onOpenDocument }: Readonly<{ block: KnowledgeBlock; tokenToDocument: ReadonlyMap<string, string>; onOpenDocument: (documentId: string) => void }>) {
  return block.children?.length ? <div className="mt-2 border-l border-slate-200 pl-4" style={{ borderRadius: 0 }}><KnowledgeBlocks blocks={block.children} onOpenDocument={onOpenDocument} tokenToDocument={tokenToDocument} /></div> : null;
}

function MediaBlock({ block, inGallery }: Readonly<{ block: KnowledgeBlock; inGallery: boolean }>) {
  if (!block.asset_id) return null;
  return <figure className={inGallery ? "min-w-0" : "my-8"}>
    <a href={assetUrl(block.asset_id)} rel="noreferrer" target="_blank"><img alt={block.file_name || (block.type === "whiteboard" ? "飞书白板" : "知识库图片")} className={inGallery ? "h-auto max-h-[520px] w-full border border-slate-200 object-contain" : "h-auto max-h-[720px] w-auto max-w-full border border-slate-200 object-contain"} height={block.height ?? undefined} loading="lazy" src={assetUrl(block.asset_id)} style={{ borderRadius: 4 }} width={block.width ?? undefined} /></a>
    {block.type === "whiteboard" ? <figcaption className="mt-2 text-sm text-slate-500">飞书白板 · 点击查看原图</figcaption> : null}
  </figure>;
}

function AttachmentBlock({ block }: Readonly<{ block: KnowledgeBlock }>) {
  const href = block.asset_id ? assetUrl(block.asset_id) : block.fallback_url;
  const metadata = [formatFileSize(block.file_size), block.mime_type].filter(Boolean).join(" · ");
  return <div className="my-5 flex min-w-0 items-center gap-3 border border-slate-200 bg-slate-50 p-3 sm:p-4" style={{ borderRadius: 4 }}><span className="grid size-10 shrink-0 place-items-center rounded bg-[#1687c9]/10 text-[#1687c9]"><Icon name="file" size={20} /></span><div className="min-w-0 flex-1"><p className="break-words text-sm font-semibold text-slate-900">{block.file_name || "附件"}</p>{metadata ? <p className="mt-1 break-words text-xs text-slate-500">{metadata}</p> : null}</div>{href ? <a className="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded border border-[#1687c9]/45 px-3 py-2 text-sm font-semibold text-[#1687c9] transition hover:border-[#1687c9] hover:bg-[#1687c9]/10 hover:text-slate-950" download={block.asset_id ? block.file_name : undefined} href={href} rel={block.asset_id ? undefined : "noreferrer"} target={block.asset_id ? undefined : "_blank"}>{block.asset_id ? <><Icon name="download" size={16} /><span className="hidden sm:inline">下载</span></> : "在飞书查看"}</a> : null}</div>;
}

function tableCellData(cell: KnowledgeBlock[] | KnowledgeTableCell) {
  return Array.isArray(cell)
    ? { blocks: cell, rowSpan: undefined, colSpan: undefined }
    : {
        blocks: cell.blocks,
        rowSpan: cell.row_span,
        colSpan: cell.col_span,
      };
}

function Block({ block, tokenToDocument, onOpenDocument }: Readonly<{ block: KnowledgeBlock; tokenToDocument: ReadonlyMap<string, string>; onOpenDocument: (documentId: string) => void }>) {
  const rich = <RichText onOpenDocument={onOpenDocument} segments={block.segments} tokenToDocument={tokenToDocument} />;
  switch (block.type) {
    case "paragraph": return <div className="my-3 break-words leading-8 text-slate-700"><p>{rich}</p><Nested block={block} onOpenDocument={onOpenDocument} tokenToDocument={tokenToDocument} /></div>;
    case "heading": return (block.level ?? 1) <= 1 ? <h2 className="scroll-mt-8 break-words pt-8 text-2xl font-bold text-slate-900 sm:text-3xl" id={"kb-" + block.id}>{rich}</h2> : <h3 className="scroll-mt-8 break-words pt-7 text-xl font-bold text-slate-900 sm:text-2xl" id={"kb-" + block.id}>{rich}</h3>;
    case "todo": return <div className="my-3 flex gap-3 bg-slate-50 px-4 py-3 text-slate-700" style={{ borderRadius: 4 }}><span aria-label={block.done ? "已完成" : "未完成"}>{block.done ? "☑" : "☐"}</span><div className={block.done ? "text-slate-500 line-through" : ""}>{rich}<Nested block={block} onOpenDocument={onOpenDocument} tokenToDocument={tokenToDocument} /></div></div>;
    case "quote": return <blockquote className="my-5 break-words border-l-2 border-[#1687c9]/80 bg-[#1687c9]/[0.05] px-4 py-3 leading-7 text-slate-700 sm:px-5">{rich}<Nested block={block} onOpenDocument={onOpenDocument} tokenToDocument={tokenToDocument} /></blockquote>;
    case "equation": return <MathFormula displayMode latex={(block.segments ?? []).map((segment) => segment.text).join("")} />;
    case "callout": {
      const background = tone(block.background_color ?? block.tone);
      const border = tone(block.border_color);
      const text = tone(block.text_color);
      return <aside className={`my-6 flex min-w-0 items-start gap-3 border px-4 py-4 sm:gap-4 sm:px-5 ${calloutBackground[background] ?? calloutBackground[7]} ${calloutBorder[border] ?? calloutBorder[7]} ${calloutText[text] ?? calloutText[7]}`} style={{ borderRadius: 4 }}><span aria-hidden="true" className="mt-0.5 shrink-0 text-xl leading-7" title={block.emoji_id}>{emoji(block.emoji_id)}</span><div className="min-w-0 flex-1 space-y-4">{rich}<Nested block={block} onOpenDocument={onOpenDocument} tokenToDocument={tokenToDocument} /></div></aside>;
    }
    case "code": return <CodeBlock block={block} />;
    case "divider": return <hr className="my-8 border-0 border-t border-slate-200" />;
    case "image":
    case "whiteboard": return <MediaBlock block={block} inGallery={false} />;
    case "attachment": return <AttachmentBlock block={block} />;
    case "table": return <div className="my-8 max-w-full overflow-x-auto border border-slate-200" style={{ borderRadius: 4 }}><table className="w-full min-w-[640px] border-collapse text-left text-sm"><tbody>{(block.rows ?? []).map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => {
      const data = tableCellData(cell);
      return <td className="whitespace-pre-wrap break-words border border-slate-200 px-3 py-2 align-top leading-6 text-slate-700" colSpan={data.colSpan} key={Array.isArray(cell) ? cellIndex : cell.id} rowSpan={data.rowSpan}><KnowledgeBlocks blocks={data.blocks} onOpenDocument={onOpenDocument} tokenToDocument={tokenToDocument} /></td>;
    })}</tr>)}</tbody></table></div>;
    case "container": return <Nested block={block} onOpenDocument={onOpenDocument} tokenToDocument={tokenToDocument} />;
    case "bullet":
    case "ordered": return null;
  }
}

export function KnowledgeBlocks({ blocks, tokenToDocument, onOpenDocument }: KnowledgeBlocksProps) {
  const rendered: ReactNode[] = [];
  for (let index = 0; index < blocks.length; index += 1) {
    const block = blocks[index];
    if (block.type === "bullet" || block.type === "ordered") {
      const type = block.type;
      const items: KnowledgeBlock[] = [];
      while (index < blocks.length && blocks[index].type === type) { items.push(blocks[index]); index += 1; }
      index -= 1;
      const List = type === "bullet" ? "ul" : "ol";
      rendered.push(<List className={type === "bullet" ? "list-disc space-y-2 pl-6" : "list-decimal space-y-2 pl-6"} key={"list-" + block.id}>{items.map((item) => <li className="break-words leading-7 text-slate-700" key={item.id}><RichText onOpenDocument={onOpenDocument} segments={item.segments} tokenToDocument={tokenToDocument} /><Nested block={item} onOpenDocument={onOpenDocument} tokenToDocument={tokenToDocument} /></li>)}</List>);
      continue;
    }
    if (block.type === "image" || block.type === "whiteboard") {
      const gallery: KnowledgeBlock[] = [block];
      while (index + 1 < blocks.length && (blocks[index + 1].type === "image" || blocks[index + 1].type === "whiteboard")) { gallery.push(blocks[index + 1]); index += 1; }
      rendered.push(gallery.length > 1 ? <div className="my-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" key={"gallery-" + block.id}>{gallery.map((item) => <MediaBlock block={item} inGallery key={item.id} />)}</div> : <MediaBlock block={block} inGallery={false} key={block.id} />);
      continue;
    }
    rendered.push(<Block block={block} key={block.id} onOpenDocument={onOpenDocument} tokenToDocument={tokenToDocument} />);
  }
  return <>{rendered}</>;
}
