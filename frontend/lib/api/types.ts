export type Role = "student" | "admin";
export type UserStatus = "pending_email" | "active" | "disabled";

export type CategorySummary = {
  id: string;
  code: string;
  name: string;
};

export type User = {
  id: string;
  email: string;
  student_number: string;
  full_name: string;
  role: Role;
  status: UserStatus;
  student_view?: boolean;
  cohort: CategorySummary | null;
  direction: CategorySummary | null;
  email_verified_at: string | null;
  created_at: string;
  revision: number;
};
export function isAdminView(user: User): boolean {
  return user.role === "admin" && user.student_view !== true;
}

export type UserPage = {
  items: User[];
  page: number;
  page_size: number;
  total: number;
};

export type Session = {
  id: string;
  created_at: string;
  last_seen_at: string;
  idle_expires_at: string;
  absolute_expires_at: string;
  revoked_at: string | null;
  ip_prefix: string;
  user_agent_summary: string;
  is_current: boolean;
};


export type AdminSession = {
  id: string;
  user_id: string;
  user_full_name: string;
  user_email: string;
  user_role: Role;
  user_status: UserStatus;
  created_at: string;
  last_seen_at: string;
  idle_expires_at: string;
  absolute_expires_at: string;
  ip_prefix: string;
  user_agent_summary: string;
  is_current: boolean;
};
export type Direction = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  revision: number;
};

export type ErrorDetail = {
  field: string;
  reason: string;
};

export type ApiErrorPayload = {
  error: {
    code: string;
    message: string;
    request_id: string;
    details?: ErrorDetail[];
  };
};


export type AnnouncementStatus =
  | "draft"
  | "scheduled"
  | "published"
  | "archived";

export type AnnouncementAudience = {
  all_students: boolean;
  cohort_ids: string[];
  direction_ids: string[];
  match: "union" | "intersection";
};

export type AnnouncementSummary = {
  id: string;
  title: string;
  summary: string;
  published_at: string;
  updated_at: string;
  pinned_until: string | null;
  is_pinned: boolean;
  is_unread: boolean;
  has_attachments: boolean;
};

export type AnnouncementPage = {
  items: AnnouncementSummary[];
  page: number;
  page_size: number;
  total: number;
};

export type AnnouncementAttachment = {
  id: string;
  file_name: string;
  size_bytes: number;
  media_type: string;
  sha256: string;
};

export type AnnouncementDetail = {
  id: string;
  title: string;
  summary: string;
  body_html: string;
  published_at: string;
  updated_at: string;
  pinned_until: string | null;
  audience_description: string;
  attachments: AnnouncementAttachment[];
  notification_ids: string[];
};

export type AnnouncementAdmin = {
  id: string;
  title: string;
  summary: string;
  body_markdown: string;
  body_html: string;
  status: AnnouncementStatus;
  audience: AnnouncementAudience;
  attachment_file_ids: string[];
  publish_at: string | null;
  published_at: string | null;
  pinned_until: string | null;
  send_email: boolean;
  archived_at: string | null;
  estimated_recipient_count: number;
  actual_recipient_count: number;
  created_at: string;
  updated_at: string;
  revision: number;
};

export type AnnouncementAdminPage = {
  items: AnnouncementAdmin[];
  page: number;
  page_size: number;
  total: number;
};

export type Dashboard = {
  current_user: {
    id: string;
    full_name: string;
    role: Role;
    cohort_id: string | null;
    direction_id: string | null;
  };
  unread_count: number;
  recent_announcements: AnnouncementSummary[];
  assignments: { id: string; title: string; deadline: string }[];
  competitions: { id: string; name: string; status: string }[];
};

export type StudentNotification = {
  id: string;
  type: string;
  title: string;
  target_url: string;
  created_at: string;
  read_at: string | null;
};

export type StudentNotificationPage = {
  items: StudentNotification[];
  page: number;
  page_size: number;
  total: number;
};

export type OutboxJob = {
  id: string;
  job_type: string;
  status: string;
  recipient_masked: string;
  available_at: string;
  attempt_count: number;
  max_attempts: number;
  last_error_code: string | null;
  last_error_summary: string | null;
  created_at: string;
  sent_at: string | null;
};

export type OutboxJobPage = {
  items: OutboxJob[];
  page: number;
  page_size: number;
  total: number;
};

export type AuditLog = {
  id: string;
  actor_user_id: string | null;
  action: string;
  target_type: string;
  target_id: string;
  request_id: string;
  ip_prefix: string;
  result: string;
  change_summary: Record<string, unknown>;
  created_at: string;
};

export type AuditLogPage = {
  items: AuditLog[];
  page: number;
  page_size: number;
  total: number;
};

export type UploadSession = {
  upload_id: string;
  file_id: string;
  status: string;
  part_size_bytes: number;
  part_count: number;
  uploaded_parts: {
    part_number: number;
    etag: string;
    checksum_sha256: string;
    size_bytes: number;
  }[];
  expires_at: string;
  failure_code: string | null;
};

export type CompletedFile = {
  file_id: string;
  status: string;
  file_name: string;
  size_bytes: number;
  media_type: string;
  sha256: string;
};
export type AssignmentAudience = {
  all_students: boolean;
  cohort_ids: string[];
  direction_ids: string[];
  match: "union" | "intersection";
};

export type AssignmentStats = {
  target_count: number;
  submitted_count: number;
  unsubmitted_count: number;
  feedback_submission_count: number;
  last_submitted_at: string | null;
};

export type AssignmentAdmin = {
  id: string;
  title: string;
  description_markdown: string;
  description_html: string;
  training_url: string | null;
  submission_instructions: string;
  status: "draft" | "published" | "closed" | "archived";
  audience: AssignmentAudience;
  allowed_extensions: string[];
  max_total_bytes: number;
  publish_at: string;
  published_at: string | null;
  deadline: string;
  closed_at: string | null;
  archived_at: string | null;
  estimated_recipient_count: number;
  actual_recipient_count: number;
  stats: AssignmentStats;
  created_at: string;
  updated_at: string;
  revision: number;
};

export type AssignmentAdminPage = {
  items: AssignmentAdmin[];
  page: number;
  page_size: number;
  total: number;
};

export type AssignmentSubmissionSummary = {
  submission_id: string;
  latest_version_id: string;
  latest_version_number: number;
  submitted_at: string;
  has_feedback: boolean;
};

export type ExcellentSubmissionSummary = {
  version_id: string;
  author_name: string;
  version_number: number;
  marked_at: string;
};

export type AssignmentSummary = {
  id: string;
  title: string;
  status: "draft" | "published" | "closed" | "archived";
  public_deadline: string;
  effective_deadline: string;
  has_personal_extension: boolean;
  can_submit: boolean;
  latest_submission: AssignmentSubmissionSummary | null;
};

export type AssignmentPage = {
  items: AssignmentSummary[];
  page: number;
  page_size: number;
  total: number;
};

export type AssignmentDetail = AssignmentSummary & {
  description_html: string;
  training_url: string | null;
  submission_instructions: string;
  allowed_extensions: string[];
  max_total_bytes: number;
  excellent_submissions: ExcellentSubmissionSummary[];
};

export type SubmissionAttachment = {
  id: string;
  file_name: string;
  size_bytes: number;
  media_type: string;
  sha256: string;
};

export type Feedback = {
  id: string;
  body_html: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  revision: number;
};

export type SubmissionVersion = {
  id: string;
  submission_id: string;
  version_number: number;
  submitted_by: string;
  text_html: string | null;
  external_url: string | null;
  total_file_bytes: number;
  submitted_at: string;
  attachments: SubmissionAttachment[];
  feedback: Feedback | null;
};

export type Submission = {
  id: string;
  assignment_id: string | null;
  competition_task_id: string | null;
  owner_user_id: string | null;
  owner_team_id: string | null;
  latest_version_id: string;
  versions: SubmissionVersion[];
};

export type SubmissionVersionCreated = {
  submission_id: string;
  version_id: string;
  version_number: number;
  submitted_at: string;
  total_file_bytes: number;
};

export type ExcellentSubmissionDetail = {
  assignment_id: string;
  assignment_title: string;
  version_id: string;
  version_number: number;
  author_name: string;
  text_html: string | null;
  external_url: string | null;
  submitted_at: string;
  marked_at: string;
  attachments: SubmissionAttachment[];
};

export type AssignmentSubmissionAdminItem = {
  user_id: string;
  full_name: string;
  student_number: string;
  cohort_id: string | null;
  direction_id: string | null;
  submission_id: string | null;
  latest_version_number: number | null;
  last_submitted_at: string | null;
  has_feedback: boolean;
};

export type AssignmentSubmissionAdminPage = {
  items: AssignmentSubmissionAdminItem[];
  page: number;
  page_size: number;
  total: number;
};

export type AssignmentExtension = {
  assignment_id: string;
  user_id: string;
  extended_deadline: string;
  reason: string;
  granted_by: string;
  created_at: string;
  updated_at: string;
  revision: number;
};

export type CompetitionStatus =
  | "draft"
  | "registration_open"
  | "registration_closed"
  | "submission_open"
  | "submission_closed"
  | "archived";

export type RegistrationStatus =
  | "registered"
  | "withdrawn"
  | "disqualified";

export type TeamStatus =
  | "forming"
  | "dissolved"
  | "locked"
  | "invalid"
  | "disqualified"
  | "archived";

export type CompetitionTask = {
  id: string;
  competition_id: string;
  title: string;
  description_markdown: string;
  description_html: string;
  resource_url: string | null;
  allowed_extensions: string[];
  max_total_bytes: number;
  deadline: string;
  display_order: number;
  revision: number;
  submission_id: string | null;
  latest_version_id: string | null;
};

export type CompetitionSummary = {
  id: string;
  name: string;
  status: CompetitionStatus;
  registration_start: string;
  registration_end: string;
  submission_start: string;
  submission_end: string;
  min_team_size: number;
  max_team_size: number;
  registration_status: RegistrationStatus | null;
  registration_disqualification_reason: string | null;
  team_id: string | null;
  team_name: string | null;
  team_status: TeamStatus | null;
};

export type CompetitionPage = {
  items: CompetitionSummary[];
  total: number;
  page: number;
  page_size: number;
};

export type CompetitionDetail = {
  id: string;
  name: string;
  description_markdown: string;
  description_html: string;
  rules_url: string | null;
  status: CompetitionStatus;
  registration_start: string;
  registration_end: string;
  submission_start: string;
  submission_end: string;
  min_team_size: number;
  max_team_size: number;
  published_at: string | null;
  archived_at: string | null;
  revision: number;
  registration_status: RegistrationStatus | null;
  registration_disqualification_reason: string | null;
  team_id: string | null;
  team_name: string | null;
  team_status: TeamStatus | null;
  tasks: CompetitionTask[];
};

export type AdminCompetitionDetail = CompetitionDetail & {
  registration_count: number;
  team_count: number;
  valid_team_count: number;
  invalid_team_count: number;
};

export type Registration = {
  competition_id: string;
  user_id: string;
  status: RegistrationStatus;
  registered_at: string;
  withdrawn_at: string | null;
  disqualified_at: string | null;
  disqualification_reason: string | null;
  revision: number;
};

export type AdminRegistrationItem = {
  user_id: string;
  full_name: string;
  student_number: string;
  status: RegistrationStatus;
  registered_at: string;
  withdrawn_at: string | null;
  disqualified_at: string | null;
  disqualification_reason: string | null;
  team_id: string | null;
  team_name: string | null;
};

export type AdminRegistrationList = {
  items: AdminRegistrationItem[];
  total: number;
};

export type TeamMember = {
  user_id: string;
  full_name: string;
  student_id: string;
  joined_at: string;
  added_by_admin: boolean;
  is_captain: boolean;
};

export type Team = {
  id: string;
  competition_id: string;
  name: string;
  status: TeamStatus;
  captain_user_id: string | null;
  member_count: number;
  min_team_size: number;
  max_team_size: number;
  min_size_waived: boolean;
  waiver_reason: string | null;
  disqualification_reason: string | null;
  locked_at: string | null;
  dissolved_at: string | null;
  revision: number;
  members: TeamMember[];
  can_manage: boolean;
  can_submit: boolean;
};

export type TeamCreated = Team & {
  invite_code: string;
};

export type AutoAssign = Team & {
  assignment: "joined" | "created";
  invite_code: string | null;
};

export type TeamDirectoryItem = {
  id: string;
  competition_id: string;
  name: string;
  status: TeamStatus;
  member_count: number;
  max_team_size: number;
  can_join: boolean;
};

export type TeamDirectoryPage = {
  items: TeamDirectoryItem[];
  total: number;
  page: number;
  page_size: number;
};

export type InviteCodeRotated = {
  team_id: string;
  invite_code: string;
  rotated_at: string;
  revision: number;
};

export type AdminTeamListItem = {
  id: string;
  competition_id: string;
  name: string;
  status: TeamStatus;
  captain_user_id: string | null;
  member_count: number;
  min_size_waived: boolean;
  latest_submission_count: number;
};

export type AdminTeamList = {
  items: AdminTeamListItem[];
  total: number;
};

export type AdminTeamSubmissionItem = {
  task_id: string;
  task_title: string;
  deadline: string;
  submission_id: string | null;
  latest_version_id: string | null;
};

export type AdminTeamDetail = Team & {
  submissions: AdminTeamSubmissionItem[];
};


export type IntentionStatus = "draft" | "open" | "closed" | "archived";

export type IntentionOption = {
  id: string;
  label: string;
  display_order: number;
};

export type IntentionSurveySummary = {
  id: string;
  title: string;
  description_html: string;
  status: IntentionStatus;
  allow_multiple: boolean;
  starts_at: string | null;
  ends_at: string | null;
  option_count: number;
  has_response: boolean;
};

export type IntentionSurvey = IntentionSurveySummary & {
  options: IntentionOption[];
  response: {
    selected_option_ids: string[];
    free_text: string | null;
    submitted_at: string;
  } | null;
  revision: number;
};

export type IntentionSurveyPage = {
  items: IntentionSurveySummary[];
  total: number;
};

export type AdminIntentionSurvey = {
  id: string;
  title: string;
  description_markdown: string;
  status: IntentionStatus;
  allow_multiple: boolean;
  starts_at: string | null;
  ends_at: string | null;
  option_count: number;
  responded_count: number;
  created_at: string;
  updated_at: string;
  revision: number;
};

export type AdminIntentionSurveyPage = {
  items: AdminIntentionSurvey[];
  total: number;
};

export type IntentionStats = {
  survey_id: string;
  total_active_students: number;
  responded_count: number;
  response_rate: number;
  options: {
    option_id: string;
    label: string;
    response_count: number;
    percentage: number;
  }[];
};

export type IntentionQr = {
  survey_id: string;
  token: string;
  fill_url: string;
  generated_at: string;
};

export type KnowledgeSnapshot = {
  run_id: string;
  synced_at: string;
  source_url: string;
  document_count: number;
  asset_count: number;
};

export type KnowledgeNode = {
  id: string;
  parent_id: string | null;
  document_id: string | null;
  title: string;
  node_type: "document" | "folder" | "unsupported";
  depth: number;
  display_order: number;
  source_url: string | null;
};

export type KnowledgeDocumentSummary = {
  id: string;
  title: string;
  source_url: string;
  source_token: string;
  display_order: number;
};

export type KnowledgeOverview = {
  snapshot: KnowledgeSnapshot | null;
  nodes: KnowledgeNode[];
  documents: KnowledgeDocumentSummary[];
};

export type KnowledgeRichSegment = {
  text: string;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  strikethrough?: boolean;
  inline_code?: boolean;
  href?: string;
  document_token?: string;
};

export type KnowledgeTableCell = {
  id: string;
  blocks: KnowledgeBlock[];
  row_span?: number;
  col_span?: number;
};

export type KnowledgeBlock = {
  id: string;
  type:
    | "paragraph"
    | "heading"
    | "bullet"
    | "ordered"
    | "code"
    | "quote"
    | "todo"
    | "callout"
    | "divider"
    | "image"
    | "whiteboard"
    | "attachment"
    | "table"
    | "container";
  segments?: KnowledgeRichSegment[];
  level?: number;
  done?: boolean;
  language?: string;
  tone?: string;
  wrap?: boolean;
  emoji_id?: string;
  background_color?: number | string;
  border_color?: number | string;
  text_color?: number | string;
  asset_id?: string | null;
  file_name?: string;
  fallback_url?: string;
  file_size?: number;
  mime_type?: string;
  width?: number | null;
  height?: number | null;
  children?: KnowledgeBlock[];
  rows?: Array<Array<KnowledgeBlock[] | KnowledgeTableCell>>;
};

export type KnowledgeDocument = KnowledgeDocumentSummary & {
  synced_at: string;
  blocks: KnowledgeBlock[];
};

export type KnowledgeSyncRun = {
  id: string;
  status: "pending" | "running" | "succeeded" | "failed";
  source_url: string;
  started_at: string | null;
  finished_at: string | null;
  document_count: number;
  asset_count: number;
  error_code: string | null;
  error_summary: string | null;
  created_at: string;
};

export type KnowledgeAdminStatus = {
  configured: boolean;
  current_snapshot: KnowledgeSnapshot | null;
  latest_run: KnowledgeSyncRun | null;
};

export type KnowledgeSyncCreated = {
  run: KnowledgeSyncRun;
};
