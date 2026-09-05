import { redirect } from "next/navigation";

import { requireAdmin } from "@/lib/api/server";

export default async function NewCompetitionPage() {
  await requireAdmin();
  redirect("/admin/competitions");
}
