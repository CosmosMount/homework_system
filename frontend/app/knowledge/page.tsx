import { AppShell } from "@/components/layout/app-shell";
import { KnowledgeReader } from "@/components/knowledge/knowledge-reader";
import {
  getDashboard,
  getKnowledge,
  getKnowledgeDocument,
  requireUser,
} from "@/lib/api/server";

type KnowledgePageProps = Readonly<{
  searchParams: Promise<{ doc?: string }>;
}>;

export default async function KnowledgePage({
  searchParams,
}: KnowledgePageProps) {
  const [user, dashboard, overview, filters] = await Promise.all([
    requireUser("/knowledge"),
    getDashboard(),
    getKnowledge(),
    searchParams,
  ]);
  const requested = (filters.doc ?? "").trim();
  const selectedId = overview.documents.some((item) => item.id === requested)
    ? requested
    : overview.documents[0]?.id;
  const document = selectedId
    ? await getKnowledgeDocument(selectedId)
    : null;

  return (
    <AppShell fullBleed unreadCount={dashboard.unread_count} user={user}>
      <KnowledgeReader initialDocument={document} overview={overview} />
    </AppShell>
  );
}
