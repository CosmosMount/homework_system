import { AuthShell } from "@/components/auth/auth-shell";
import { LoginFormSkeleton } from "@/components/auth/login-form-skeleton";

export default function LoginPage() {
  return (
    <AuthShell
      description="使用经过验证的香港科技大学（广州）校园邮箱进入内部平台。"
      eyebrow="IDENTITY / LOGIN"
      title="登录训练平台"
    >
      <LoginFormSkeleton />
    </AuthShell>
  );
}
