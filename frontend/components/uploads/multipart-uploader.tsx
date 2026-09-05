"use client";

import { type ChangeEvent, useRef, useState } from "react";

import { ApiError, apiFetch, csrfFetch } from "@/lib/api/client";
import { buttonClassName } from "@/components/ui/form-controls";
import type { CompletedFile, UploadSession } from "@/lib/api/types";
import { createIdempotencyKey } from "@/lib/idempotency";
import {
  digestBase64,
  digestHex,
  hashBlob,
} from "@/lib/sha256";

type PresignResponse = {
  parts: {
    part_number: number;
    url: string;
    checksum_header: "x-amz-checksum-sha256";
  }[];
  expires_in_seconds: number;
};

type PersistedUpload = {
  uploadId: string;
  idempotencyKey: string;
  sha256: string;
};

function messageFor(error: unknown): string {
  return error instanceof ApiError ? error.message : "上传失败，请稍后重试。";
}

function resumeKey(contextId: string, file: File): string {
  return [
    "pnx-upload",
    contextId,
    file.name,
    String(file.size),
    String(file.lastModified),
  ].join(":");
}

function readPersisted(key: string): PersistedUpload | null {
  const raw = window.localStorage.getItem(key);
  if (raw === null) {
    return null;
  }
  try {
    return JSON.parse(raw) as PersistedUpload;
  } catch {
    window.localStorage.removeItem(key);
    return null;
  }
}

export function MultipartUploader({
  contextId,
  purpose,
  accept,
  maxBytes,
  maxSelectedBytes,
  maxSelectedFiles,
  multiple = false,
  heading,
  description,
  onCompleted,
}: Readonly<{
  contextId: string;
  purpose: "announcement_attachment" | "assignment_submission";
  accept: string;
  maxBytes: number;
  maxSelectedBytes?: number;
  maxSelectedFiles?: number;
  multiple?: boolean;
  heading: string;
  description: string;
  onCompleted: (file: CompletedFile) => void;
}>) {
  const [files, setFiles] = useState<File[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const [activeUploadId, setActiveUploadId] = useState<string | null>(null);
  const [resumeStorageKey, setResumeStorageKey] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("等待选择文件");
  const [error, setError] = useState<string | null>(null);
  const selectedByteLimit = maxSelectedBytes ?? maxBytes;
  const selectedFileLimit = maxSelectedFiles ?? (multiple ? 100 : 1);

  function rejectSelection(message: string) {
    setFiles([]);
    setStage("等待重新选择");
    setError(message);
    if (inputRef.current !== null) {
      inputRef.current.value = "";
    }
  }

  function chooseFiles(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files ?? []);
    setActiveUploadId(null);
    setResumeStorageKey(null);
    setProgress(0);
    setError(null);

    if (selected.length > selectedFileLimit) {
      rejectSelection("所选文件数量超过本版本当前可添加的附件数量。");
      return;
    }
    if (selected.some((file) => file.size > maxBytes)) {
      rejectSelection("所选文件中有文件超过当前资源允许的单文件大小上限。");
      return;
    }
    if (
      selected.reduce((total, file) => total + file.size, 0) >
      selectedByteLimit
    ) {
      rejectSelection("所选文件合计超过本版本当前剩余大小上限。");
      return;
    }

    setFiles(selected);
    setStage(selected.length === 0 ? "等待选择文件" : "等待开始");
  }

  async function uploadFile(
    file: File,
    fileIndex: number,
    fileCount: number,
  ): Promise<CompletedFile> {
    const prefix = fileCount > 1 ? fileIndex + 1 + "/" + fileCount + " · " : "";
    const updateFileProgress = (fileProgress: number) => {
      setProgress(
        Math.round(((fileIndex + fileProgress / 100) / fileCount) * 100),
      );
    };

    setStage(prefix + "正在流式计算完整 SHA-256");
    const fullDigest = await hashBlob(file, (processed) => {
      updateFileProgress(
        file.size === 0 ? 20 : Math.round((processed / file.size) * 20),
      );
    });
    const sha256 = digestHex(fullDigest);
    const key = resumeKey(contextId, file);
    setResumeStorageKey(key);
    let persisted = readPersisted(key);
    let upload: UploadSession | null = null;

    if (persisted !== null && persisted.sha256 === sha256) {
      try {
        upload = await apiFetch<UploadSession>(
          "/uploads/" + persisted.uploadId,
        );
        setStage(prefix + "已恢复上次上传会话");
      } catch (nextError) {
        if (!(nextError instanceof ApiError) || nextError.status !== 404) {
          throw nextError;
        }
        window.localStorage.removeItem(key);
        persisted = null;
      }
    }

    if (upload === null) {
      const idempotencyKey =
        persisted?.idempotencyKey ?? createIdempotencyKey();
      upload = await csrfFetch<UploadSession>("/uploads/init", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({
          purpose,
          context_id: contextId,
          file_name: file.name,
          size_bytes: file.size,
          media_type: file.type || "application/octet-stream",
          sha256,
        }),
      });
      persisted = {
        uploadId: upload.upload_id,
        idempotencyKey,
        sha256,
      };
      window.localStorage.setItem(key, JSON.stringify(persisted));
    }

    setActiveUploadId(upload.upload_id);
    if (upload.status === "available") {
      window.localStorage.removeItem(key);
      updateFileProgress(100);
      return {
        file_id: upload.file_id,
        status: upload.status,
        file_name: file.name,
        size_bytes: file.size,
        media_type: file.type || "application/octet-stream",
        sha256,
      };
    }

    const completedParts = new Map(
      upload.uploaded_parts
        .filter((part) => part.etag && part.checksum_sha256)
        .map((part) => [part.part_number, part]),
    );
    const missingNumbers = Array.from(
      { length: upload.part_count },
      (_, index) => index + 1,
    ).filter((partNumber) => !completedParts.has(partNumber));

    for (let offset = 0; offset < missingNumbers.length; offset += 10) {
      const partBatch = missingNumbers.slice(offset, offset + 10);
      const presigned = await csrfFetch<PresignResponse>(
        "/uploads/" + upload.upload_id + "/parts/presign",
        {
          method: "POST",
          body: JSON.stringify({ part_numbers: partBatch }),
        },
      );
      for (const part of presigned.parts) {
        setStage(
          prefix +
            "正在上传分片 " +
            part.part_number +
            " / " +
            upload.part_count,
        );
        const startByte = (part.part_number - 1) * upload.part_size_bytes;
        const blob = file.slice(
          startByte,
          Math.min(startByte + upload.part_size_bytes, file.size),
        );
        const checksum = digestBase64(await hashBlob(blob));
        const response = await fetch(part.url, {
          method: "PUT",
          body: blob,
          credentials: "omit",
          headers: {
            [part.checksum_header]: checksum,
          },
        });
        if (!response.ok) {
          throw new Error("对象存储拒绝了分片 " + part.part_number + "。");
        }
        const etag = response.headers.get("etag");
        if (etag === null) {
          throw new Error("对象存储响应缺少 ETag。");
        }
        completedParts.set(part.part_number, {
          part_number: part.part_number,
          etag,
          checksum_sha256: checksum,
          size_bytes: blob.size,
        });
        updateFileProgress(
          20 + Math.round((completedParts.size / upload.part_count) * 75),
        );
      }
    }

    setStage(prefix + "正在完成并校验文件");
    const completed = await csrfFetch<CompletedFile>(
      "/uploads/" + upload.upload_id + "/complete",
      {
        method: "POST",
        headers: { "Idempotency-Key": createIdempotencyKey() },
        body: JSON.stringify({
          parts: Array.from(completedParts.values())
            .sort((left, right) => left.part_number - right.part_number)
            .map((part) => ({
              part_number: part.part_number,
              etag: part.etag,
              checksum_sha256: part.checksum_sha256,
            })),
          sha256,
        }),
      },
    );
    window.localStorage.removeItem(key);
    updateFileProgress(100);
    return completed;
  }

  async function start() {
    if (files.length === 0) {
      setError("请先选择文件。");
      return;
    }
    if (files.length > selectedFileLimit) {
      setError("所选文件数量超过本版本当前可添加的附件数量。");
      return;
    }
    if (files.some((file) => file.size > maxBytes)) {
      setError("所选文件中有文件超过当前资源允许的单文件大小上限。");
      return;
    }
    if (
      files.reduce((total, file) => total + file.size, 0) > selectedByteLimit
    ) {
      setError("所选文件合计超过本版本当前剩余大小上限。");
      return;
    }

    const batch = files;
    setPending(true);
    setError(null);
    setProgress(0);
    for (let fileIndex = 0; fileIndex < batch.length; fileIndex += 1) {
      const file = batch[fileIndex];
      if (file === undefined) {
        continue;
      }
      try {
        const completed = await uploadFile(file, fileIndex, batch.length);
        onCompleted(completed);
        setFiles(batch.slice(fileIndex + 1));
        setActiveUploadId(null);
        setResumeStorageKey(null);
      } catch (nextError) {
        setFiles(batch.slice(fileIndex));
        setError(file.name + "：" + messageFor(nextError));
        setStage(
          (batch.length > 1
            ? fileIndex + 1 + "/" + batch.length + " · "
            : "") + "上传已暂停，可重新开始以恢复",
        );
        setPending(false);
        return;
      }
    }

    setProgress(100);
    setStage(
      batch.length > 1
        ? batch.length + " 个文件上传和服务端校验均已完成"
        : "上传和服务端校验均已完成",
    );
    if (inputRef.current !== null) {
      inputRef.current.value = "";
    }
    setPending(false);
  }

  async function abort() {
    if (activeUploadId === null) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      await csrfFetch("/uploads/" + activeUploadId, { method: "DELETE" });
      if (resumeStorageKey !== null) {
        window.localStorage.removeItem(resumeStorageKey);
      }
      setActiveUploadId(null);
      setResumeStorageKey(null);
      setProgress(0);
      setStage("当前文件上传已终止，可重新开始所选文件");
    } catch (nextError) {
      setError(messageFor(nextError));
    } finally {
      setPending(false);
    }
  }

  const actionLabel = activeUploadId
    ? files.length > 1
      ? "继续上传 " + files.length + " 个文件"
      : "继续上传"
    : files.length > 1
      ? "开始上传 " + files.length + " 个文件"
      : "开始上传";

  return (
    <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <h3 className="text-lg font-medium">{heading}</h3>
      <p className="mt-2 text-xs text-[var(--color-text-muted)]">
        {description}
      </p>
      <input
        accept={accept}
        className="mt-4 block w-full text-sm"
        disabled={pending || selectedFileLimit === 0}
        multiple={multiple}
        onChange={chooseFiles}
        ref={inputRef}
        type="file"
      />
      {files.length > 1 ? (
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">
          已选择 {files.length} 个文件，将按选择顺序逐个上传。
        </p>
      ) : null}
      <div className="mt-4 h-2 bg-[var(--color-bg)]" role="progressbar" aria-valuemax={100} aria-valuemin={0} aria-valuenow={progress}>
        <div
          className="h-full bg-[var(--color-accent-fill)] transition-[width]"
          style={{ width: progress + "%" }}
        />
      </div>
      <p className="mt-2 text-xs text-[var(--color-text-muted)]">{stage}</p>
      {error ? (
        <p aria-live="polite" className="mt-3 text-sm text-[var(--color-danger)]">
          {error}
        </p>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-3">
        <button
          className={buttonClassName + " disabled:opacity-55"}
          disabled={pending || files.length === 0}
          onClick={start}
          type="button"
        >
          {pending ? "处理中…" : actionLabel}
        </button>
        {activeUploadId ? (
          <button
            className="min-h-11 border border-[var(--color-border-strong)] px-5 disabled:opacity-55"
            disabled={pending}
            onClick={abort}
            type="button"
          >
            终止上传
          </button>
        ) : null}
      </div>
    </section>
  );
}
