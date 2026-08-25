import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MultipartUploader } from "@/components/uploads/multipart-uploader";

const {
  apiFetchMock,
  csrfFetchMock,
  digestBase64Mock,
  digestHexMock,
  hashBlobMock,
} = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  csrfFetchMock: vi.fn(),
  digestBase64Mock: vi.fn(() => "part-checksum"),
  digestHexMock: vi.fn(() => "full-sha256"),
  hashBlobMock: vi.fn(async () => new Uint8Array([1, 2, 3])),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiFetch: apiFetchMock,
  csrfFetch: csrfFetchMock,
}));

vi.mock("@/lib/sha256", () => ({
  digestBase64: digestBase64Mock,
  digestHex: digestHexMock,
  hashBlob: hashBlobMock,
}));

describe("assignment multipart upload", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    csrfFetchMock.mockReset();
    hashBlobMock.mockClear();
    digestBase64Mock.mockClear();
    digestHexMock.mockClear();
    window.localStorage.clear();
  });

  it("sends assignment purpose and completes a multipart upload", async () => {
    const onCompleted = vi.fn();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(null, { status: 200, headers: { etag: "etag-1" } }),
      );
    csrfFetchMock
      .mockResolvedValueOnce({
        upload_id: "upload-1",
        file_id: "file-1",
        status: "uploading",
        part_size_bytes: 3,
        part_count: 1,
        uploaded_parts: [],
        expires_at: "2026-08-25T00:00:00Z",
        failure_code: null,
      })
      .mockResolvedValueOnce({
        parts: [
          {
            part_number: 1,
            url: "https://object.test/part-1",
            checksum_header: "x-amz-checksum-sha256",
          },
        ],
        expires_in_seconds: 900,
      })
      .mockResolvedValueOnce({
        file_id: "file-1",
        status: "available",
        file_name: "answer.pdf",
        size_bytes: 3,
        media_type: "application/pdf",
        sha256: "full-sha256",
      });

    const { container } = render(
      <MultipartUploader
        accept=".pdf"
        contextId="assignment-1"
        description="只允许 PDF"
        heading="上传作业附件"
        maxBytes={1024}
        onCompleted={onCompleted}
        purpose="assignment_submission"
      />,
    );
    const input = container.querySelector<HTMLInputElement>(
      'input[type="file"]',
    );
    expect(input).not.toBeNull();
    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [
          new File([new Uint8Array([1, 2, 3])], "answer.pdf", {
            type: "application/pdf",
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始上传" }));

    await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(1));
    expect(csrfFetchMock.mock.calls[0]?.[0]).toBe("/uploads/init");
    expect(
      JSON.parse(String(csrfFetchMock.mock.calls[0]?.[1]?.body)),
    ).toMatchObject({
      purpose: "assignment_submission",
      context_id: "assignment-1",
      file_name: "answer.pdf",
    });
    expect(csrfFetchMock.mock.calls[1]?.[0]).toBe(
      "/uploads/upload-1/parts/presign",
    );
    expect(csrfFetchMock.mock.calls[2]?.[0]).toBe(
      "/uploads/upload-1/complete",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "https://object.test/part-1",
      expect.objectContaining({
        method: "PUT",
        credentials: "omit",
      }),
    );
  });
});
