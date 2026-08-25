"use client";

import { MultipartUploader } from "@/components/uploads/multipart-uploader";
import type { CompletedFile } from "@/lib/api/types";

export function AnnouncementUploader({
  announcementId,
  onCompleted,
}: Readonly<{
  announcementId: string;
  onCompleted: (file: CompletedFile) => void;
}>) {
  return (
    <MultipartUploader
      accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.zip,.7z,.mp4,.webm"
      contextId={announcementId}
      description="文件直传私有对象存储；刷新后选择同一文件可恢复已完成分片。完成后仍需保存通知才能正式绑定。"
      heading="添加通知附件"
      maxBytes={2_147_483_648}
      onCompleted={onCompleted}
      purpose="announcement_attachment"
    />
  );
}
