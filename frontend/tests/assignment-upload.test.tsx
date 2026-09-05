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
    vi.restoreAllMocks();
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

  it("uploads multiple selected assignment images in order", async () => {
    const onCompleted = vi.fn();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(null, { status: 200, headers: { etag: "etag-part" } }),
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
            url: "https://object.test/image-1",
            checksum_header: "x-amz-checksum-sha256",
          },
        ],
        expires_in_seconds: 900,
      })
      .mockResolvedValueOnce({
        file_id: "file-1",
        status: "available",
        file_name: "front.png",
        size_bytes: 3,
        media_type: "image/png",
        sha256: "full-sha256",
      })
      .mockResolvedValueOnce({
        upload_id: "upload-2",
        file_id: "file-2",
        status: "uploading",
        part_size_bytes: 4,
        part_count: 1,
        uploaded_parts: [],
        expires_at: "2026-08-25T00:00:00Z",
        failure_code: null,
      })
      .mockResolvedValueOnce({
        parts: [
          {
            part_number: 1,
            url: "https://object.test/image-2",
            checksum_header: "x-amz-checksum-sha256",
          },
        ],
        expires_in_seconds: 900,
      })
      .mockResolvedValueOnce({
        file_id: "file-2",
        status: "available",
        file_name: "back.jpg",
        size_bytes: 4,
        media_type: "image/jpeg",
        sha256: "full-sha256",
      });

    const { container } = render(
      <MultipartUploader
        accept=".png,.jpg"
        contextId="assignment-1"
        description="允许多张图片"
        heading="上传作业附件"
        maxBytes={1024}
        maxSelectedBytes={1024}
        maxSelectedFiles={100}
        multiple
        onCompleted={onCompleted}
        purpose="assignment_submission"
      />,
    );
    const input = container.querySelector<HTMLInputElement>(
      'input[type="file"]',
    );
    expect(input).not.toBeNull();
    expect(input).toHaveAttribute("multiple");

    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [
          new File([new Uint8Array([1, 2, 3])], "front.png", {
            type: "image/png",
          }),
          new File([new Uint8Array([4, 5, 6, 7])], "back.jpg", {
            type: "image/jpeg",
          }),
        ],
      },
    });
    expect(
      screen.getByText("已选择 2 个文件，将按选择顺序逐个上传。"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "开始上传 2 个文件" }),
    );

    await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(2));
    expect(onCompleted.mock.calls.map(([file]) => file.file_name)).toEqual([
      "front.png",
      "back.jpg",
    ]);
    expect(
      JSON.parse(String(csrfFetchMock.mock.calls[0]?.[1]?.body)),
    ).toMatchObject({ file_name: "front.png" });
    expect(
      JSON.parse(String(csrfFetchMock.mock.calls[3]?.[1]?.body)),
    ).toMatchObject({ file_name: "back.jpg" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(
      screen.getByText("2 个文件上传和服务端校验均已完成"),
    ).toBeInTheDocument();
  });

  it("rejects a batch over the remaining version size before upload init", () => {
    const onCompleted = vi.fn();
    const { container } = render(
      <MultipartUploader
        accept=".png,.jpg"
        contextId="assignment-1"
        description="允许多张图片"
        heading="上传作业附件"
        maxBytes={1024}
        maxSelectedBytes={5}
        maxSelectedFiles={100}
        multiple
        onCompleted={onCompleted}
        purpose="assignment_submission"
      />,
    );
    const input = container.querySelector<HTMLInputElement>(
      'input[type="file"]',
    );
    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [
          new File([new Uint8Array([1, 2, 3])], "front.png", {
            type: "image/png",
          }),
          new File([new Uint8Array([4, 5, 6])], "back.jpg", {
            type: "image/jpeg",
          }),
        ],
      },
    });

    expect(
      screen.getByText("所选文件合计超过本版本当前剩余大小上限。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始上传" })).toBeDisabled();
    expect(csrfFetchMock).not.toHaveBeenCalled();
    expect(onCompleted).not.toHaveBeenCalled();
  });


  it("rejects a batch over the remaining attachment count before upload init", () => {
    const { container } = render(
      <MultipartUploader
        accept=".png,.jpg"
        contextId="assignment-1"
        description="允许多张图片"
        heading="上传作业附件"
        maxBytes={1024}
        maxSelectedFiles={1}
        multiple
        onCompleted={vi.fn()}
        purpose="assignment_submission"
      />,
    );
    const input = container.querySelector<HTMLInputElement>(
      'input[type="file"]',
    );
    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [
          new File([new Uint8Array([1])], "front.png", {
            type: "image/png",
          }),
          new File([new Uint8Array([2])], "back.jpg", {
            type: "image/jpeg",
          }),
        ],
      },
    });

    expect(
      screen.getByText("所选文件数量超过本版本当前可添加的附件数量。"),
    ).toBeInTheDocument();
    expect(csrfFetchMock).not.toHaveBeenCalled();
  });
});
