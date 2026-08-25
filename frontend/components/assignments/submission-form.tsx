"use client";

import { type FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { MultipartUploader } from "@/components/uploads/multipart-uploader";
import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type {
  CompletedFile,
  SubmissionVersionCreated,
} from "@/lib/api/types";
import { formatFileSize } from "@/lib/format";
import { createIdempotencyKey } from "@/lib/idempotency";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "提交失败，请稍后重试。";
}

type VersionSubmissionFormProps = Readonly<{
  allowedExtensions: string[];
  maxTotalBytes: number;
}> &
  (
    | Readonly<{ assignmentId: string }>
    | Readonly<{ competitionId: string; taskId: string }>
  );

export function AssignmentSubmissionForm(props: VersionSubmissionFormProps) {
  const { allowedExtensions, maxTotalBytes } = props;
  const isCompetition = "competitionId" in props;
  const contextId = isCompetition ? props.taskId : props.assignmentId;
  const resourceLabel = isCompetition ? "赛题" : "作业";
  const submitPath = isCompetition
    ? "/competitions/" +
      props.competitionId +
      "/tasks/" +
      props.taskId +
      "/submission-versions"
    : "/assignments/" + props.assignmentId + "/submission-versions";
  const router = useRouter();
  const [textMarkdown, setTextMarkdown] = useState("");
  const [externalUrl, setExternalUrl] = useState("");
  const [files, setFiles] = useState<CompletedFile[]>([]);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const totalBytes = files.reduce((total, file) => total + file.size_bytes, 0);
  const accept = useMemo(
    () => allowedExtensions.map((extension) => "." + extension).join(","),
    [allowedExtensions],
  );

  function addCompletedFile(file: CompletedFile) {
    setError(null);
    setFiles((current) => {
      if (current.some((item) => item.file_id === file.file_id)) {
        return current;
      }
      const nextTotal =
        current.reduce((total, item) => total + item.size_bytes, 0) +
        file.size_bytes;
      if (nextTotal > maxTotalBytes) {
        setError(
          "已上传附件合计超过本" +
            resourceLabel +
            "上限；该文件不会加入本次正式版本。",
        );
        return current;
      }
      return [...current, file];
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    if (!textMarkdown.trim() && !externalUrl.trim() && files.length === 0) {
      setError("文本、外部链接和附件至少需要一种。");
      return;
    }
    if (totalBytes > maxTotalBytes) {
      setError("附件合计超过本" + resourceLabel + "上限。");
      return;
    }
    if (
      !window.confirm(
        isCompetition
          ? "确认代表整个团队创建正式版本？版本不可修改或删除，之后的更正需要创建新版本。"
          : "确认创建正式版本？正式版本不可修改或删除，之后的更正需要创建新版本。",
      )
    ) {
      return;
    }

    setPending(true);
    try {
      const created = await csrfFetch<SubmissionVersionCreated>(submitPath, {
        method: "POST",
        headers: { "Idempotency-Key": createIdempotencyKey() },
        body: JSON.stringify({
          text_markdown: textMarkdown.trim() || null,
          external_url: externalUrl.trim() || null,
          file_ids: files.map((file) => file.file_id),
        }),
      });
      setMessage("正式版本 v" + created.version_number + " 已创建。");
      router.push(
        isCompetition
          ? "/competitions/" +
              props.competitionId +
              "/tasks/" +
              props.taskId +
              "#version-" +
              created.version_id
          : "/assignments/" +
              props.assignmentId +
              "/submissions/" +
              created.submission_id,
      );
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="mt-8 space-y-6" onSubmit={submit}>
      <section className="space-y-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
        <div>
          <p className="font-mono text-xs text-[var(--color-accent)]">
            NEW IMMUTABLE VERSION
          </p>
          <h2 className="mt-2 text-2xl font-semibold">
            {isCompetition ? "代表团队创建正式版本" : "创建正式版本"}
          </h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            可提交 Markdown 文本、HTTP(S) 外部链接或附件，至少选择一种。
            {isCompetition ? " 本次提交代表整个团队。" : null}
          </p>
        </div>
        {message ? <FormMessage tone="success">{message}</FormMessage> : null}
        {error ? <FormMessage>{error}</FormMessage> : null}
        <label className="block text-sm font-medium">
          Markdown 文本
          <textarea
            className={inputClassName + " min-h-52 py-3 font-mono text-sm"}
            disabled={pending}
            maxLength={200000}
            onChange={(event) => setTextMarkdown(event.target.value)}
            value={textMarkdown}
          />
        </label>
        <label className="block text-sm font-medium">
          外部链接
          <input
            className={inputClassName}
            disabled={pending}
            maxLength={2000}
            onChange={(event) => setExternalUrl(event.target.value)}
            placeholder="https://..."
            type="url"
            value={externalUrl}
          />
        </label>
      </section>

      <MultipartUploader
        accept={accept}
        contextId={contextId}
        description={
          "允许扩展名：" +
          allowedExtensions.join(", ") +
          "。刷新后重新选择同一文件可恢复分片。"
        }
        heading={"上传" + resourceLabel + "附件"}
        maxBytes={maxTotalBytes}
        onCompleted={addCompletedFile}
        purpose={isCompetition ? "competition_submission" : "assignment_submission"}
      />

      {files.length ? (
        <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-lg font-medium">本版本附件</h3>
            <span className="font-mono text-xs text-[var(--color-text-muted)]">
              {formatFileSize(totalBytes)} / {formatFileSize(maxTotalBytes)}
            </span>
          </div>
          <div className="mt-4 space-y-2">
            {files.map((file) => (
              <div
                className="flex flex-wrap items-center justify-between gap-3 border border-[var(--color-border)] p-3"
                key={file.file_id}
              >
                <span className="text-sm">
                  {file.file_name} · {formatFileSize(file.size_bytes)}
                </span>
                <button
                  className="text-sm text-[var(--color-danger)]"
                  disabled={pending}
                  onClick={() =>
                    setFiles((current) =>
                      current.filter((item) => item.file_id !== file.file_id),
                    )
                  }
                  type="button"
                >
                  从本版本移除
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <button className={buttonClassName} disabled={pending} type="submit">
        {pending ? "正在创建正式版本…" : "确认并创建正式版本"}
      </button>
    </form>
  );
}

export const CompetitionSubmissionForm = AssignmentSubmissionForm;
