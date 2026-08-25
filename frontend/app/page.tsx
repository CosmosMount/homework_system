import { redirect } from "next/navigation";

import { getOptionalUser } from "@/lib/api/server";

export default async function Home() {
  const user = await getOptionalUser();
  if (user === null) {
    redirect("/login");
  }
  redirect(user.role === "admin" ? "/admin/dashboard" : "/dashboard");
}
