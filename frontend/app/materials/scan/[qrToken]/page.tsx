import { AppShell } from "@/components/layout/app-shell";
import { MaterialScanConfirmation } from "@/components/materials/material-scan-confirmation";
import { requireUser } from "@/lib/api/server";

export default async function MaterialScanPage({ params }: Readonly<{ params: Promise<{ qrToken: string }> }>) {
  const { qrToken } = await params;
  const user = await requireUser(`/materials/scan/${qrToken}`);
  return <AppShell user={user}><MaterialScanConfirmation qrToken={qrToken} /></AppShell>;
}
