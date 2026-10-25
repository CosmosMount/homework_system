"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { MaterialPrinter } from "@/components/materials/material-printer";
import { MaterialQrCode } from "@/components/materials/material-qr-code";
import { buttonClassName } from "@/components/ui/form-controls";
import { ApiError, apiFetch, csrfFetch } from "@/lib/api/client";
import type { MaterialDetail } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { materialPrice, materialScanUrl } from "@/lib/materials/presentation";

export function MaterialInformation({ materialId }: Readonly<{ materialId: string }>) {
  const [material, setMaterial] = useState<MaterialDetail | null>(null);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const origin = useSyncExternalStore(() => () => undefined, () => window.location.origin, () => "");

  useEffect(() => {
    void apiFetch<MaterialDetail>(`/materials/${materialId}`)
      .then(setMaterial)
      .catch((failure: unknown) => setError(failure instanceof ApiError ? failure.message : "物资详情加载失败。"));
  }, [materialId]);

  async function remove() {
    if (!material) return;
    const suffix = material.paired_material ? `及配套物品“${material.paired_material.name}”` : "";
    if (!window.confirm(`确定删除“${material.name}”${suffix}吗？删除后二维码将停用，历史记录仍保留。`)) return;
    setDeleting(true);
    setError("");
    try {
      await csrfFetch<void>(`/materials/${material.id}`, { method: "DELETE" });
      setMaterial(await apiFetch<MaterialDetail>(`/materials/${material.id}`));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "删除失败，请重试。");
    } finally {
      setDeleting(false);
    }
  }

  if (error && !material) return <p role="alert">{error}</p>;
  if (!material) return <p role="status">正在加载物资详情…</p>;
  return <div className="space-y-6">
    <Link className="text-sm text-[var(--color-info)] underline" href="/materials">← 返回物资台账</Link>
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">MATERIALS / DETAIL</p>
        <h1 className="mt-2 break-words text-3xl font-semibold">{material.name}</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">查看物资信息、专属二维码和领用历史。</p>
      </div>
      {material.can_delete ? <button className={buttonClassName} disabled={deleting || Boolean(material.active_loan)} onClick={() => void remove()} type="button">{deleting ? "正在删除…" : "删除物资"}</button> : null}
    </header>
    {error ? <p className="text-[var(--color-danger)]" role="alert">{error}</p> : null}
    {material.deleted_at ? <p className="rounded-xl border border-[var(--color-border)] p-4" role="status">物资已删除（{formatDateTime(material.deleted_at)}），原二维码已停用。以下保留历史信息。</p> : null}
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="space-y-6">
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-xl font-semibold">物资信息</h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <Info label="名称" value={material.name} />
            <Info label="单价" value={materialPrice(material.price)} />
            <Info label="技术组" value={material.tech_group} />
            <Info label="登记人" value={material.created_by_name} />
            <Info label="登记时间" value={formatDateTime(material.created_at)} />
            {material.paired_material ? <div><dt className="text-sm text-[var(--color-text-muted)]">配套物品</dt><dd><Link className="text-[var(--color-info)] underline" href={`/materials/${material.paired_material.id}`}>{material.paired_material.name}</Link></dd></div> : null}
          </dl>
        </section>
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-xl font-semibold">当前状态</h2>
          <p className="mt-3">{material.deleted_at ? "已删除" : material.active_loan ? "使用中" : "可领用"}</p>
          {material.active_loan ? <p className="mt-2 text-sm">{material.active_loan.borrower_name} · {formatDateTime(material.active_loan.checked_out_at)} 领用</p> : null}
          {!material.deleted_at ? <Link className="mt-4 inline-block text-sm text-[var(--color-info)] underline" href={`/materials/scan/${material.qr_token}`}>打开扫码确认页</Link> : null}
        </section>
        <section>
          <h2 className="text-xl font-semibold">领用历史</h2>
          {material.history.length === 0 ? <p className="mt-3">暂无领用记录。</p> : <ol className="mt-4 space-y-3">
            {material.history.map((loan) => <li className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4" key={loan.id}>
              <p className="font-medium">{loan.borrower_name}</p>
              <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{formatDateTime(loan.checked_out_at)} 领用 · {loan.returned_at ? `${formatDateTime(loan.returned_at)} 归还` : "尚未归还"}</p>
              {loan.has_return_photo ? <a className="mt-3 inline-block" href={`/api/v1/materials/loans/${loan.id}/photo`} rel="noreferrer" target="_blank">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img alt={`${loan.borrower_name}的物资归还照片`} className="h-24 w-24 rounded-lg border border-[var(--color-border)] object-cover" src={`/api/v1/materials/loans/${loan.id}/photo`} />
              </a> : null}
            </li>)}
          </ol>}
        </section>
      </div>
      {!material.deleted_at ? <aside className="h-fit space-y-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 lg:sticky lg:top-6">
        <h2 className="text-xl font-semibold">专属二维码</h2>
        <p className="text-sm text-[var(--color-text-secondary)]">二维码长期对应此物资。请从正式域名打开后下载并粘贴到实物上。</p>
        <MaterialQrCode token={material.qr_token} name={material.name} />
        <MaterialPrinter items={origin ? [{ materialName: material.name, price: materialPrice(material.price), techGroup: material.tech_group, scanUrl: materialScanUrl(material.qr_token, origin) }] : []} label="连接 D110 系列并打印" />
      </aside> : null}
    </div>
  </div>;
}

function Info({ label, value }: Readonly<{ label: string; value: string }>) {
  return <div><dt className="text-sm text-[var(--color-text-muted)]">{label}</dt><dd className="mt-1 break-words font-medium">{value}</dd></div>;
}
