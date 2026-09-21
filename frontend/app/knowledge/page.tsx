import { AppShell } from "@/components/layout/app-shell";
import { KnowledgeReader } from "@/components/knowledge/knowledge-reader";
import {
  getDashboard,
  getKnowledge,
  getKnowledgeDocument,
  requireUser,
} from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";

type KnowledgePageProps = Readonly<{
  searchParams: Promise<{ doc?: string; source?: string }>;
}>;

export default async function KnowledgePage({
  searchParams,
}: KnowledgePageProps) {
  const user = await requireUser("/knowledge");
  const [dashboard, overview, filters] = await Promise.all([
    getDashboard(),
    getKnowledge(),
    searchParams,
  ]);
  const requested = (filters.doc ?? "").trim();
  const source = (filters.source ?? "").trim();
  const selectedId = overview.documents.some((item) => item.id === requested)
    ? requested
    : overview.documents.find((item) => item.source_token === source)?.id;
  const document = selectedId
    ? await getKnowledgeDocument(selectedId)
    : null;

  return (
    <AppShell fullBleed unreadCounts={dashboard.unread_counts} user={user}>
      <KnowledgeReader
        allowFeishuSourceLinks={isAdminView(user)}
        initialDocument={document}
        overview={overview}
      />
    </AppShell>
  );
}
