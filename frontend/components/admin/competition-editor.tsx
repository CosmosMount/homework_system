"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type {
  AdminCompetitionDetail,
  AdminTeamListItem,
  CompetitionDetail,
} from "@/lib/api/types";
import {
  competitionStatusLabel,
  statusTagClass,
  teamStatusLabel,
} from "@/lib/competition-labels";
import { formatDateTime } from "@/lib/format";

function localDateTime(value: string | null): string {
  if (value === null) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function apiDateTime(value: string): string {
  return new Date(value).toISOString();
}


function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}


export function CompetitionEditor({
  initialCompetition,
  initialTeams,
}: Readonly<{
  initialCompetition: AdminCompetitionDetail | null;
  initialTeams: AdminTeamListItem[];
}>) {
  const router = useRouter();
  const [competition, setCompetition] = useState<CompetitionDetail | null>(
    initialCompetition,
  );
  const [name, setName] = useState(initialCompetition?.name ?? "");
  const [description, setDescription] = useState(
    initialCompetition?.description_markdown ?? "",
  );
  const [rulesUrl, setRulesUrl] = useState(
    initialCompetition?.rules_url ?? "",
  );
  const [registrationStart, setRegistrationStart] = useState(
    localDateTime(initialCompetition?.registration_start ?? null),
  );
  const [registrationEnd, setRegistrationEnd] = useState(
    localDateTime(initialCompetition?.registration_end ?? null),
  );
  const [submissionStart, setSubmissionStart] = useState(
    localDateTime(initialCompetition?.submission_start ?? null),
  );
  const [submissionEnd, setSubmissionEnd] = useState(
    localDateTime(initialCompetition?.submission_end ?? null),
  );
  const [minTeamSize, setMinTeamSize] = useState(
    String(initialCompetition?.min_team_size ?? 2),
  );
  const [maxTeamSize, setMaxTeamSize] = useState(
    String(initialCompetition?.max_team_size ?? 4),
  );
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function validCompetition(): boolean {
    const minSize = Number(minTeamSize);
    const maxSize = Number(maxTeamSize);
    if (
      !name.trim() ||
      !description.trim() ||
      !registrationStart ||
      !registrationEnd ||
      !submissionStart ||
      !submissionEnd
    ) {
      setError("赛事名称、说明和四个时间节点均不能为空。");
      return false;
    }
    if (
      !(
        new Date(registrationStart) < new Date(registrationEnd) &&
        new Date(registrationEnd) <= new Date(submissionStart) &&
        new Date(submissionStart) < new Date(submissionEnd)
      )
    ) {
      setError("时间必须满足报名开始 < 报名结束 ≤ 组队锁定时间 < 赛事结束时间。");
      return false;
    }
    if (
      !Number.isSafeInteger(minSize) ||
      !Number.isSafeInteger(maxSize) ||
      minSize < 1 ||
      minSize > maxSize ||
      maxSize > 20
    ) {
      setError("队伍人数必须满足 1 ≤ 最小人数 ≤ 最大人数 ≤ 20。");
      return false;
    }
    return true;
  }

  function competitionPayload(current: CompetitionDetail | null) {
    const common = {
      name: name.trim(),
      description_markdown: description.trim(),
      rules_url: rulesUrl.trim() || null,
      registration_end: apiDateTime(registrationEnd),
      submission_start: apiDateTime(submissionStart),
      submission_end: apiDateTime(submissionEnd),
    };
    if (current === null || current.status === "draft") {
      return {
        ...common,
        registration_start: apiDateTime(registrationStart),
        min_team_size: Number(minTeamSize),
        max_team_size: Number(maxTeamSize),
        ...(current === null ? {} : { revision: current.revision }),
      };
    }
    return { ...common, revision: current.revision };
  }

  async function persist(): Promise<CompetitionDetail> {
    if (!validCompetition()) throw new Error("FORM_INVALID");
    const current = competition;
    const saved = await csrfFetch<CompetitionDetail>(
      current === null
        ? "/admin/competitions"
        : "/admin/competitions/" + current.id,
      {
        method: current === null ? "POST" : "PATCH",
        body: JSON.stringify(competitionPayload(current)),
      },
    );
    setCompetition(saved);
    if (current === null) {
      router.replace("/admin/competitions/" + saved.id);
    }
    return saved;
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      await persist();
      setMessage("赛事配置已保存。");
      router.refresh();
    } catch (nextError) {
      if (!(nextError instanceof Error) || nextError.message !== "FORM_INVALID") {
        setError(errorMessage(nextError));
      }
    } finally {
      setPending(false);
    }
  }

  async function transition(
    action:
      | "publish"
      | "close-registration"
      | "close-submissions"
      | "archive",
  ) {
    if (competition === null) return;
    if (
      !window.confirm(
        {
          publish: "确认发布赛事？Worker 会按时间单向推进阶段。",
          "close-registration": "确认提前关闭报名并立即锁定全部成形队伍？",
          "close-submissions": "确认提前结束赛事？",
          archive: "确认归档？报名和队伍将全部只读。",
        }[action],
      )
    ) {
      return;
    }
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const result = await csrfFetch<CompetitionDetail>(
        "/admin/competitions/" + competition.id + "/" + action,
        { method: "POST" },
      );
      setCompetition(result);
      setMessage("赛事状态已更新为“" + competitionStatusLabel(result.status) + "”。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  const editable = competition?.status !== "archived";
  const rulesEditable = competition === null || competition.status === "draft";

  return (
    <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <form className="space-y-6" onSubmit={save}>
        {message ? <FormMessage tone="success">{message}</FormMessage> : null}
        {error ? <FormMessage>{error}</FormMessage> : null}

        <section className="space-y-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-semibold">校内赛公告与组队</h2>
            {competition ? (
              <span
                className={
                  "border px-2 py-1 font-mono text-xs " +
                  statusTagClass(competition.status)
                }
              >
                {competitionStatusLabel(competition.status)} · revision{" "}
                {competition.revision}
              </span>
            ) : null}
          </div>
          <label className="block text-sm">
            名称
            <input
              className={inputClassName}
              disabled={!editable}
              maxLength={200}
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
          </label>
          <label className="block text-sm">
            公告（Markdown）
            <textarea
              className={inputClassName + " min-h-64 py-3 font-mono text-sm"}
              disabled={!editable}
              maxLength={200000}
              onChange={(event) => setDescription(event.target.value)}
              value={description}
            />
          </label>
          <label className="block text-sm">
            规则链接
            <input
              className={inputClassName}
              disabled={!editable}
              onChange={(event) => setRulesUrl(event.target.value)}
              type="url"
              value={rulesUrl}
            />
          </label>
        </section>

        <section className="grid gap-5 border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:grid-cols-2 sm:p-6">
          <h2 className="text-xl font-semibold sm:col-span-2">报名与组队规则</h2>
          <label className="text-sm">
            报名开始
            <input
              className={inputClassName}
              disabled={!rulesEditable}
              onChange={(event) => setRegistrationStart(event.target.value)}
              type="datetime-local"
              value={registrationStart}
            />
          </label>
          <label className="text-sm">
            报名结束
            <input
              className={inputClassName}
              disabled={!editable}
              onChange={(event) => setRegistrationEnd(event.target.value)}
              type="datetime-local"
              value={registrationEnd}
            />
          </label>
          <label className="text-sm">
            组队锁定时间
            <input
              className={inputClassName}
              disabled={!editable}
              onChange={(event) => setSubmissionStart(event.target.value)}
              type="datetime-local"
              value={submissionStart}
            />
          </label>
          <label className="text-sm">
            赛事结束时间
            <input
              className={inputClassName}
              disabled={!editable}
              onChange={(event) => setSubmissionEnd(event.target.value)}
              type="datetime-local"
              value={submissionEnd}
            />
          </label>
          <label className="text-sm">
            最小队伍人数
            <input
              className={inputClassName}
              disabled={!rulesEditable}
              max={20}
              min={1}
              onChange={(event) => setMinTeamSize(event.target.value)}
              type="number"
              value={minTeamSize}
            />
          </label>
          <label className="text-sm">
            最大队伍人数
            <input
              className={inputClassName}
              disabled={!rulesEditable}
              max={20}
              min={1}
              onChange={(event) => setMaxTeamSize(event.target.value)}
              type="number"
              value={maxTeamSize}
            />
          </label>
        </section>

        <div className="flex flex-wrap gap-3">
          <button className={buttonClassName} disabled={!editable || pending} type="submit">
            {pending ? "处理中…" : "保存赛事"}
          </button>
          {competition?.status === "draft" ? (
            <button
              className="min-h-11 border border-[var(--color-accent)] px-5 text-[var(--color-accent-hover)]"
              disabled={pending}
              onClick={() => transition("publish")}
              type="button"
            >
              发布赛事
            </button>
          ) : null}
          {competition?.status === "registration_open" ? (
            <button
              className="min-h-11 border border-[var(--color-danger)] px-5 text-[var(--color-danger)]"
              disabled={pending}
              onClick={() => transition("close-registration")}
              type="button"
            >
              提前关闭报名
            </button>
          ) : null}
          {competition &&
          ["registration_closed", "submission_open"].includes(
            competition.status,
          ) ? (
            <button
              className="min-h-11 border border-[var(--color-danger)] px-5 text-[var(--color-danger)]"
              disabled={pending}
              onClick={() => transition("close-submissions")}
              type="button"
            >
              提前结束赛事
            </button>
          ) : null}
          {competition?.status === "submission_closed" ? (
            <button
              className="min-h-11 border border-[var(--color-border-strong)] px-5"
              disabled={pending}
              onClick={() => transition("archive")}
              type="button"
            >
              归档赛事
            </button>
          ) : null}
        </div>

        {competition && initialTeams.length ? (
          <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
            <h2 className="text-xl font-semibold">队伍</h2>
            <div className="mt-4 space-y-3">
              {initialTeams.map((team) => (
                <Link
                  className="flex flex-wrap items-center justify-between gap-4 border border-[var(--color-border)] p-4"
                  href={
                    "/admin/competitions/" +
                    competition.id +
                    "/teams/" +
                    team.id
                  }
                  key={team.id}
                >
                  <div>
                    <p className="font-medium">{team.name}</p>
                    <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                      {teamStatusLabel(team.status)} · {team.member_count} 人
                    </p>
                  </div>
                  <span className="font-mono text-xs text-[var(--color-info)]">
                    查看队伍详情 →
                  </span>
                </Link>
              ))}
            </div>
          </section>
        ) : null}
      </form>

      <aside className="space-y-4">
        <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-lg font-semibold">统计</h2>
          <dl className="mt-4 space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-[var(--color-text-muted)]">报名人数</dt>
              <dd>{initialCompetition?.registration_count ?? 0}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[var(--color-text-muted)]">队伍总数</dt>
              <dd>{initialCompetition?.team_count ?? 0}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[var(--color-text-muted)]">有效队伍</dt>
              <dd>{initialCompetition?.valid_team_count ?? 0}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[var(--color-text-muted)]">无效/取消资格</dt>
              <dd>{initialCompetition?.invalid_team_count ?? 0}</dd>
            </div>
          </dl>
        </section>
        {competition ? (
          <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 text-sm text-[var(--color-text-secondary)]">
            <p>报名截止：{formatDateTime(competition.registration_end)}</p>
            <p className="mt-2">
              赛事结束：{formatDateTime(competition.submission_end)}
            </p>
            <p className="mt-2">
              队伍人数：{competition.min_team_size}–
              {competition.max_team_size}
            </p>
          </section>
        ) : null}
      </aside>
    </div>
  );
}
