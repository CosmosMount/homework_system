"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { buttonClassName, FormMessage, inputClassName } from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { SelfDirectionOptions, User } from "@/lib/api/types";

export function DirectionSelector({ user, options }: Readonly<{
  user: User;
  options: SelfDirectionOptions;
}>) {
  const router = useRouter();
  const [current, setCurrent] = useState(user);
  const [directionId, setDirectionId] = useState(user.direction?.id ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function save() {
    if (!directionId || !window.confirm("确认修改技术方向？队伍配置会按新方向重新校验，新方向的历史作业将追加，旧作业和提交仍保留。")) return;
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await csrfFetch<User>("/users/me/direction", {
        method: "PATCH",
        body: JSON.stringify({ direction_id: directionId, revision: current.revision }),
      });
      setCurrent(updated);
      setMessage("技术方向已更新，匹配的历史作业已同步。");
      router.refresh();
    } catch (nextError) {
      setError(nextError instanceof ApiError ? nextError.message : "修改失败，请稍后重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mt-8 rounded-2xl border border-[var(--color-border)] p-5">
      <h2 className="text-xl font-semibold">修改技术方向</h2>
      <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
        {options.is_direction_change_open
          ? "管理员已开放自助修改。队伍按当前技术组计算名额；改方向不会删除旧作业或提交。"
          : "管理员暂未开放自助修改技术方向，如需调整请联系管理员。"}
      </p>
      {options.is_direction_change_open ? (
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="grid gap-2 text-sm">
            技术方向
            <select className={inputClassName} disabled={pending} value={directionId}
              onChange={(event) => setDirectionId(event.target.value)}>
              <option value="">请选择技术方向</option>
              {options.directions.map((direction) => (
                <option key={direction.id} value={direction.id}>{direction.name}</option>
              ))}
            </select>
          </label>
          <button className={buttonClassName} disabled={pending || !directionId || directionId === current.direction?.id}
            type="button" onClick={save}>{pending ? "保存中…" : "保存技术方向"}</button>
        </div>
      ) : null}
      {message ? <div className="mt-3"><FormMessage tone="success">{message}</FormMessage></div> : null}
      {error ? <div className="mt-3"><FormMessage>{error}</FormMessage></div> : null}
    </section>
  );
}
