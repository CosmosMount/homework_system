"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { buttonClassName, inputClassName } from "@/components/ui/form-controls";
import { ApiError, csrfFetch } from "@/lib/api/client";
import { MATERIAL_TECH_GROUPS } from "@/lib/materials/presentation";

export function MaterialRegistration() {
  const router = useRouter();
  const [paired, setPaired] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [requestKey] = useState(() => crypto.randomUUID());

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    const form = new FormData(event.currentTarget);
    const quantity = Number(form.get("quantity"));
    try {
      const result = await csrfFetch<{ material_id: string; created_count: number }>("/materials", {
        method: "POST",
        body: JSON.stringify({
          name: String(form.get("name") ?? "").trim(),
          price: String(form.get("price") ?? "").trim(),
          tech_group: String(form.get("tech_group") ?? ""),
          quantity,
          paired,
          companion_name: paired ? String(form.get("companion_name") ?? "").trim() : null,
          companion_price: paired ? String(form.get("companion_price") ?? "").trim() : null,
          companion_tech_group: paired ? String(form.get("companion_tech_group") ?? "") : null,
          idempotency_key: requestKey,
        }),
      });
      router.push(quantity === 1 ? `/materials/${result.material_id}` : "/materials");
      router.refresh();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "登记失败，请重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Link className="text-sm text-[var(--color-info)] underline" href="/materials">← 返回物资台账</Link>
      <p className="mt-6 font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">MATERIALS / REGISTER</p>
      <h1 className="mt-2 text-3xl font-semibold">登记物资</h1>
      <p className="mt-2 text-sm text-[var(--color-text-secondary)]">每件物资都会生成独立的永久二维码。批量登记和配套登记在同一事务中完成。</p>
      <form className="mt-6 space-y-5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-7" onSubmit={(event) => void submit(event)}>
        <Field label="物资名称" name="name" maxLength={200} required placeholder="例如：示波器" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="单件价格（元）" name="price" required inputMode="decimal" pattern="(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?" placeholder="0.00" />
          <Field label="数量" name="quantity" required min={1} max={100} type="number" defaultValue="1" />
        </div>
        <label className="block text-sm font-medium" htmlFor="tech_group">所属技术组</label>
        <select className={inputClassName} defaultValue="" id="tech_group" name="tech_group" required>
          <option value="" disabled>请选择技术组</option>
          {MATERIAL_TECH_GROUPS.map((group) => <option key={group} value={group}>{group}</option>)}
        </select>
        <label className="flex items-center gap-3 text-sm"><input checked={paired} className="size-5" onChange={(event) => setPaired(event.target.checked)} type="checkbox" />配套物品（按同一序号成套）</label>
        {paired ? <fieldset className="space-y-4 rounded-xl border border-[var(--color-border)] p-4">
          <legend className="px-2 font-medium">配套物品</legend>
          <Field label="配套物品名称" name="companion_name" maxLength={200} required />
          <Field label="配套物品单价（元）" name="companion_price" required inputMode="decimal" pattern="(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?" />
          <label className="block text-sm font-medium" htmlFor="companion_tech_group">配套物品技术组</label>
          <select className={inputClassName} defaultValue="" id="companion_tech_group" name="companion_tech_group" required>
            <option value="" disabled>请选择技术组</option>
            {MATERIAL_TECH_GROUPS.map((group) => <option key={group} value={group}>{group}</option>)}
          </select>
        </fieldset> : null}
        {error ? <p className="text-sm text-[var(--color-danger)]" role="alert">{error}</p> : null}
        <button className={buttonClassName} disabled={pending} type="submit">{pending ? "正在登记…" : "确认登记"}</button>
      </form>
    </div>
  );
}

function Field({ label, name, ...props }: Readonly<{
  label: string;
  name: string;
} & React.InputHTMLAttributes<HTMLInputElement>>) {
  return <label className="block text-sm font-medium" htmlFor={name}>{label}<input {...props} className={inputClassName} id={name} name={name} /></label>;
}
