import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { KnowledgeReferencePicker } from "@/components/knowledge/knowledge-reference-picker";
import {
  escapeMarkdownLinkLabel,
  insertMarkdownAtSelection,
  knowledgeDocumentReference,
} from "@/lib/knowledge-references";
import type { KnowledgeOverview } from "@/lib/api/types";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiFetch: apiFetchMock,
}));

const overview: KnowledgeOverview = {
  snapshot: {
    run_id: "snapshot-1",
    synced_at: "2026-08-27T08:00:00Z",
    source_url: "https://pnx.feishu.cn/wiki/space",
    document_count: 2,
    asset_count: 0,
  },
  nodes: [],
  documents: [
    {
      id: "document-1",
      title: "机械基础 [入门]",
      source_url: "https://pnx.feishu.cn/wiki/document-1",
      source_token: "token/one?x=1",
      display_order: 0,
    },
    {
      id: "document-2",
      title: "视觉进阶",
      source_url: "https://pnx.feishu.cn/wiki/document-2",
      source_token: "token-two",
      display_order: 1,
    },
  ],
};

describe("knowledge references", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("escapes markdown labels and URL-encodes stable source tokens", () => {
    expect(escapeMarkdownLinkLabel("A\\[B]")).toBe("A\\\\\\[B\\]");
    expect(
      knowledgeDocumentReference({
        title: "机械基础 [入门]",
        source_token: "token/one?x=1",
      }),
    ).toBe("[机械基础 \\[入门\\]](/knowledge?source=token%2Fone%3Fx%3D1)");
  });

  it("inserts a reference with readable paragraph spacing and cursor position", () => {
    const result = insertMarkdownAtSelection(
      "已有内容\n\n更多内容",
      "[培训文档](/knowledge?source=token)",
      4,
      4,
    );

    expect(result.value).toBe(
      "已有内容\n\n[培训文档](/knowledge?source=token)\n\n更多内容",
    );
    expect(result.cursor).toBe(4 + 2 + "[培训文档](/knowledge?source=token)".length);
  });

  it("loads, searches, and inserts a selected document", async () => {
    apiFetchMock.mockResolvedValue(overview);
    const onInsert = vi.fn();
    render(<KnowledgeReferencePicker onInsert={onInsert} />);

    fireEvent.click(screen.getByRole("button", { name: "引用知识库文档" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/knowledge"));
    expect(screen.getByText("机械基础 [入门]")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "搜索知识库文档" }), {
      target: { value: "视觉" },
    });
    expect(screen.queryByText("机械基础 [入门]")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "视觉进阶" }));

    expect(onInsert).toHaveBeenCalledWith(
      "[视觉进阶](/knowledge?source=token-two)",
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
