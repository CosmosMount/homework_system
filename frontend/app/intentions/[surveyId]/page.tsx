import { notFound } from "next/navigation";

import { SafeHtml } from "@/components/announcements/safe-html";
import { IntentionForm } from "@/components/intentions/intention-form";
import { AppShell } from "@/components/layout/app-shell";
import { getDashboard, getIntention, requireUser } from "@/lib/api/server";

type IntentionDetailPageProps = Readonly<{
  params: Promise<{ surveyId: string }>;
  searchParams: Promise<{ token?: string }>;
}>;

export default async function IntentionDetailPage({
  params,
  searchParams,
}: IntentionDetailPageProps) {
  const [{ surveyId }, filters] = await Promise.all([params, searchParams]);
  const token = (filters.token ?? "").slice(0, 256);
  const returnQuery = token ? "?token=" + encodeURIComponent(token) : "";
  const user = await requireUser("/intentions/" + surveyId + returnQuery);
  const [dashboard, survey] = await Promise.all([
    getDashboard(),
    getIntention(surveyId, token),
  ]);
  if (survey === null) {
    notFound();
  }

  return (
    <AppShell user={user} unreadCount={dashboard.unread_count}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        STUDENT / QUESTIONNAIRES
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">
        {survey.title}
      </h1>
      <div className="mt-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <SafeHtml sanitizedHtml={survey.description_html} />
      </div>
      <IntentionForm initialSurvey={survey} />
    </AppShell>
  );
}
