import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { ResetPasswordForm } from "@/components/auth/auth-forms";
import { FormMessage } from "@/components/ui/form-controls";

export const metadata: Metadata = {
  title: "设置新密码",
  referrer: "no-referrer",
};

type ResetPasswordPageProps = {
  searchParams: Promise<{ token?: string | string[] }>;
};

export default async function ResetPasswordPage({
  searchParams,
}: ResetPasswordPageProps) {
  const tokenValue = (await searchParams).token;
  const token = Array.isArray(tokenValue) ? tokenValue[0] : tokenValue;
  return (
    <AuthShell
      description="新密码生效后，账号原有登录设备将全部退出。"
      eyebrow="IDENTITY / RECOVERY"
      title="设置新密码"
    >
      {token ? (
        <ResetPasswordForm token={token} />
      ) : (
        <FormMessage>重置链接缺少令牌，请重新申请密码重置。</FormMessage>
      )}
    </AuthShell>
  );
}
