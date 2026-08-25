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
  CompetitionDetail,
  Registration,
  Team,
  TeamCreated,
} from "@/lib/api/types";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function CompetitionRegistrationActions({
  competition,
}: Readonly<{ competition: CompetitionDetail }>) {
  const router = useRouter();
  const [registrationStatus, setRegistrationStatus] = useState(
    competition.registration_status,
  );
  const [teamId, setTeamId] = useState(competition.team_id);
  const [teamName, setTeamName] = useState(competition.team_name);
  const [newTeamName, setNewTeamName] = useState("");
  const [inviteCodeInput, setInviteCodeInput] = useState("");
  const [oneTimeInviteCode, setOneTimeInviteCode] = useState<string | null>(
    null,
  );
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const registrationOpen = competition.status === "registration_open";

  function begin() {
    setPending(true);
    setMessage(null);
    setError(null);
  }

  async function register() {
    begin();
    try {
      const registration = await csrfFetch<Registration>(
        "/competitions/" + competition.id + "/registration",
        { method: "POST" },
      );
      setRegistrationStatus(registration.status);
      setMessage("报名成功。现在可以创建队伍或使用邀请码加入。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function withdraw() {
    if (!window.confirm("确认撤回本赛事报名？撤回后可在报名期重新报名。")) {
      return;
    }
    begin();
    try {
      await csrfFetch(
        "/competitions/" + competition.id + "/registration",
        { method: "DELETE" },
      );
      setRegistrationStatus("withdrawn");
      setMessage("报名已撤回。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function createTeam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newTeamName.trim()) {
      setError("队伍名称不能为空。");
      return;
    }
    begin();
    try {
      const created = await csrfFetch<TeamCreated>(
        "/competitions/" + competition.id + "/teams",
        {
          method: "POST",
          body: JSON.stringify({ name: newTeamName.trim() }),
        },
      );
      setTeamId(created.id);
      setTeamName(created.name);
      setOneTimeInviteCode(created.invite_code);
      setMessage("队伍已创建。邀请码只显示这一次，请立即安全发送给队友。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  async function joinTeam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!inviteCodeInput.trim()) {
      setError("请输入邀请码。");
      return;
    }
    begin();
    try {
      const joined = await csrfFetch<Team>(
        "/competitions/" + competition.id + "/teams/join",
        {
          method: "POST",
          body: JSON.stringify({ invite_code: inviteCodeInput.trim() }),
        },
      );
      setTeamId(joined.id);
      setTeamName(joined.name);
      setInviteCodeInput("");
      setMessage("已加入队伍“" + joined.name + "”。");
      router.refresh();
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
      <h2 className="text-xl font-semibold">我的参赛状态</h2>
      {message ? (
        <div className="mt-4">
          <FormMessage tone="success">{message}</FormMessage>
        </div>
      ) : null}
      {error ? (
        <div className="mt-4">
          <FormMessage>{error}</FormMessage>
        </div>
      ) : null}

      {oneTimeInviteCode ? (
        <div className="mt-4 border border-[var(--color-warning)] bg-[var(--color-bg)] p-4">
          <p className="text-sm text-[var(--color-warning)]">
            一次性显示的邀请码
          </p>
          <code className="mt-2 block select-all text-xl tracking-[0.14em]">
            {oneTimeInviteCode}
          </code>
          <p className="mt-2 text-xs text-[var(--color-text-muted)]">
            离开页面后无法再次读取；如遗失，请在队伍页轮换。
          </p>
        </div>
      ) : null}

      {teamId ? (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border border-[var(--color-border)] p-4">
          <div>
            <p className="text-sm text-[var(--color-text-muted)]">当前队伍</p>
            <p className="mt-1 font-medium">{teamName}</p>
          </div>
          <Link
            className="min-h-11 border border-[var(--color-info)] px-5 py-2 text-[var(--color-info)]"
            href={"/competitions/" + competition.id + "/team"}
          >
            进入我的队伍
          </Link>
        </div>
      ) : registrationStatus === "disqualified" ? (
        <div className="mt-4 border-l-2 border-[var(--color-danger)] px-4 text-sm text-[var(--color-text-secondary)]">
          <p>你已被取消本赛事参赛资格，不能重新报名。</p>
          {competition.registration_disqualification_reason ? (
            <p className="mt-2 text-[var(--color-danger)]">
              原因：{competition.registration_disqualification_reason}
            </p>
          ) : null}
        </div>
      ) : registrationStatus === "registered" ? (
        registrationOpen ? (
          <div className="mt-5 grid gap-5 lg:grid-cols-2">
            <form
              className="space-y-4 border border-[var(--color-border)] p-4"
              onSubmit={createTeam}
            >
              <h3 className="font-medium">创建队伍</h3>
              <label className="block text-sm">
                队伍名称
                <input
                  className={inputClassName}
                  disabled={pending}
                  maxLength={120}
                  onChange={(event) => setNewTeamName(event.target.value)}
                  value={newTeamName}
                />
              </label>
              <button className={buttonClassName} disabled={pending} type="submit">
                创建并成为队长
              </button>
            </form>
            <form
              className="space-y-4 border border-[var(--color-border)] p-4"
              onSubmit={joinTeam}
            >
              <h3 className="font-medium">使用邀请码加入</h3>
              <label className="block text-sm">
                邀请码
                <input
                  autoCapitalize="characters"
                  className={inputClassName + " font-mono tracking-wider"}
                  disabled={pending}
                  maxLength={64}
                  onChange={(event) => setInviteCodeInput(event.target.value)}
                  value={inviteCodeInput}
                />
              </label>
              <button className={buttonClassName} disabled={pending} type="submit">
                加入队伍
              </button>
            </form>
            <button
              className="min-h-11 justify-self-start border border-[var(--color-danger)] px-5 text-[var(--color-danger)] lg:col-span-2"
              disabled={pending}
              onClick={withdraw}
              type="button"
            >
              撤回报名
            </button>
          </div>
        ) : (
          <p className="mt-4 text-sm text-[var(--color-text-secondary)]">
            你已报名，但报名期已经结束且没有当前队伍，请联系管理员处理。
          </p>
        )
      ) : registrationOpen ? (
        <button
          className={buttonClassName + " mt-5"}
          disabled={pending}
          onClick={register}
          type="button"
        >
          {pending ? "处理中…" : "报名参赛"}
        </button>
      ) : (
        <p className="mt-4 text-sm text-[var(--color-text-secondary)]">
          当前不在报名期，无法新报名。
        </p>
      )}
    </section>
  );
}
