"use client";

import { type FormEvent, useState } from "react";

import {
  buttonClassName,
  Field,
  FormMessage,
} from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { Direction } from "@/lib/api/types";

export function CategoryAdminPanel({
  initialDirections,
}: Readonly<{
  initialDirections: Direction[];
}>) {
  const [directions, setDirections] = useState(initialDirections);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleError(nextError: unknown) {
    setError(
      nextError instanceof ApiError ? nextError.message : "操作失败，请稍后重试。",
    );
  }

  async function createDirection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    setError(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const direction = await csrfFetch<Direction>("/admin/directions", {
        method: "POST",
        body: JSON.stringify({
          code: data.get("code"),
          name: data.get("name"),
          description: data.get("description") || null,
        }),
      });
      setDirections((current) => [...current, direction]);
      setMessage("方向已创建。");
      form.reset();
    } catch (nextError) {
      handleError(nextError);
    } finally {
      setPending(false);
    }
  }

  async function toggleDirection(direction: Direction) {
    setPending(true);
    setError(null);
    try {
      const updated = await csrfFetch<Direction>(
        "/admin/directions/" + direction.id,
        {
          method: "PATCH",
          body: JSON.stringify({
            revision: direction.revision,
            is_active: !direction.is_active,
          }),
        },
      );
      setDirections((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (nextError) {
      handleError(nextError);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mt-8 space-y-8">
      {message ? <FormMessage tone="success">{message}</FormMessage> : null}
      {error ? <FormMessage>{error}</FormMessage> : null}
      <section className="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <form
          className="space-y-4 border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
          onSubmit={createDirection}
        >
          <h2 className="text-lg font-medium">新建方向</h2>
          <Field label="编码" name="code" placeholder="robotics" required />
          <Field label="名称" name="name" placeholder="机器人" required />
          <Field
            label="说明"
            maxLength={1000}
            name="description"
            placeholder="可选说明"
          />
          <button
            className={buttonClassName + " w-full"}
            disabled={pending}
            type="submit"
          >
            创建方向
          </button>
        </form>
        <div className="border border-[var(--color-border)]">
          {directions.map((direction) => (
            <div
              className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--color-border)] p-5 last:border-b-0"
              key={direction.id}
            >
              <div>
                <h3 className="font-medium">{direction.name}</h3>
                <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
                  {direction.code}
                </p>
                {direction.description ? (
                  <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                    {direction.description}
                  </p>
                ) : null}
              </div>
              <button
                className="min-h-10 border border-[var(--color-border-strong)] px-4 text-sm disabled:opacity-50"
                disabled={pending}
                onClick={() => toggleDirection(direction)}
                type="button"
              >
                {direction.is_active ? "停用" : "启用"}
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
