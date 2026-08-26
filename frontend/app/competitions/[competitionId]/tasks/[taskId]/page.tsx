import { redirect } from "next/navigation";

import { requireUser } from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";

type CompetitionTaskPageProps = Readonly<{
  params: Promise<{ competitionId: string; taskId: string }>;
}>;

export default async function CompetitionTaskPage({
  params,
}: CompetitionTaskPageProps) {
  const { competitionId } = await params;
  const user = await requireUser();
  redirect(
    isAdminView(user)
      ? "/admin/competitions/" + competitionId
      : "/competitions/" + competitionId,
  );
}
