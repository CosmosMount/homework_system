import { redirect } from "next/navigation";

import { requireAdmin } from "@/lib/api/server";

type LegacyAdminTeamPageProps = Readonly<{
  params: Promise<{ competitionId: string; teamId: string }>;
}>;

export default async function LegacyAdminTeamPage({
  params,
}: LegacyAdminTeamPageProps) {
  const [{ teamId }] = await Promise.all([params, requireAdmin()]);
  redirect("/admin/competitions/" + teamId);
}
