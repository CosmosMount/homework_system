import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { VerifyEmailForm } from "@/components/auth/auth-forms";
import { FormMessage } from "@/components/ui/form-controls";

export const metadata: Metadata = {
  title: "验证校园邮箱",
  referrer: "no-referrer",
};

type VerifyEmailPageProps = {
  searchParams: Promise<{ token?: string | string[] }>;
};

export default async function VerifyEmailPage({
  searchParams,
}: VerifyEmailPageProps) {
  const tokenValue = (await searchParams).token;
  const token = Array.isArray(tokenValue) ? tokenValue[0] : tokenValue;
  return (
    <AuthShell
      description="验证成功后账号将直接进入 active 状态，不需要审批或分组。"
      eyebrow="IDENTITY / VERIFY"
      title="验证校园邮箱"
    >
      {token ? (
        <VerifyEmailForm token={token} />
      ) : (
        <FormMessage>验证链接缺少令牌，请重新发送验证邮件。</FormMessage>
      )}
    </AuthShell>
  );
}
