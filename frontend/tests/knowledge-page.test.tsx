import { beforeEach, describe, expect, it, vi } from "vitest";

import KnowledgePage from "@/app/knowledge/page";

const {
  getDashboardMock,
  getKnowledgeDocumentMock,
  getKnowledgeMock,
  requireUserMock,
} = vi.hoisted(() => ({
  getDashboardMock: vi.fn(),
  getKnowledgeDocumentMock: vi.fn(),
  getKnowledgeMock: vi.fn(),
  requireUserMock: vi.fn(),
}));

vi.mock("@/lib/api/server", () => ({
  getDashboard: getDashboardMock,
  getKnowledge: getKnowledgeMock,
  getKnowledgeDocument: getKnowledgeDocumentMock,
  requireUser: requireUserMock,
}));

describe("knowledge page", () => {
  beforeEach(() => {
    getDashboardMock.mockReset();
    getKnowledgeDocumentMock.mockReset();
    getKnowledgeMock.mockReset();
    requireUserMock.mockReset();
  });

  it("finishes the return-aware authentication guard before protected reads", async () => {
    requireUserMock.mockRejectedValue(new Error("NEXT_REDIRECT"));

    await expect(
      KnowledgePage({ searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("NEXT_REDIRECT");

    expect(requireUserMock).toHaveBeenCalledWith("/knowledge");
    expect(getDashboardMock).not.toHaveBeenCalled();
    expect(getKnowledgeMock).not.toHaveBeenCalled();
    expect(getKnowledgeDocumentMock).not.toHaveBeenCalled();
  });

  it("keeps the default page at the root directory without loading the first document", async () => {
    requireUserMock.mockResolvedValue({ role: "student" });
    getDashboardMock.mockResolvedValue({ unread_counts: {} });
    getKnowledgeMock.mockResolvedValue({
      snapshot: {
        run_id: "run-1",
        synced_at: "2026-08-31T00:00:00Z",
        source_url: "https://pnx.feishu.cn/wiki/",
        document_count: 1,
        asset_count: 0,
      },
      nodes: [],
      documents: [{
        id: "document-1",
        title: "培训课时安排",
        source_url: "https://pnx.feishu.cn/wiki/document-1",
        source_token: "document-1",
        display_order: 0,
      }],
    });

    await expect(
      KnowledgePage({ searchParams: Promise.resolve({}) }),
    ).resolves.toBeDefined();

    expect(getKnowledgeDocumentMock).not.toHaveBeenCalled();
  });
});
