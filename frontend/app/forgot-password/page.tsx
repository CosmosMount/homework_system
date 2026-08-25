import { AuthShell } from "@/components/auth/auth-shell";
import { EmailRequestForm } from "@/components/auth/auth-forms";

export default function ForgotPasswordPage() {
  return (
    <AuthShell
      description="输入校园邮箱。无论账号是否存在，页面都会返回相同结果以保护账号隐私。"
      eyebrow="IDENTITY / RECOVERY"
      title="重置密码"
    >
      <EmailRequestForm mode="reset" />
    </AuthShell>
  );
}
