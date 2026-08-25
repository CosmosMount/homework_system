import { AuthShell } from "@/components/auth/auth-shell";
import { RegisterForm } from "@/components/auth/auth-forms";

export default function RegisterPage() {
  return (
    <AuthShell
      description="使用 Connect 学校邮箱注册；验证成功后直接激活，空系统的首个账号自动成为管理员。"
      eyebrow="IDENTITY / REGISTER"
      title="创建校内账号"
    >
      <RegisterForm />
    </AuthShell>
  );
}
