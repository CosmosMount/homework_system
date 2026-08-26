"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { AdminTeamDetail, Team, User } from "@/lib/api/types";
import { statusTagClass, teamStatusLabel } from "@/lib/competition-labels";
import { formatDateTime } from "@/lib/format";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function AdminTeamCorrectionPanel({
  initialTeam,
  users,
}: Readonly<{ initialTeam: AdminTeamDetail; users: User[] }>) {
  const router = useRouter();
  const [team, setTeam] = useState(initialTeam);
  const [reason, setReason] = useState("");
  const [addUserId, setAddUserId] = useState("");
  const [newCaptainId, setNewCaptainId] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const currentIds = useMemo(
    () => new Set(team.members.map((member) => member.user_id)),
    [team.members],
  );
  const candidates = users.filter(
    (user) =>
      user.role === "student" &&
      user.status === "active" &&
      !currentIds.has(user.id),
  );

  function begin(): boolean {
    if (!reason.trim()) {
      setError("管理员纠错必须填写原因。");
      return false;
    }
    setPending(true);
    setMessage(null);
    setError(null);
    return true;
  }

  function mergeTeam(result: Team) {
    setTeam((current) => ({ ...result, submissions: current.submissions }));
  }

  async function addMember() {
    if (!addUserId) {
      setError("请选择需要补录的学生。");
      return;
    }
    if (!begin()) return;
    try {
      const result = await csrfFetch<Team>(
        "/admin/teams/" + team.id + "/members",
        {
          method: "POST",
          body: JSON.stringify({
            user_id: addUserId,
            reason: reason.trim(),
          }),
        },
      );
      mergeTeam(result);
      setAddUserId("");
      setReason("");
      setMessage("成员已补录并写入审计。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function removeMember(userId: string) {
    if (!begin()) return;
    if (!window.confirm("确认以管理员身份移除该成员？此操作会审计原因。")) {
      setPending(false);
      return;
    }
    try {
      const result = await csrfFetch<Team>(
        "/admin/teams/" + team.id + "/members/" + userId,
        {
          method: "DELETE",
          body: JSON.stringify({ reason: reason.trim() }),
        },
      );
      mergeTeam(result);
      setReason("");
      setMessage("成员已移除并写入审计。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function transferCaptain() {
    if (!newCaptainId) {
      setError("请选择新队长。");
      return;
    }
    if (!begin()) return;
    try {
      const result = await csrfFetch<Team>(
        "/admin/teams/" + team.id + "/captain-transfer",
        {
          method: "POST",
          body: JSON.stringify({
            new_captain_user_id: newCaptainId,
            reason: reason.trim(),
          }),
        },
      );
      mergeTeam(result);
      setNewCaptainId("");
      setReason("");
      setMessage("队长已变更并写入审计。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function reasonAction(action: "waive-min-size" | "disqualify") {
    if (!begin()) return;
    if (
      action === "disqualify" &&
      !window.confirm("确认取消整支队伍参赛资格？该队将不能继续参赛。")
    ) {
      setPending(false);
      return;
    }
    try {
      const result = await csrfFetch<Team>(
        "/admin/teams/" + team.id + "/" + action,
        {
          method: "POST",
          body: JSON.stringify({ reason: reason.trim() }),
        },
      );
      mergeTeam(result);
      setReason("");
      setMessage(
        action === "waive-min-size"
          ? "最小人数已豁免并写入审计。"
          : "队伍已取消资格并写入审计。",
      );
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  const mutable = !["dissolved", "archived"].includes(team.status);

  return (
    <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1fr)_23rem]">
      <div className="space-y-6">
        {message ? <FormMessage tone="success">{message}</FormMessage> : null}
        {error ? <FormMessage>{error}</FormMessage> : null}

        <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold">{team.name}</h2>
              <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                {team.member_count} 人 · 要求 {team.min_team_size}–
                {team.max_team_size} 人
              </p>
            </div>
            <span
              className={
                "border px-2 py-1 font-mono text-xs " +
                statusTagClass(team.status)
              }
            >
              {teamStatusLabel(team.status)}
            </span>
          </div>
          <div className="mt-6 space-y-3">
            {team.members.map((member) => (
              <article
                className="flex flex-wrap items-center justify-between gap-4 border border-[var(--color-border)] p-4"
                key={member.user_id}
              >
                <div>
                  <p className="font-medium">
                    {member.full_name}
                    {member.is_captain ? (
                      <span className="ml-2 font-mono text-xs text-[var(--color-accent-hover)]">
                        CAPTAIN
                      </span>
                    ) : null}
                  </p>
                  <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                    {member.student_id} · {formatDateTime(member.joined_at)}
                    {member.added_by_admin ? " · 管理员补录" : ""}
                  </p>
                </div>
                {mutable && !member.is_captain ? (
                  <button
                    className="min-h-10 border border-[var(--color-danger)] px-4 text-sm text-[var(--color-danger)]"
                    disabled={pending}
                    onClick={() => removeMember(member.user_id)}
                    type="button"
                  >
                    管理员移除
                  </button>
                ) : null}
              </article>
            ))}
          </div>
        </section>

      </div>

      <aside>
        <section className="space-y-4 border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-lg font-semibold">管理员纠错</h2>
          <label className="block text-sm">
            必填原因
            <textarea
              className={inputClassName + " min-h-28 py-3"}
              disabled={!mutable || pending}
              maxLength={2000}
              onChange={(event) => setReason(event.target.value)}
              value={reason}
            />
          </label>
          <label className="block text-sm">
            补录学生
            <select
              className={inputClassName}
              disabled={!mutable || pending}
              onChange={(event) => setAddUserId(event.target.value)}
              value={addUserId}
            >
              <option value="">请选择已报名学生</option>
              {candidates.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.full_name} · {user.student_number}
                </option>
              ))}
            </select>
          </label>
          <button
            className={buttonClassName + " w-full"}
            disabled={!mutable || pending}
            onClick={addMember}
            type="button"
          >
            补录成员
          </button>
          <label className="block text-sm">
            新队长
            <select
              className={inputClassName}
              disabled={!mutable || pending}
              onChange={(event) => setNewCaptainId(event.target.value)}
              value={newCaptainId}
            >
              <option value="">请选择当前成员</option>
              {team.members
                .filter((member) => !member.is_captain)
                .map((member) => (
                  <option key={member.user_id} value={member.user_id}>
                    {member.full_name}
                  </option>
                ))}
            </select>
          </label>
          <button
            className="min-h-11 w-full border border-[var(--color-info)] px-5 text-[var(--color-info)]"
            disabled={!mutable || pending}
            onClick={transferCaptain}
            type="button"
          >
            变更队长
          </button>
          {!team.min_size_waived ? (
            <button
              className="min-h-11 w-full border border-[var(--color-warning)] px-5 text-[var(--color-warning)]"
              disabled={!mutable || pending}
              onClick={() => reasonAction("waive-min-size")}
              type="button"
            >
              豁免最小人数
            </button>
          ) : null}
          {team.status !== "disqualified" ? (
            <button
              className="min-h-11 w-full border border-[var(--color-danger)] px-5 text-[var(--color-danger)]"
              disabled={!mutable || pending}
              onClick={() => reasonAction("disqualify")}
              type="button"
            >
              取消队伍资格
            </button>
          ) : null}
        </section>
      </aside>
    </div>
  );
}
