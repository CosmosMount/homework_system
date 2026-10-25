"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { MaterialPrinter } from "@/components/materials/material-printer";
import { buttonClassName, buttonLinkClassName, inputClassName } from "@/components/ui/form-controls";
import { ApiError, apiFetch } from "@/lib/api/client";
import type { MaterialItem, MaterialPage } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { MATERIAL_TECH_GROUPS, materialPrice, materialScanUrl } from "@/lib/materials/presentation";

type Filters = { q?: string; tech_group?: string; status?: string; page?: string };

export function MaterialLedger({ filters }: Readonly<{ filters: Filters }>) {
  const query = (filters.q ?? "").slice(0, 200);
  const techGroup = MATERIAL_TECH_GROUPS.find((item) => item === filters.tech_group) ?? "";
  const status = filters.status === "AVAILABLE" || filters.status === "IN_USE" ? filters.status : "";
  const pageNumber = /^\d+$/.test(filters.page ?? "")
    ? Math.min(100000, Math.max(1, Number(filters.page))) : 1;
  const [page, setPage] = useState<MaterialPage | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<MaterialItem[]>([]);
  const origin = useSyncExternalStore(() => () => undefined, () => window.location.origin, () => "");

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams();
    if (query) params.set("query", query);
    if (techGroup) params.set("tech_group", techGroup);
    if (status) params.set("status", status);
    params.set("page", String(pageNumber));
    void apiFetch<MaterialPage>(`/materials?${params}`)
      .then((value) => { if (active) setPage(value); })
      .catch((failure: unknown) => {
        if (active) setError(failure instanceof ApiError ? failure.message : "物资台账加载失败。");
      });
    return () => { active = false; };
  }, [query, techGroup, status, pageNumber]);

  const printItems = useMemo(() => selected.map((item) => ({
    materialName: item.name,
    price: materialPrice(item.price),
    scanUrl: origin ? materialScanUrl(item.qr_token, origin) : "",
    techGroup: item.tech_group,
  })), [selected, origin]);

  function toggle(item: MaterialItem, checked: boolean) {
    setSelected((current) => checked
      ? current.some((selectedItem) => selectedItem.id === item.id) ? current : [...current, item]
      : current.filter((selectedItem) => selectedItem.id !== item.id));
  }

  function pageHref(number: number) {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (techGroup) params.set("tech_group", techGroup);
    if (status) params.set("status", status);
    params.set("page", String(number));
    return `/materials?${params}`;
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">MATERIALS / LEDGER</p>
          <h1 className="mt-2 text-3xl font-semibold">物资台账</h1>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">查看每件物资的使用状态，扫描实物二维码领用或拍照归还。</p>
        </div>
        <Link className={buttonLinkClassName} href="/materials/new">登记物资</Link>
      </header>

      {page ? <section aria-label="物资状态概览" className="grid gap-3 sm:grid-cols-3">
        {[["全部物资", page.total_count], ["正在使用", page.in_use_count], ["当前可用", page.available_count]].map(([label, value]) => (
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5" key={label}>
            <p className="text-sm text-[var(--color-text-secondary)]">{label}</p>
            <p className="mt-2 text-3xl font-semibold">{value}</p>
          </div>
        ))}
      </section> : null}

      <form className="grid gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-[1fr_10rem_9rem_auto]" method="get">
        <input aria-label="搜索物资名称" className={inputClassName} defaultValue={query} maxLength={200} name="q" placeholder="搜索物资名称" />
        <select aria-label="所属技术组" className={inputClassName} defaultValue={techGroup} name="tech_group">
          <option value="">全部技术组</option>
          {MATERIAL_TECH_GROUPS.map((group) => <option key={group} value={group}>{group}</option>)}
        </select>
        <select aria-label="使用状态" className={inputClassName} defaultValue={status} name="status">
          <option value="">全部状态</option><option value="AVAILABLE">可领用</option><option value="IN_USE">使用中</option>
        </select>
        <button className={buttonClassName} type="submit">筛选</button>
      </form>

      {error ? <p role="alert" className="text-[var(--color-danger)]">{error}</p> : null}
      {!page && !error ? <p role="status">正在加载物资台账…</p> : null}
      {page ? <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-[var(--color-text-secondary)]">第 {page.page} 页，显示 {page.items.length} 件</p>
          <div className="flex flex-wrap items-center gap-3">
            <button className="text-sm text-[var(--color-info)] underline" onClick={() => setSelected((current) => [...current, ...page.items.filter((item) => !current.some((selectedItem) => selectedItem.id === item.id))])} type="button">全选当前页</button>
            <button className="text-sm text-[var(--color-info)] underline" onClick={() => setSelected([])} type="button">清空</button>
            <MaterialPrinter items={printItems} label={`打印所选标签（${selected.length}）`} />
          </div>
        </div>
        {page.items.length === 0 ? <p className="rounded-xl border border-[var(--color-border)] p-6">暂无符合条件的物资。</p> : null}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {page.items.map((item) => <article className="min-w-0 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)]" key={item.id}>
            <div className="flex items-start gap-3">
              <input aria-label={`选择打印 ${item.name}`} checked={selected.some((selectedItem) => selectedItem.id === item.id)} className="mt-1 size-5" onChange={(event) => toggle(item, event.target.checked)} type="checkbox" />
              <div className="min-w-0 flex-1">
                <Link className="break-words text-lg font-semibold text-[var(--color-accent)] hover:underline" href={`/materials/${item.id}`}>{item.name}</Link>
                {item.paired_material ? <p className="mt-1 text-xs text-[var(--color-text-muted)]">配套：{item.paired_material.name}</p> : null}
              </div>
              <span className="shrink-0 rounded-full border border-[var(--color-border)] px-2 py-1 text-xs">{item.active_loan ? "使用中" : "可领用"}</span>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-[var(--color-text-muted)]">单价</dt><dd>{materialPrice(item.price)}</dd></div>
              <div><dt className="text-[var(--color-text-muted)]">技术组</dt><dd>{item.tech_group}</dd></div>
              <div><dt className="text-[var(--color-text-muted)]">当前使用人</dt><dd>{item.active_loan?.borrower_name ?? "无人使用"}</dd></div>
              <div><dt className="text-[var(--color-text-muted)]">领用时间</dt><dd>{formatDateTime(item.active_loan?.checked_out_at ?? null)}</dd></div>
            </dl>
            <Link className="mt-4 inline-block text-sm text-[var(--color-info)] underline" href={`/materials/scan/${item.qr_token}`}>扫码确认页</Link>
          </article>)}
        </div>
        <nav aria-label="物资台账分页" className="flex items-center justify-center gap-5 text-sm">
          {page.page > 1 ? <Link className="text-[var(--color-info)] underline" href={pageHref(page.page - 1)}>上一页</Link> : null}
          <span>第 {page.page} 页</span>
          {page.has_more ? <Link className="text-[var(--color-info)] underline" href={pageHref(page.page + 1)}>下一页</Link> : null}
        </nav>
      </section> : null}
    </div>
  );
}
