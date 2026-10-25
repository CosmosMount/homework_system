"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, apiFetch, csrfFetch } from "@/lib/api/client";
import type { InviteCodeRotated, Team, TeamApplication } from "@/lib/api/types";
import { teamStatusLabel, statusTagClass } from "@/lib/competition-labels";
import { formatDateTime } from "@/lib/format";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function TeamManagementPanel({
  initialTeam,
  currentUserId,
  initialApplications = [],
}: Readonly<{ initialTeam: Team; currentUserId: string; initialApplications?: TeamApplication[] }>) {
  const router = useRouter();
  const [team, setTeam] = useState(initialTeam);
  const [newCaptainId, setNewCaptainId] = useState("");
  const [newName, setNewName] = useState(initialTeam.name);
  const [applications, setApplications] = useState(initialApplications);
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

  async function renameTeam() {
    if (!newName.trim()) { setError("请输入队伍名称。"); return; }
    begin();
    try {
      const updated = await csrfFetch<Team>(`/teams/${team.id}/name`, {
        method: "PATCH", body: JSON.stringify({ name: newName.trim(), revision: team.revision }),
      });
      setTeam(updated);
      setNewName(updated.name);
      setMessage("队名已更新。");
      router.refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally { setPending(false); }
  }

  async function respondToApplication(applicationId: string, accept: boolean) {
    if (!window.confirm(accept ? "同意申请？已有队伍的申请人会立即换到本队。" : "拒绝这条入队申请？")) return;
    begin();
    try {
      await csrfFetch(`/teams/${team.id}/applications/${applicationId}/${accept ? "accept" : "decline"}`, { method: "POST" });
      setApplications((current) => current.filter((item) => item.id !== applicationId));
      const updated = await apiFetch<Team | null>("/teams/me");
      if (updated) setTeam(updated);
      setMessage(accept ? "已同意申请，申请人已加入队伍。" : "已拒绝申请。");
      router.refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally { setPending(false); }
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
        router.push("/competitions");
      } else {
        const updated = await apiFetch<Team | null>("/teams/me");
        if (updated) setTeam(updated);
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
      router.push("/competitions");
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
              当前 {team.member_count} / {team.max_members} 人。
              {team.composition ? (
                <span className="mt-2 block">
                  机械 {team.composition.mechanical}/2（至少 1 人） · 嵌入式控制 {team.composition.embedded_control}/1 · 嵌入式硬件 {team.composition.embedded_hardware}/1 · 算法 {team.composition.algorithm}/1
                  {team.composition.unassigned > 0 ? ` · 未匹配方向 ${team.composition.unassigned} 人` : ""}
                  {team.composition.is_complete ? " · 配置已齐全" : " · 配置待补齐或调整"}
                </span>
              ) : null}
              <span className="mt-2 block text-sm text-[var(--color-text-secondary)]">
                队长邮箱：{team.captain_email || "未提供"}
                {team.contact_wechat ? ` · 队伍微信：${team.contact_wechat}` : ""}
              </span>
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
                  {member.student_number} · 加入于 {formatDateTime(member.joined_at)}
                  {member.added_by_admin ? " · 管理员补录" : ""}
                </p>
                <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                  {member.direction_name ?? "未设置技术方向"}
                </p>
                {member.introduction ? (
                  <p className="mt-2 max-w-2xl whitespace-pre-wrap text-sm leading-6 text-[var(--color-text-secondary)]">
                    {member.introduction}
                  </p>
                ) : null}
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
            <label className="block text-sm">队伍名称
              <input className={inputClassName} disabled={pending} maxLength={120} onChange={(event) => setNewName(event.target.value)} value={newName} />
            </label>
            <button className={buttonClassName + " w-full"} disabled={pending || newName.trim() === team.name} onClick={renameTeam} type="button">更改队名</button>
            <div className="border-t border-[var(--color-border)] pt-4">
              <h3 className="font-medium">入队申请 {applications.length > 0 ? `(${applications.length})` : ""}</h3>
              {applications.length === 0 ? <p className="mt-2 text-sm text-[var(--color-text-muted)]">暂无待处理申请。</p> : null}
              {applications.map((application) => (
                <div className="mt-3 border border-[var(--color-border)] p-3" key={application.id}>
                  <p className="text-sm">{application.applicant_full_name}</p>
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">申请于 {formatDateTime(application.created_at)}</p>
                  <div className="mt-3 flex gap-2">
                    <button className="min-h-10 border border-[var(--color-info)] px-3 text-sm text-[var(--color-info)]" disabled={pending} onClick={() => respondToApplication(application.id, true)} type="button">同意</button>
                    <button className="min-h-10 border border-[var(--color-danger)] px-3 text-sm text-[var(--color-danger)]" disabled={pending} onClick={() => respondToApplication(application.id, false)} type="button">拒绝</button>
                  </div>
                </div>
              ))}
            </div>
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
              ? "所有成员都可从个人简介页邀请同学；当前队长可以调整成员、轮换邀请码并把队长身份转让给其他成员。"
              : "队伍已解散，成员关系只读。"}
          </p>
        </section>
      </aside>
    </div>
  );
}
