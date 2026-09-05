import "server-only";

import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import { isAdminView } from "@/lib/api/types";
import { safeReturnPath } from "@/lib/safe-return-path";

import type {
  AdminHelpRequestDetail,
  AdminHelpRequestPage,
  AdminSession,
  AdminUserPage,
  AdminIntentionSurveyPage,
  IntentionRoster,
  IntentionStats,
  IntentionSurvey,
  IntentionSurveyPage,
  KnowledgeAdminStatus,
  KnowledgeDocument,
  KnowledgeOverview,
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
  Dashboard,
  Direction,
  ExcellentSubmissionDetail,
  ExcellentSubmissionSummary,
  HelpRequestDetail,
  HelpRequestPage,
  PublicHelpRequestDetail,
  OutboxJobPage,
  Session,
  Submission,
  Team,
  TeamDirectoryPage,
  User,
} from "@/lib/api/types";

const internalApiBase =
  process.env.API_INTERNAL_BASE_URL ?? "http://backend:8000/api/v1";

async function serverApi<T>(path: string): Promise<Response | T> {
  const [cookieStore, incomingHeaders] = await Promise.all([cookies(), headers()]);
  const cookieHeader = cookieStore.toString();
  const forwardedFor = incomingHeaders.get("x-forwarded-for")?.trim();
  const internalHeaders = new Headers();
  if (cookieHeader) {
    internalHeaders.set("cookie", cookieHeader);
  }
  if (forwardedFor) {
    internalHeaders.set("x-forwarded-for", forwardedFor);
  }
  const response = await fetch(internalApiBase + path, {
    cache: "no-store",
    headers: internalHeaders,
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

export async function requireUser(returnTo?: string): Promise<User> {
  const user = await getOptionalUser();
  if (user === null) {
    const safeReturnTo = safeReturnPath(returnTo);
    redirect(
      safeReturnTo === null
        ? "/login"
        : "/login?next=" + encodeURIComponent(safeReturnTo),
    );
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

type AdminUserQuery = Readonly<{
  activity?: "inactive";
  directionId?: string;
  page?: number;
  pageSize?: number;
  search?: string;
}>;

export async function getAdminUsers({
  activity,
  directionId,
  page = 1,
  pageSize = 100,
  search,
}: AdminUserQuery = {}): Promise<AdminUserPage> {
  const safePage = Math.min(10_000, Math.max(1, Math.trunc(page)));
  const safePageSize = Math.min(100, Math.max(1, Math.trunc(pageSize)));
  const params = new URLSearchParams({
    page: String(safePage),
    page_size: String(safePageSize),
  });
  if (activity === "inactive") {
    params.set("activity", activity);
  }
  if (directionId) {
    params.set("direction_id", directionId);
  }
  const normalizedSearch = search?.trim().slice(0, 200);
  if (normalizedSearch) {
    params.set("search", normalizedSearch);
  }
  const result = await serverApi<AdminUserPage>(
    "/admin/users?" + params.toString(),
  );
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
  const pageSize = 100;
  const first = resolveProtectedResult(
    await serverApi<AssignmentSubmissionAdminPage>(
      "/admin/assignments/" +
        encodeURIComponent(assignmentId) +
        "/submissions?page=1&page_size=" +
        pageSize,
    ),
  );
  const pageCount = Math.ceil(first.total / pageSize);
  if (pageCount <= 1) return first;
  const remaining = await Promise.all(
    Array.from({ length: pageCount - 1 }, (_, index) =>
      serverApi<AssignmentSubmissionAdminPage>(
        "/admin/assignments/" +
          encodeURIComponent(assignmentId) +
          "/submissions?page=" +
          (index + 2) +
          "&page_size=" +
          pageSize,
      ).then(resolveProtectedResult),
    ),
  );
  return {
    ...first,
    items: [first, ...remaining].flatMap((page) => page.items),
  };
}

export async function getTeams(search = ""): Promise<TeamDirectoryPage> {
  const suffix = search ? "?" + search : "";
  return resolveProtectedResult(
    await serverApi<TeamDirectoryPage>("/teams" + suffix),
  );
}

export async function getMyTeam(): Promise<Team | null> {
  return resolveProtectedResult(await serverApi<Team | null>("/teams/me"));
}

export async function getIntentions(): Promise<IntentionSurveyPage> {
  return resolveProtectedResult(await serverApi<IntentionSurveyPage>("/intentions"));
}

export async function getIntention(
  surveyId: string,
  token = "",
): Promise<IntentionSurvey | null> {
  const query = token ? "?token=" + encodeURIComponent(token) : "";
  const result = await serverApi<IntentionSurvey>(
    "/intentions/" + encodeURIComponent(surveyId) + query,
  );
  if (result instanceof Response && result.status === 404) return null;
  return resolveProtectedResult(result);
}

export async function getAdminIntentions(): Promise<AdminIntentionSurveyPage> {
  return resolveProtectedResult(
    await serverApi<AdminIntentionSurveyPage>("/admin/intentions"),
  );
}

export async function getAdminIntentionStats(surveyId: string): Promise<IntentionStats> {
  return resolveProtectedResult(
    await serverApi<IntentionStats>(
      "/admin/intentions/" + encodeURIComponent(surveyId) + "/stats",
    ),
  );
}

export async function getAdminIntentionRoster(surveyId: string): Promise<IntentionRoster> {
  return resolveProtectedResult(
    await serverApi<IntentionRoster>(
      "/admin/intentions/" + encodeURIComponent(surveyId) + "/responses",
    ),
  );
}

export async function getHelpRequests(search = ""): Promise<HelpRequestPage> {
  const suffix = search ? "?" + search : "";
  return resolveProtectedResult(
    await serverApi<HelpRequestPage>("/help-requests" + suffix),
  );
}

export async function getHelpRequest(
  requestId: string,
): Promise<HelpRequestDetail | null> {
  const result = await serverApi<HelpRequestDetail>(
    "/help-requests/" + encodeURIComponent(requestId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getPublicHelpRequests(
  search = "",
): Promise<HelpRequestPage> {
  const suffix = search ? "?" + search : "";
  return resolveProtectedResult(
    await serverApi<HelpRequestPage>("/help-requests/public" + suffix),
  );
}

export async function getPublicHelpRequest(
  requestId: string,
): Promise<PublicHelpRequestDetail | null> {
  const result = await serverApi<PublicHelpRequestDetail>(
    "/help-requests/public/" + encodeURIComponent(requestId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getAdminHelpRequests(
  search = "",
): Promise<AdminHelpRequestPage> {
  const suffix = search ? "?" + search : "";
  return resolveProtectedResult(
    await serverApi<AdminHelpRequestPage>("/admin/help-requests" + suffix),
  );
}

export async function getAdminHelpRequest(
  requestId: string,
): Promise<AdminHelpRequestDetail | null> {
  const result = await serverApi<AdminHelpRequestDetail>(
    "/admin/help-requests/" + encodeURIComponent(requestId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getKnowledge(): Promise<KnowledgeOverview> {
  return resolveProtectedResult(
    await serverApi<KnowledgeOverview>("/knowledge"),
  );
}

export async function getKnowledgeDocument(
  documentId: string,
): Promise<KnowledgeDocument | null> {
  const result = await serverApi<KnowledgeDocument>(
    "/knowledge/documents/" + encodeURIComponent(documentId),
  );
  if (result instanceof Response && result.status === 404) {
    return null;
  }
  return resolveProtectedResult(result);
}

export async function getAdminKnowledge(): Promise<KnowledgeAdminStatus> {
  return resolveProtectedResult(
    await serverApi<KnowledgeAdminStatus>("/admin/knowledge"),
  );
}

export async function getAdminTeams(search = ""): Promise<AdminTeamList> {
  const suffix = search ? "?" + search : "";
  return resolveProtectedResult(
    await serverApi<AdminTeamList>("/admin/teams" + suffix),
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
