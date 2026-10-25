"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { buttonClassName } from "@/components/ui/form-controls";
import { ApiError, apiFetch, csrfFetch } from "@/lib/api/client";
import type { MaterialScanResult, MaterialScanView } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { materialPrice } from "@/lib/materials/presentation";

export function MaterialScanConfirmation({ qrToken }: Readonly<{ qrToken: string }>) {
  const [material, setMaterial] = useState<MaterialScanView | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [photo, setPhoto] = useState<File | null>(null);
  const [success, setSuccess] = useState<MaterialScanResult | null>(null);
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());

  async function refresh() {
    try {
      setMaterial(await apiFetch<MaterialScanView>(`/materials/scan/${qrToken}`));
      setRequestKey(crypto.randomUUID());
      setError("");
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "物资状态加载失败。");
    }
  }

  useEffect(() => {
    let active = true;
    void apiFetch<MaterialScanView>(`/materials/scan/${qrToken}`)
      .then((value) => { if (active) setMaterial(value); })
      .catch((failure: unknown) => {
        if (active) setError(failure instanceof ApiError ? failure.message : "物资状态加载失败。");
      });
    return () => { active = false; };
  }, [qrToken]);

  const operation = !material?.active_loan
    ? "CHECKOUT"
    : material.can_return
      ? "RETURN"
      : material.can_reclaim
        ? "RECLAIM"
        : null;

  async function submit() {
    if (!material || !operation) return;
    if (operation !== "CHECKOUT" && !photo) {
      setError("请先拍摄物资归还照片。");
      return;
    }
    if (photo && photo.size > 8 * 1024 * 1024) {
      setError("归还照片不能超过 8 MiB。");
      return;
    }
    setPending(true);
    setError("");
    try {
      let result: MaterialScanResult;
      if (operation === "CHECKOUT") {
        result = await csrfFetch<MaterialScanResult>("/materials/scan", {
          method: "POST",
          body: JSON.stringify({
            qr_token: qrToken,
            operation,
            expected_active_loan_id: null,
            idempotency_key: requestKey,
          }),
        });
      } else {
        result = await csrfFetch<MaterialScanResult>("/materials/scan/return", {
          method: "POST",
          body: photo!,
          headers: {
            "Content-Type": photo!.type,
            "X-Material-Qr-Token": qrToken,
            "X-Material-Operation": operation,
            "X-Material-Loan-Id": material.active_loan!.id,
            "Idempotency-Key": requestKey,
          },
        });
      }
      setSuccess(result);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "操作失败，请重试。");
    } finally {
      setPending(false);
    }
  }

  return <div className="mx-auto max-w-xl space-y-6">
    <Link className="text-sm text-[var(--color-info)] underline" href="/materials">← 返回物资台账</Link>
    <header>
      <p className="font-mono text-xs tracking-[0.18em] text-[var(--color-accent)]">MATERIALS / SCAN</p>
      <h1 className="mt-2 text-3xl font-semibold">扫码领用 / 归还</h1>
      <p className="mt-2 text-sm text-[var(--color-text-secondary)]">请核对实物及状态，再手动确认。</p>
    </header>
    {error ? <p className="rounded-lg border border-[var(--color-danger)] p-3 text-sm text-[var(--color-danger)]" role="alert">{error}</p> : null}
    {success ? <section className="space-y-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-center" role="status">
      <h2 className="text-xl font-semibold">{success.operation === "CHECKOUT" ? "领用成功" : "归还成功"}</h2>
      <p>{success.material_name} · {formatDateTime(success.occurred_at)}</p>
      <Link className="text-[var(--color-info)] underline" href="/materials">返回物资台账</Link>
    </section> : material ? <section className="space-y-5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="text-center">
        <h2 className="break-words text-xl font-semibold">{material.name}</h2>
        {material.paired_material ? <p className="mt-1 text-sm">配套物品：{material.paired_material.name}</p> : null}
        <p className="mt-2 text-sm">{material.tech_group} · {material.active_loan ? "使用中" : "可领用"}</p>
      </div>
      <dl className="grid grid-cols-2 gap-3 rounded-lg bg-[var(--color-surface-raised)] p-4 text-sm">
        <div><dt className="text-[var(--color-text-muted)]">价格</dt><dd>{materialPrice(material.price)}</dd></div>
        <div><dt className="text-[var(--color-text-muted)]">当前使用人</dt><dd>{material.active_loan?.borrower_name ?? "无人使用"}</dd></div>
      </dl>
      {operation ? <div className="space-y-4">
        <p className="text-sm text-[var(--color-text-secondary)]">{operation === "CHECKOUT"
          ? material.paired_material ? "确认后将同时领用这套物资。" : "确认后将由当前登录账号领用。"
          : operation === "RECLAIM" ? "原领用人账号已注销。管理员须拍摄现场照片后处理遗留占用。"
          : material.paired_material ? "请拍摄包含两件配套物品的现场照片，确认后整套归还。" : "请拍摄物资当前状态。照片将在下一位用户领用后清理。"}</p>
        {operation !== "CHECKOUT" ? <label className="block text-sm font-medium" htmlFor="return-photo">归还照片
          <input accept="image/png,image/jpeg,image/webp,image/heic,image/heif,image/avif" capture="environment" className="mt-2 block w-full text-sm" id="return-photo" onChange={(event) => setPhoto(event.target.files?.[0] ?? null)} type="file" />
          <span className="mt-2 block text-xs text-[var(--color-text-muted)]">最大 8 MiB；手机优先打开后置摄像头。</span>
        </label> : null}
        <button className={`${buttonClassName} w-full`} disabled={pending} onClick={() => void submit()} type="button">{pending ? "正在处理…" : operation === "CHECKOUT" ? "确认领用" : "确认归还"}</button>
      </div> : <p className="rounded-lg border border-[var(--color-border)] p-4 text-sm" role="alert">该物资当前由 {material.active_loan?.borrower_name} 使用，只有领用人可以归还。</p>}
      <button className="text-sm text-[var(--color-info)] underline" onClick={() => void refresh()} type="button">刷新物资状态</button>
      <p className="text-center text-xs text-[var(--color-text-muted)]">打开二维码或相机预览不会自动领用或归还。</p>
    </section> : !error ? <p role="status">正在读取物资状态…</p> : null}
  </div>;
}
