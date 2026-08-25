import { AuthShell } from "@/components/auth/auth-shell";
import { EmailRequestForm } from "@/components/auth/auth-forms";

export default function ResendVerificationPage() {
  return (
    <AuthShell
      description="重新发送验证邮件。页面不会确认某个邮箱是否已经注册。"
      eyebrow="IDENTITY / VERIFY"
      title="重发验证邮件"
    >
      <EmailRequestForm mode="resend" />
    </AuthShell>
  );
}
