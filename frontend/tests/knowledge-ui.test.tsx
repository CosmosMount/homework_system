import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { KnowledgeAdminPanel } from "@/components/admin/knowledge-admin-panel";
import { KnowledgeBlocks } from "@/components/knowledge/knowledge-blocks";
import { KnowledgeReader } from "@/components/knowledge/knowledge-reader";
import { AppShell } from "@/components/layout/app-shell";
import type {
  KnowledgeAdminStatus,
  KnowledgeDocument,
  KnowledgeOverview,
} from "@/lib/api/types";

const { apiFetchMock, csrfFetchMock, replaceMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  csrfFetchMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/knowledge",
  useRouter: () => ({ replace: replaceMock }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiFetch: apiFetchMock,
  csrfFetch: csrfFetchMock,
}));

const student = {
  id: "student-id",
  email: "student@connect.hkust-gz.edu.cn",
  student_number: "20260001",
  full_name: "测试学生",
  role: "student" as const,
  status: "active" as const,
  cohort: null,
  direction: null,
  email_verified_at: "2026-08-24T00:00:00Z",
  created_at: "2026-08-24T00:00:00Z",
  revision: 1,
};

function document(
  id = "document-1",
  title = "机械基础",
): KnowledgeDocument {
  return {
    id,
    title,
    source_url: "https://pnx.feishu.cn/wiki/node-" + id,
    source_token: "token-" + id,
    display_order: id === "document-1" ? 0 : 1,
    synced_at: "2026-08-27T08:00:00Z",
    blocks: [
      {
        id: "heading-" + id,
        type: "heading",
        level: 2,
        segments: [{ text: title }],
      },
      {
        id: "paragraph-" + id,
        type: "paragraph",
        segments: [{ text: "培训正文" }],
      },
    ],
  };
}

function overview(): KnowledgeOverview {
  return {
    snapshot: {
      run_id: "run-1",
      synced_at: "2026-08-27T08:00:00Z",
      source_url: "https://pnx.feishu.cn/wiki/",
      document_count: 2,
      asset_count: 1,
    },
    nodes: [
      {
        id: "node-1",
        parent_id: null,
        document_id: "document-1",
        title: "机械基础",
        node_type: "document",
        depth: 0,
        display_order: 0,
        source_url: "https://pnx.feishu.cn/wiki/node-1",
      },
      {
        id: "node-2",
        parent_id: null,
        document_id: "document-2",
        title: "视觉进阶",
        node_type: "document",
        depth: 0,
        display_order: 1,
        source_url: "https://pnx.feishu.cn/wiki/node-2",
      },
    ],
    documents: [
      {
        id: "document-1",
        title: "机械基础",
        source_url: "https://pnx.feishu.cn/wiki/node-1",
        source_token: "token-document-1",
        display_order: 0,
      },
      {
        id: "document-2",
        title: "视觉进阶",
        source_url: "https://pnx.feishu.cn/wiki/node-2",
        source_token: "token-document-2",
        display_order: 1,
      },
    ],
  };
}

describe("knowledge document renderer", () => {
  it("renders code copy, tables, protected images, attachments, and internal links", () => {
    const openDocument = vi.fn();
    const { container } = render(
      <KnowledgeBlocks
        blocks={[
          {
            id: "paragraph",
            type: "paragraph",
            segments: [
              { text: "下一篇", document_token: "target-token" },
              {
                text: "普通飞书链接",
                href: "https://pnx.feishu.cn/wiki/node-target",
              },
              { text: "外部", href: "https://example.edu" },
              { text: "e^{i\\pi}+1=0", equation: true },
            ],
          },
          {
            id: "equation",
            type: "equation",
            segments: [{
              text: "\\int_0^\\infty e^{-x^2}\\,dx=\\frac{\\sqrt{\\pi}}{2}",
              equation: true,
            }],
          },
          {
            id: "invalid-equation",
            type: "equation",
            segments: [{ text: "\\notacommand{", equation: true }],
          },
          {
            id: "untrusted-equation",
            type: "equation",
            segments: [{ text: "\\htmlClass{danger}{x}", equation: true }],
          },
          {
            id: "code",
            type: "code",
            language: "Python",
            segments: [{ text: "print('PNX')" }],
          },
          {
            id: "image",
            type: "image",
            asset_id: "asset-image",
            file_name: "结构图.png",
          },
          {
            id: "attachment",
            type: "attachment",
            asset_id: "asset-file",
            file_name: "培训资料.pdf",
            file_size: 4096,
            mime_type: "application/pdf",
          },
          {
            id: "table",
            type: "table",
            rows: [[{
              id: "cell",
              row_span: 2,
              blocks: [{
                id: "cell-paragraph",
                type: "paragraph",
                segments: [{ text: "表格内容" }],
              }],
            }]],
          },
        ]}
        onOpenDocument={openDocument}
        tokenToDocument={new Map([
          ["target-token", "document-2"],
          ["node-target", "document-3"],
        ])}
      />,
    );

    fireEvent.click(screen.getByRole("link", { name: "下一篇" }));
    expect(openDocument).toHaveBeenCalledWith("document-2");
    const wikiLink = screen.getByRole("link", { name: "普通飞书链接" });
    expect(wikiLink).not.toHaveAttribute("target");
    fireEvent.click(wikiLink);
    expect(openDocument).toHaveBeenCalledWith("document-3");
    expect(screen.getByRole("link", { name: "外部" })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(container.querySelectorAll(".katex")).toHaveLength(2);
    expect(container.querySelector(".katex-display")).toBeInTheDocument();
    const equationFallbacks = screen.getAllByLabelText("公式解析失败");
    expect(equationFallbacks).toHaveLength(2);
    expect(equationFallbacks[0]).toHaveTextContent("\\notacommand{");
    expect(equationFallbacks[1]).toHaveTextContent("\\htmlClass{danger}{x}");
    expect(container.querySelector(".danger")).not.toBeInTheDocument();
    expect(screen.getByAltText("结构图.png")).toHaveAttribute(
      "src",
      "/api/v1/knowledge/assets/asset-image/content",
    );
    expect(screen.getByRole("link", { name: "下载" })).toHaveAttribute(
      "href",
      "/api/v1/knowledge/assets/asset-file/content",
    );
    expect(
      screen.getByText("4.0 KB · application/pdf"),
    ).toBeInTheDocument();

    expect(screen.getByRole("cell", { name: "表格内容" })).toHaveAttribute(
      "rowspan",
      "2",
    );
  });
});

describe("knowledge reader", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    csrfFetchMock.mockReset();
    replaceMock.mockReset();
    vi.stubGlobal("scrollTo", vi.fn());
  });

  it("filters titles and loads another document without leaving the reader", async () => {
    apiFetchMock.mockResolvedValue(document("document-2", "视觉进阶"));
    render(
      <AppShell fullBleed user={student}>
        <KnowledgeReader
          initialDocument={document()}
          overview={overview()}
        />
      </AppShell>,
    );
    expect(screen.getByTestId("app-shell-sidebar")).toHaveAttribute(
      "data-state",
      "expanded",
    );

    fireEvent.change(screen.getByLabelText("搜索文档标题"), {
      target: { value: "视觉" },
    });
    expect(screen.queryByRole("button", { name: "机械基础" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "视觉进阶" }));

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1));
    expect(
      screen.getAllByRole("heading", { name: "视觉进阶", level: 2 }),
    ).toHaveLength(1);
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/knowledge/documents/document-2",
    );
    expect(window.location.search).toBe("?doc=document-2");
    expect(screen.getByTestId("app-shell-sidebar")).toHaveAttribute(
      "data-state",
      "collapsed",
    );
    expect(screen.getByRole("button", { name: "收起文档目录" })).toBeInTheDocument();
  });
  it("matches the reference directory controls on desktop and mobile", () => {
    render(
      <KnowledgeReader initialDocument={document()} overview={overview()} />,
    );

    expect(screen.getByRole("heading", { name: "PNX 培训知识库" })).toBeInTheDocument();
    expect(screen.getByTestId("knowledge-reader")).toHaveClass("bg-white", "text-slate-950");
    expect(screen.getByTestId("knowledge-page-toc")).toHaveClass(
      "lg:sticky",
      "lg:top-6",
      "lg:max-h-[calc(100vh-3rem)]",
      "lg:overflow-y-auto",
    );
    expect(screen.getByRole("button", { name: "收起文档目录" })).toHaveClass(
      "rounded-lg",
      "border-[var(--color-border)]",
    );
    expect(screen.getByRole("button", { name: "机械基础" })).toHaveClass("rounded-xl");
    expect(screen.getByLabelText("搜索文档标题").parentElement).toHaveClass(
      "rounded-xl",
      "bg-[var(--color-surface-raised)]",
    );
    expect(screen.getByTestId("knowledge-document-directory").nextElementSibling).toBe(
      screen.getByTestId("knowledge-document"),
    );
    expect(screen.getByTestId("knowledge-document-content").nextElementSibling).toBe(
      screen.getByTestId("knowledge-page-toc"),
    );

    fireEvent.click(screen.getByRole("button", { name: "收起文档目录" }));
    expect(screen.getByRole("button", { name: "展开文档目录" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "收起本文目录" }));
    expect(screen.getByRole("button", { name: "展开本文目录" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "打开目录" }));
    expect(screen.getByRole("dialog", { name: "移动端目录" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "关闭目录" }));
    expect(screen.queryByRole("dialog", { name: "移动端目录" })).not.toBeInTheDocument();
  });

  it("keeps the current document visible when the next document fails", async () => {
    apiFetchMock.mockRejectedValue(new Error("network"));
    render(
      <AppShell fullBleed user={student}>
        <KnowledgeReader initialDocument={document()} overview={overview()} />
      </AppShell>,
    );

    fireEvent.click(screen.getByRole("button", { name: "视觉进阶" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("文档加载失败");
    expect(screen.getByRole("heading", { name: "机械基础", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("培训正文")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起文档目录" })).toBeInTheDocument();
    expect(screen.getByTestId("app-shell-sidebar")).toHaveAttribute(
      "data-state",
      "expanded",
    );
  });

  it("tracks the current heading while the right table of contents follows scrolling", async () => {
    const trackedDocument = document();
    trackedDocument.blocks = [
      { id: "heading-intro", type: "heading", level: 2, segments: [{ text: "入门" }] },
      { id: "paragraph-intro", type: "paragraph", segments: [{ text: "入门正文" }] },
      { id: "heading-advanced", type: "heading", level: 2, segments: [{ text: "进阶" }] },
      { id: "paragraph-advanced", type: "paragraph", segments: [{ text: "进阶正文" }] },
    ];
    render(<KnowledgeReader initialDocument={trackedDocument} overview={overview()} />);

    const intro = window.document.getElementById("kb-heading-intro");
    const advanced = window.document.getElementById("kb-heading-advanced");
    expect(intro).not.toBeNull();
    expect(advanced).not.toBeNull();
    if (!intro || !advanced) return;
    intro.getBoundingClientRect = vi.fn(() => ({ top: -40 }) as DOMRect);
    advanced.getBoundingClientRect = vi.fn(() => ({ top: 80 }) as DOMRect);
    fireEvent.scroll(window);

    await waitFor(() => expect(screen.getByRole("link", { name: "进阶" })).toHaveAttribute(
      "aria-current",
      "location",
    ));
    expect(screen.getByRole("link", { name: "入门" })).not.toHaveAttribute("aria-current");
  });

  it("loads the URL document when browser history changes", async () => {
    apiFetchMock.mockResolvedValue(document("document-2", "视觉进阶"));
    render(
      <KnowledgeReader initialDocument={document()} overview={overview()} />,
    );

    window.history.pushState({}, "", "/knowledge?doc=document-2");
    window.dispatchEvent(new PopStateEvent("popstate"));

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith(
      "/knowledge/documents/document-2",
    ));
    expect(await screen.findByRole("heading", { name: "视觉进阶", level: 2 })).toBeInTheDocument();
  });

  it("keeps a clear empty state before the first successful sync", () => {
    render(
      <KnowledgeReader
        initialDocument={null}
        overview={{ snapshot: null, nodes: [], documents: [] }}
      />,
    );
    expect(screen.getByText("培训文档尚未同步")).toBeInTheDocument();
  });
});

describe("knowledge administrator panel", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    csrfFetchMock.mockReset();
  });

  it("creates one manual asynchronous sync task", async () => {
    const initial: KnowledgeAdminStatus = {
      configured: true,
      current_snapshot: null,
      latest_run: null,
    };
    csrfFetchMock.mockResolvedValue({
      run: {
        id: "run-2",
        status: "pending",
        source_url: "https://pnx.feishu.cn/wiki/",
        started_at: null,
        finished_at: null,
        document_count: 0,
        asset_count: 0,
        error_code: null,
        error_summary: null,
        created_at: "2026-08-27T09:00:00Z",
      },
    });
    render(<KnowledgeAdminPanel initialStatus={initial} />);

    fireEvent.click(screen.getByRole("button", { name: "立即同步" }));

    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledTimes(1));
    expect(csrfFetchMock).toHaveBeenCalledWith(
      "/admin/knowledge/sync",
      { method: "POST" },
    );
    expect(screen.getByText("等待 Worker")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "同步进行中…" })).toBeDisabled();
  });
});
