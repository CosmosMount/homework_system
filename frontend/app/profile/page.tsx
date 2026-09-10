import { ProfileEditor } from "@/components/admin/profile-editor";
import { AppShell } from "@/components/layout/app-shell";
import { AccountDeletion } from "@/components/profile/account-deletion";
import { DirectionSelector } from "@/components/profile/direction-selector";
import { getDashboard, getSelfDirectionOptions, requireUser } from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";

export default async function ProfilePage() {
  const user = await requireUser();
  const dashboard = isAdminView(user) ? null : await getDashboard();
  const directionOptions = user.role === "student" ? await getSelfDirectionOptions() : null;
  const items = [
    ["真实姓名", user.full_name],
    ["学号", user.student_number],
    ["校园邮箱", user.email],
    ["角色", isAdminView(user) ? "管理员" : "学生"],
    ["账号状态", user.status === "active" ? "已激活" : user.status],
    ["技术方向", user.direction?.name ?? "未设置"],
  ];
  return (
    <AppShell unreadCounts={dashboard?.unread_counts} user={user}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        ACCOUNT / PROFILE
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">个人资料</h1>
      <p className="mt-3 text-[var(--color-text-secondary)]">
        {isAdminView(user)
          ? "管理员可以维护自己的姓名、学号和校园邮箱；修改邮箱后需要重新验证。"
          : "邮箱和学号由管理员维护；技术方向在管理员开放权限后可自行修改，未设置方向不影响登录。"}
      </p>
      <dl className="mt-8 grid gap-px border border-[var(--color-border)] bg-[var(--color-border)] sm:grid-cols-2">
        {items.map(([label, value]) => (
          <div className="bg-[var(--color-surface)] p-5" key={label}>
            <dt className="text-sm text-[var(--color-text-muted)]">{label}</dt>
            <dd className="mt-1 break-words">{value}</dd>
          </div>
        ))}
      </dl>
      {isAdminView(user) ? <ProfileEditor initialUser={user} /> : null}
      {directionOptions ? <DirectionSelector key={user.revision} user={user} options={directionOptions} /> : null}
      <AccountDeletion user={user} />
    </AppShell>
  );
}
