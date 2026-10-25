import { AppShell } from "@/components/layout/app-shell";
import { MaterialInformation } from "@/components/materials/material-information";
import { requireUser } from "@/lib/api/server";

export default async function MaterialPage({ params }: Readonly<{ params: Promise<{ id: string }> }>) {
  const { id } = await params;
  const user = await requireUser(`/materials/${id}`);
  return <AppShell user={user}><MaterialInformation materialId={id} /></AppShell>;
}
