import { AppShell } from "@/components/layout/app-shell";
import { MaterialRegistration } from "@/components/materials/material-registration";
import { requireUser } from "@/lib/api/server";

export default async function NewMaterialPage() {
  const user = await requireUser("/materials/new");
  return <AppShell user={user}><MaterialRegistration /></AppShell>;
}
