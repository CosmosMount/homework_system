import { AppShell } from "@/components/layout/app-shell";
import { MaterialLedger } from "@/components/materials/material-ledger";
import { requireUser } from "@/lib/api/server";

export default async function MaterialsPage({ searchParams }: Readonly<{
  searchParams: Promise<{ q?: string; tech_group?: string; status?: string; page?: string }>;
}>) {
  const user = await requireUser("/materials");
  const filters = await searchParams;
  return <AppShell user={user}><MaterialLedger filters={filters} /></AppShell>;
}
