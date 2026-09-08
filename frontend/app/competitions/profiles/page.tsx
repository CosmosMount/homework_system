import Link from "next/link";
import { redirect } from "next/navigation";

import { TeamProfileDirectory } from "@/components/competitions/team-profile-directory";
import { AppShell } from "@/components/layout/app-shell";
import { buttonClassName } from "@/components/ui/form-controls";
import {
  getDashboard,
  getMyTeam,
  getMyTeamProfile,
  getTeamInvitations,
  getTeamProfiles,
  requireUser,
} from "@/lib/api/server";
import { isAdminView } from "@/lib/api/types";

type TeamProfilesPageProps = Readonly<{
  searchParams: Promise<{ direction_id?: string; q?: string; page?: string }>;
}>;

export default async function TeamProfilesPage({
  searchParams,
}: TeamProfilesPageProps) {
  const user = await requireUser("/competitions/profiles");
  if (isAdminView(user)) {
    redirect("/admin/competitions");
  }
  const filters = await searchParams;
  const query = (filters.q ?? "").trim().slice(0, 120);
  const requestedPage = Number(filters.page ?? "1");
  const page =
    Number.isSafeInteger(requestedPage) && requestedPage > 0
      ? requestedPage
      : 1;
  const directionId = (filters.direction_id ?? "").trim();
  const search = new URLSearchParams({
    ...(query ? { query } : {}),
    ...(directionId ? { direction_id: directionId } : {}),
    page: String(page),
    page_size: "20",
  }).toString();
  const [dashboard, profile, profiles] = await Promise.all([
    getDashboard(),
    getMyTeamProfile(),
    getTeamProfiles(search),
  ]);
  const [team, invitations] = profiles.team_open
    ? await Promise.all([getMyTeam(), getTeamInvitations()])
    : [null, []];

  return (
    <AppShell unreadCounts={dashboard.unread_counts} user={user}>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">
        STUDENT / TEAM PROFILES
      </p>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">组队个人简介</h1>
          <p className="mt-3 max-w-3xl text-[var(--color-text-secondary)]">
            {profiles.team_open
              ? "查看同学自愿发布的组队简介。队伍中的任一成员都可以发出邀请，对方接受后才会加入。"
              : "管理员暂未开放组队。你仍可填写个人简介、查看同学简介，并按技术组筛选。"}
          </p>
        </div>
        <Link className={buttonClassName} href="/competitions">
          返回队伍中心
        </Link>
      </div>
      <TeamProfileDirectory
        currentUserId={user.id}
        hasTeam={team !== null}
        directionId={directionId}
        initialInvitations={invitations}
        initialProfile={profile}
        initialProfiles={profiles}
        query={query}
        teamCanInvite={profiles.team_open && team !== null && team.member_count < team.max_members}
        teamOpen={profiles.team_open}
      />
    </AppShell>
  );
}
