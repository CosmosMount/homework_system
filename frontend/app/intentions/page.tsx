import Link from "next/link";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { getDashboard, getIntentions, requireUser } from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

export default async function IntentionsPage() {
  const [user, dashboard, surveys] = await Promise.all([
    requireUser(),
    getDashboard(),
    getIntentions(),
  ]);
  if (isAdminView(user)) {
    redirect("/admin/intentions");
  }

  return (
    <AppShell user={user} unreadCount={dashboard.unread_count}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        STUDENT / QUESTIONNAIRES
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">问卷</h1>
      <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
        填写当前开放的问卷，帮助管理员安排培训和组队；每份问卷会标明可提交次数。
      </p>

      {surveys.items.length > 0 ? (
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {surveys.items.map((survey) => (
            <Link
              className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:border-[var(--color-accent)]"
              href={"/intentions/" + survey.id}
              key={survey.id}
            >
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-xl font-semibold">{survey.title}</h2>
                <span className="rounded-full bg-[var(--color-action-fill)] px-2.5 py-1 text-xs text-[var(--color-action-text)]">
                  {survey.max_submissions !== null &&
                  survey.submissions_used >= survey.max_submissions
                    ? "已达上限"
                    : survey.has_response
                      ? "已提交"
                      : "待填写"}
                </span>
              </div>
              <p className="mt-3 text-sm text-[var(--color-text-secondary)]">
                {survey.question_count} 道题 · 已提交 {survey.submissions_used} 次 ·{" "}
                {survey.max_submissions === null
                  ? "不限次数"
                  : "最多 " + survey.max_submissions + " 次"}
              </p>
              {survey.ends_at ? (
                <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                  截止 {formatDateTime(survey.ends_at)}
                </p>
              ) : null}
            </Link>
          ))}
        </div>
      ) : (
        <section className="mt-8 rounded-2xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface)] p-10 text-center text-sm text-[var(--color-text-muted)]">
          当前没有开放的问卷。
        </section>
      )}
    </AppShell>
  );
}
