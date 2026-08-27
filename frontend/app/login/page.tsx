import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/auth-forms";
import { safeReturnPath } from "@/lib/safe-return-path";

type LoginPageProps = Readonly<{
  searchParams?: Promise<{ next?: string }>;
}>;

export default async function LoginPage({ searchParams }: LoginPageProps = {}) {
  const filters = searchParams ? await searchParams : {};
  return (
    <AuthShell
      description="使用经过验证的香港科技大学（广州）校园邮箱进入内部平台。"
      eyebrow="IDENTITY / LOGIN"
      title="登录训练平台"
    >
      <LoginForm returnTo={safeReturnPath(filters.next)} />
    </AuthShell>
  );
}
