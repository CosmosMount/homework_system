"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  buttonClassName,
  FormMessage,
  inputClassName,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type {
  Team,
  TeamInvitation,
  TeamProfile,
  TeamProfilePage,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function TeamProfileDirectory({
  currentUserId,
  directionId,
  hasTeam,
  initialInvitations,
  initialProfile,
  initialProfiles,
  query,
  teamCanInvite,
  teamOpen,
}: Readonly<{
  currentUserId: string;
  directionId: string;
  hasTeam: boolean;
  initialInvitations: TeamInvitation[];
  initialProfile: TeamProfile | null;
  initialProfiles: TeamProfilePage;
  query: string;
  teamCanInvite: boolean;
  teamOpen: boolean;
}>) {
  const router = useRouter();
  const [introduction, setIntroduction] = useState(
    initialProfile?.introduction ?? "",
  );
  const [profile, setProfile] = useState(initialProfile);
  const [invitations, setInvitations] = useState(initialInvitations);
  const [sentUserIds, setSentUserIds] = useState(
    () =>
      new Set(
        initialProfiles.items
          .filter((item) => item.invitation_pending)
          .map((item) => item.user_id),
      ),
  );
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const page = initialProfiles.page;
  const hasNext = page * initialProfiles.page_size < initialProfiles.total;

  function begin(action: string) {
    setPendingAction(action);
    setMessage(null);
    setError(null);
  }

  async function saveProfile() {
    const normalized = introduction.trim();
    if (!normalized) {
      setError("请填写个人简介。");
      return;
    }
    begin("profile");
    try {
      const result = await csrfFetch<TeamProfile>("/team-profiles/me", {
        method: "PUT",
        body: JSON.stringify({
          introduction: normalized,
          revision: profile?.revision ?? null,
        }),
      });
      const wasPublished = profile !== null;
      setIntroduction(result.introduction);
      setProfile(result);
      setMessage(wasPublished ? "个人简介已更新。" : "个人简介已发布。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPendingAction(null);
    }
  }

  async function invite(profileUserId: string) {
    begin("invite:" + profileUserId);
    try {
      await csrfFetch<TeamInvitation>("/team-invitations", {
        method: "POST",
        body: JSON.stringify({ invitee_user_id: profileUserId }),
      });
      setSentUserIds((current) => new Set(current).add(profileUserId));
      setMessage("组队邀请已发送，对方确认后才会加入队伍。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPendingAction(null);
    }
  }

  async function respond(invitationId: string, accept: boolean) {
    if (accept && !window.confirm("接受后将加入该队伍，确认继续？")) return;
    begin("respond:" + invitationId);
    try {
      if (accept) {
        await csrfFetch<Team>(
          "/team-invitations/" + invitationId + "/accept",
          { method: "POST" },
        );
        router.push("/competitions");
      } else {
        await csrfFetch(
          "/team-invitations/" + invitationId + "/decline",
          { method: "POST" },
        );
        setInvitations((current) =>
          current.filter((item) => item.id !== invitationId),
        );
        setMessage("已拒绝邀请。");
      }
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPendingAction(null);
    }
  }

  function pageHref(nextPage: number): string {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (directionId) params.set("direction_id", directionId);
    if (nextPage > 1) params.set("page", String(nextPage));
    const suffix = params.toString();
    return "/competitions/profiles" + (suffix ? "?" + suffix : "");
  }

  return (
    <>
      {message ? (
        <div className="mt-6">
          <FormMessage tone="success">{message}</FormMessage>
        </div>
      ) : null}
      {error ? (
        <div className="mt-6">
          <FormMessage>{error}</FormMessage>
        </div>
      ) : null}

      <section className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <p className="text-xs font-medium tracking-[0.14em] text-[var(--color-text-muted)]">
          MY TEAM PROFILE
        </p>
        <h2 className="mt-1 text-xl font-semibold">我的组队简介</h2>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
          发布后，所有登录学生都能在本页看到这段简介。请勿填写手机号、住址等敏感信息。
        </p>
        <label className="mt-5 block text-sm font-medium">
          个人简介
          <textarea
            className={inputClassName + " min-h-36 resize-y"}
            disabled={pendingAction !== null}
            maxLength={2000}
            onChange={(event) => setIntroduction(event.target.value)}
            placeholder="介绍你的技术方向、经验、兴趣和希望寻找的队友"
            value={introduction}
          />
        </label>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs text-[var(--color-text-muted)]">
            {introduction.length} / 2000
          </span>
          <button
            className={buttonClassName}
            disabled={pendingAction !== null}
            onClick={saveProfile}
            type="button"
          >
            {pendingAction === "profile"
              ? "保存中…"
              : profile
                ? "更新简介"
                : "发布简介"}
          </button>
        </div>
      </section>

      {teamOpen && invitations.length > 0 ? (
        <section className="mt-8 rounded-2xl border border-[var(--color-info)] bg-[var(--color-surface)] p-5 sm:p-6">
          <p className="text-xs font-medium tracking-[0.14em] text-[var(--color-info)]">
            PENDING INVITATIONS
          </p>
          <h2 className="mt-1 text-xl font-semibold">收到的组队邀请</h2>
          <div className="mt-5 space-y-3">
            {invitations.map((invitation) => (
              <article
                className="flex flex-wrap items-center justify-between gap-4 border border-[var(--color-border)] p-4"
                key={invitation.id}
              >
                <div>
                  <h3 className="font-medium">{invitation.team_name}</h3>
                  <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
                    {invitation.invited_by_full_name} 邀请你加入
                  </p>
                  <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                    {formatDateTime(invitation.created_at)}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    className={buttonClassName}
                    disabled={pendingAction !== null}
                    onClick={() => respond(invitation.id, true)}
                    type="button"
                  >
                    接受
                  </button>
                  <button
                    className="min-h-11 border border-[var(--color-border-strong)] px-4 text-sm"
                    disabled={pendingAction !== null}
                    onClick={() => respond(invitation.id, false)}
                    type="button"
                  >
                    拒绝
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className="mt-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-medium tracking-[0.14em] text-[var(--color-text-muted)]">
              PROFILE DIRECTORY
            </p>
            <h2 className="mt-1 text-xl font-semibold">组队个人简介</h2>
          </div>
          <p className="text-sm text-[var(--color-text-secondary)]">
            共 {initialProfiles.total} 份
          </p>
        </div>
        <form className="mt-5 grid gap-3 sm:grid-cols-[minmax(0,1fr)_13rem_auto]" role="search">
          <label className="min-w-0 text-sm font-medium">
            搜索姓名、方向或简介
            <input
              className={inputClassName}
              defaultValue={query}
              maxLength={120}
              name="q"
              placeholder="例如：视觉、机械设计"
              type="search"
            />
          </label>
          <label className="text-sm font-medium">
            技术组
            <select className={inputClassName} defaultValue={directionId} name="direction_id">
              <option value="">全部技术组</option>
              {initialProfiles.directions.map((direction) => (
                <option key={direction.id} value={direction.id}>
                  {direction.name}
                </option>
              ))}
            </select>
          </label>
          <button className={buttonClassName + " sm:self-end"} type="submit">
            搜索
          </button>
        </form>
        {!teamOpen ? (
          <p className="mt-4 text-sm text-[var(--color-text-secondary)]">
            组队暂未开放；个人简介仍可正常填写、浏览和按技术组筛选。
          </p>
        ) : !hasTeam ? (
          <p className="mt-4 text-sm text-[var(--color-text-secondary)]">
            你可以浏览所有已发布简介；创建或加入队伍后即可邀请同学。
          </p>
        ) : !teamCanInvite ? (
          <p className="mt-4 text-sm text-[var(--color-text-secondary)]">
            当前队伍人数已满，暂时不能继续邀请。
          </p>
        ) : null}
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {initialProfiles.items.map((item) => {
            const sent = sentUserIds.has(item.user_id);
            return (
              <article
                className="flex min-h-52 flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-5"
                key={item.user_id}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-semibold">{item.full_name}</h3>
                    <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                      {item.direction_name ?? "未设置技术方向"}
                    </p>
                  </div>
                  {item.user_id === currentUserId ? (
                    <span className="border border-[var(--color-accent)] px-2 py-1 text-xs text-[var(--color-accent)]">
                      我的简介
                    </span>
                  ) : null}
                </div>
                <p className="mt-4 flex-1 whitespace-pre-wrap text-sm leading-6 text-[var(--color-text-secondary)]">
                  {item.introduction}
                </p>
                <div className="mt-4 flex items-center justify-between gap-3">
                  <span className="text-xs text-[var(--color-text-muted)]">
                    更新于 {formatDateTime(item.updated_at)}
                  </span>
                  {teamOpen && item.can_invite && !sent ? (
                    <button
                      className={buttonClassName}
                      disabled={pendingAction !== null}
                      onClick={() => invite(item.user_id)}
                      type="button"
                    >
                      {pendingAction === "invite:" + item.user_id
                        ? "发送中…"
                        : "邀请组队"}
                    </button>
                  ) : teamOpen && sent ? (
                    <span className="text-xs text-[var(--color-info)]">已邀请</span>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
        {initialProfiles.items.length === 0 ? (
          <p className="mt-5 rounded-xl border border-dashed border-[var(--color-border-strong)] p-8 text-center text-[var(--color-text-muted)]">
            暂无匹配的个人简介。
          </p>
        ) : null}
        <nav aria-label="个人简介分页" className="mt-5 flex items-center justify-between text-sm">
          {page > 1 ? (
            <Link className="text-[var(--color-info)]" href={pageHref(page - 1)}>
              ← 上一页
            </Link>
          ) : (
            <span />
          )}
          <span className="font-mono text-xs text-[var(--color-text-muted)]">
            第 {page} 页
          </span>
          {hasNext ? (
            <Link className="text-[var(--color-info)]" href={pageHref(page + 1)}>
              下一页 →
            </Link>
          ) : (
            <span />
          )}
        </nav>
      </section>
    </>
  );
}
