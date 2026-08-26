import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { isAdminView } from "@/lib/api/types";

import type {
  AdminCompetitionDetail,
  AdminRegistrationList,
  AdminSession,
  AdminTeamDetail,
  AdminTeamList,
  AnnouncementAdmin,
  AnnouncementAdminPage,
  AnnouncementDetail,
  AnnouncementPage,
  AuditLogPage,
  AssignmentAdmin,
  AssignmentAdminPage,
  AssignmentDetail,
  AssignmentPage,
  AssignmentSubmissionAdminPage,
  CompetitionDetail,
  CompetitionPage,
  CompetitionTask,
  Dashboard,
  Direction,
  ExcellentSubmissionDetail,
  ExcellentSubmissionSummary,
  OutboxJobPage,
  Session,
  Submission,
  Team,
  User,
  UserPage,
} from "@/lib/api/types";

const internalApiBase =
  process.env.API_INTERNAL_BASE_URL ?? "http://backend:8000/api/v1";

async function serverApi<T>(path: string): Promise<Response | T> {
  const cookieHeader = (await cookies()).toString();
  const response = await fetch(internalApiBase + path, {
    cache: "no-store",
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
  });
  if (!response.ok) {
    return response;
  }
  return (await response.json()) as T;
}

export async function getOptionalUser(): Promise<User | null> {
  const result = await serverApi<User>("/auth/me");
  if (result instanceof Response) {
    return null;
  }
  return result;
}

export async function requireUser(): Promise<User> {
  const user = await getOptionalUser();
  if (user === null) {
    redirect("/login");
  }
  return user;
}

export async function requireAdmin(): Promise<User> {
  const user = await requireUser();
  if (!isAdminView(user)) {
    redirect("/dashboard");
  }
  return user;
}

export async function getSessions(): Promise<Session[]> {
  const result = await serverApi<Session[]>("/auth/sessions");
  if (result instanceof Response) {
    redirect("/login");
  }
  return result;
}

export async function getAdminUsers(): Promise<UserPage> {
  const result = await serverApi<UserPage>("/admin/users?page_size=100");
  if (result instanceof Response) {

    if (result.status === 401) {
      redirect("/login");
    }
    redirect("/dashboard");
  }
  return result;
}

export async function getDirections(): Promise<Direction[]> {
  const result = await serverApi<Direction[]>("/admin/directions");
  if (result instanceof Response) {
    if (result.status === 401) {
      redirect("/login");
    }
    redirect("/dashboard");
  }
  return result;
}


function resolveProtectedResult<T>(result: Response | T): T {
  if (!(result instanceof Response)) {
    return result;
  }
  if (result.status === 401) {
    redirect("/login");

  }
  if (result.status === 403) {
    redirect("/dashboard");
  }
  throw new Error("内部 API 请求失败：" + result.status);
}

export async function getDashboard(): Promise<Dashboard> {
  return resolveProtectedResult(await serverApi<Dashboard>("/dashboard"));
}


export async function getAdminSessions(): Promise<AdminSession[]> {
  return resolveProtectedResult(
    await serverApi<AdminSession[]>("/auth/admin/sessions"),
  );
}
export async function getAnnouncements(
  search = "",
): Promise<AnnouncementPage> {
  const suffix = search ? "?" + search : "";
  return resolveProtectedResult(
    await serverApi<AnnouncementPage>("/announcements" + suffix),
  );
}

export async function getAnnouncement(
  announcementId: string,
): Promise<AnnouncementDetail | null> {
  const result = await serverApi<AnnouncementDetail>(
    "/announcements/" + encodeURIComponent(announcementId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getAdminAnnouncements(): Promise<AnnouncementAdminPage> {
  return resolveProtectedResult(
    await serverApi<AnnouncementAdminPage>(
      "/admin/announcements?page_size=100",
    ),
  );
}

export async function getAdminAnnouncement(
  announcementId: string,
): Promise<AnnouncementAdmin | null> {
  const result = await serverApi<AnnouncementAdmin>(
    "/admin/announcements/" + encodeURIComponent(announcementId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getOutboxJobs(): Promise<OutboxJobPage> {
  return resolveProtectedResult(
    await serverApi<OutboxJobPage>("/admin/mail-outbox?page_size=100"),
  );
}

export async function getAuditLogs(): Promise<AuditLogPage> {
  return resolveProtectedResult(
    await serverApi<AuditLogPage>("/admin/audit-logs?page_size=100"),
  );
}

export async function getAssignments(search = ""): Promise<AssignmentPage> {
  const suffix = search ? "?" + search : "";
  return resolveProtectedResult(
    await serverApi<AssignmentPage>("/assignments" + suffix),
  );
}

export async function getAssignment(
  assignmentId: string,
): Promise<AssignmentDetail | null> {
  const result = await serverApi<AssignmentDetail>(
    "/assignments/" + encodeURIComponent(assignmentId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getAssignmentSubmission(
  assignmentId: string,
): Promise<Submission | null> {
  const result = await serverApi<Submission>(
    "/assignments/" + encodeURIComponent(assignmentId) + "/submission",
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getSubmission(
  submissionId: string,
): Promise<Submission | null> {
  const result = await serverApi<Submission>(
    "/submissions/" + encodeURIComponent(submissionId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getExcellentSubmissions(
  assignmentId: string,
): Promise<ExcellentSubmissionSummary[]> {
  return resolveProtectedResult(
    await serverApi<ExcellentSubmissionSummary[]>(
      "/assignments/" +
        encodeURIComponent(assignmentId) +
        "/excellent-submissions",
    ),
  );
}

export async function getExcellentSubmission(
  assignmentId: string,
  versionId: string,
): Promise<ExcellentSubmissionDetail | null> {
  const result = await serverApi<ExcellentSubmissionDetail>(
    "/assignments/" +
      encodeURIComponent(assignmentId) +
      "/excellent-submissions/" +
      encodeURIComponent(versionId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getAdminAssignments(): Promise<AssignmentAdminPage> {
  return resolveProtectedResult(
    await serverApi<AssignmentAdminPage>("/admin/assignments?page_size=100"),
  );
}

export async function getAdminAssignment(
  assignmentId: string,
): Promise<AssignmentAdmin | null> {
  const result = await serverApi<AssignmentAdmin>(
    "/admin/assignments/" + encodeURIComponent(assignmentId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getAdminAssignmentSubmissions(
  assignmentId: string,
): Promise<AssignmentSubmissionAdminPage> {
  return resolveProtectedResult(
    await serverApi<AssignmentSubmissionAdminPage>(
      "/admin/assignments/" +
        encodeURIComponent(assignmentId) +
        "/submissions?page_size=100",
    ),
  );
}

export async function getCompetitions(search = ""): Promise<CompetitionPage> {
  const suffix = search ? "?" + search : "";
  return resolveProtectedResult(
    await serverApi<CompetitionPage>("/competitions" + suffix),
  );
}

export async function getCompetition(
  competitionId: string,
): Promise<CompetitionDetail | null> {
  const result = await serverApi<CompetitionDetail>(
    "/competitions/" + encodeURIComponent(competitionId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getCompetitionTeam(
  competitionId: string,
): Promise<Team | null> {
  const result = await serverApi<Team>(
    "/competitions/" + encodeURIComponent(competitionId) + "/my-team",
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getCompetitionTask(
  competitionId: string,
  taskId: string,
): Promise<CompetitionTask | null> {
  const result = await serverApi<CompetitionTask>(
    "/competitions/" +
      encodeURIComponent(competitionId) +
      "/tasks/" +
      encodeURIComponent(taskId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getCompetitionSubmission(
  competitionId: string,
  taskId: string,
): Promise<Submission | null> {
  const result = await serverApi<Submission>(
    "/competitions/" +
      encodeURIComponent(competitionId) +
      "/tasks/" +
      encodeURIComponent(taskId) +
      "/submission",
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getAdminCompetitions(): Promise<CompetitionPage> {
  return resolveProtectedResult(
    await serverApi<CompetitionPage>("/admin/competitions?page_size=100"),
  );
}

export async function getAdminCompetition(
  competitionId: string,
): Promise<AdminCompetitionDetail | null> {
  const result = await serverApi<AdminCompetitionDetail>(
    "/admin/competitions/" + encodeURIComponent(competitionId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getAdminCompetitionTeams(
  competitionId: string,
): Promise<AdminTeamList> {
  return resolveProtectedResult(
    await serverApi<AdminTeamList>(
      "/admin/competitions/" + encodeURIComponent(competitionId) + "/teams",
    ),
  );
}

export async function getAdminCompetitionRegistrations(
  competitionId: string,
): Promise<AdminRegistrationList> {
  return resolveProtectedResult(
    await serverApi<AdminRegistrationList>(
      "/admin/competitions/" +
        encodeURIComponent(competitionId) +
        "/registrations",
    ),
  );
}

export async function getAdminTeam(
  teamId: string,
): Promise<AdminTeamDetail | null> {
  const result = await serverApi<AdminTeamDetail>(
    "/admin/teams/" + encodeURIComponent(teamId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}
