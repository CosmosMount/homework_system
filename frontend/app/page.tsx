import { redirect } from "next/navigation";

import { getOptionalUser } from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";

export default async function Home() {
  const user = await getOptionalUser();
  if (user === null) {
    redirect("/login");
  }
  redirect(isAdminView(user) ? "/admin/dashboard" : "/dashboard");
}
