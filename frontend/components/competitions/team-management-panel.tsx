"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { InviteCodeRotated, Team } from "@/lib/api/types";
import { teamStatusLabel, statusTagClass } from "@/lib/competition-labels";
import { formatDateTime } from "@/lib/format";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function TeamManagementPanel({
  initialTeam,
  currentUserId,
}: Readonly<{ initialTeam: Team; currentUserId: string }>) {
  const router = useRouter();
  const [team, setTeam] = useState(initialTeam);
  const [newCaptainId, setNewCaptainId] = useState("");
  const [oneTimeInviteCode, setOneTimeInviteCode] = useState<string | null>(
    null,
  );
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isCaptain = team.captain_user_id === currentUserId;
  const canManage = isCaptain && team.can_manage;

  function begin() {
    setPending(true);
    setMessage(null);
    setError(null);
  }

  async function rotateInvite() {
    if (!window.confirm("轮换后旧邀请码立即失效，确认继续？")) return;
    begin();
    try {
      const result = await csrfFetch<InviteCodeRotated>(
        "/teams/" + team.id + "/invite-code/rotate",
        { method: "POST" },
      );
      setOneTimeInviteCode(result.invite_code);
      setTeam((current) => ({ ...current, revision: result.revision }));
      setMessage("邀请码已轮换；新码只显示这一次。");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function removeMember(userId: string) {
    const leavingSelf = userId === currentUserId;
    if (
      !window.confirm(
        leavingSelf ? "确认退出当前队伍？" : "确认从队伍中移除该成员？",
      )
    ) {
      return;
    }
    begin();
    try {
      await csrfFetch("/teams/" + team.id + "/members/" + userId, {
        method: "DELETE",
      });
      if (leavingSelf) {
        router.push("/competitions/" + team.competition_id);
      } else {
        setTeam((current) => ({
          ...current,
          member_count: current.member_count - 1,
          members: current.members.filter((member) => member.user_id !== userId),
        }));
        setMessage("成员已移除。");
      }
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
    if (!window.confirm("确认转让队长？完成后你将失去队长管理权限。")) {
      return;
    }
    begin();
    try {
      const result = await csrfFetch<Team>(
        "/teams/" + team.id + "/captain-transfer",
        {
          method: "POST",
          body: JSON.stringify({ new_captain_user_id: newCaptainId }),
        },
      );
      setTeam(result);
      setNewCaptainId("");
      setMessage("队长已转让。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function dissolve() {
    if (!window.confirm("确认解散队伍？解散后需要重新创建或加入其他队伍。")) {
      return;
    }
    begin();
    try {
      await csrfFetch("/teams/" + team.id + "/dissolve", { method: "POST" });
      router.push("/competitions/" + team.competition_id);
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold">{team.name}</h2>
            <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
              当前 {team.member_count} 人，要求 {team.min_team_size}–
              {team.max_team_size} 人。
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

        {message ? (
          <div className="mt-5">
            <FormMessage tone="success">{message}</FormMessage>
          </div>
        ) : null}
        {error ? (
          <div className="mt-5">
            <FormMessage>{error}</FormMessage>
          </div>
        ) : null}
        {oneTimeInviteCode ? (
          <div className="mt-5 border border-[var(--color-warning)] bg-[var(--color-bg)] p-4">
            <p className="text-sm text-[var(--color-warning)]">
              新邀请码（仅显示一次）
            </p>
            <code className="mt-2 block select-all text-xl tracking-[0.14em]">
              {oneTimeInviteCode}
            </code>
          </div>
        ) : null}

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
                  {member.student_id} · 加入于 {formatDateTime(member.joined_at)}
                  {member.added_by_admin ? " · 管理员补录" : ""}
                </p>
              </div>
              {canManage && !member.is_captain ? (
                <button
                  className="min-h-10 border border-[var(--color-danger)] px-4 text-sm text-[var(--color-danger)]"
                  disabled={pending}
                  onClick={() => removeMember(member.user_id)}
                  type="button"
                >
                  移除
                </button>
              ) : null}
            </article>
          ))}
        </div>

        {!isCaptain && team.status === "forming" ? (
          <button
            className="mt-5 min-h-11 border border-[var(--color-danger)] px-5 text-[var(--color-danger)]"
            disabled={pending}
            onClick={() => removeMember(currentUserId)}
            type="button"
          >
            退出队伍
          </button>
        ) : null}
      </section>

      <aside className="space-y-4">
        {canManage ? (
          <section className="space-y-4 border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <h2 className="text-lg font-semibold">队长操作</h2>
            <button
              className={buttonClassName + " w-full"}
              disabled={pending}
              onClick={rotateInvite}
              type="button"
            >
              轮换邀请码
            </button>
            {team.members.length > 1 ? (
              <>
                <label className="block text-sm">
                  转让给
                  <select
                    className={inputClassName}
                    disabled={pending}
                    onChange={(event) => setNewCaptainId(event.target.value)}
                    value={newCaptainId}
                  >
                    <option value="">请选择成员</option>
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
                  disabled={pending}
                  onClick={transferCaptain}
                  type="button"
                >
                  转让队长
                </button>
              </>
            ) : (
              <button
                className="min-h-11 w-full border border-[var(--color-danger)] px-5 text-[var(--color-danger)]"
                disabled={pending}
                onClick={dissolve}
                type="button"
              >
                解散队伍
              </button>
            )}
          </section>
        ) : null}
        <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 text-sm text-[var(--color-text-secondary)]">
          <p>
            {team.status === "forming"
              ? "报名结束前，队长可以调整成员、轮换邀请码和转让队长。"
              : "队伍已锁定或进入终态，普通成员关系只读。"}
          </p>
          {team.min_size_waived ? (
            <p className="mt-3 text-[var(--color-warning)]">
              管理员已豁免最小人数：{team.waiver_reason}
            </p>
          ) : null}
          {team.disqualification_reason ? (
            <p className="mt-3 text-[var(--color-danger)]">
              取消资格原因：{team.disqualification_reason}
            </p>
          ) : null}
        </section>
      </aside>
    </div>
  );
}
