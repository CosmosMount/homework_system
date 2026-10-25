"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import QRCode from "qrcode";

import { materialScanUrl } from "@/lib/materials/presentation";

export function MaterialQrCode({ token, name }: Readonly<{ token: string; name: string }>) {
  const origin = useSyncExternalStore(() => () => undefined, () => window.location.origin, () => "");
  const url = origin ? materialScanUrl(token, origin) : "";
  const [image, setImage] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!url) return;
    void QRCode.toDataURL(url, { width: 320, margin: 3, errorCorrectionLevel: "M" })
      .then(setImage)
      .catch(() => setMessage("二维码生成失败，请刷新页面。"));
  }, [url]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setMessage("扫码链接已复制。");
    } catch {
      setMessage("复制失败，请手动复制下方链接。");
    }
  }

  return <div className="space-y-3">
    {image ? <a download={`${name}-二维码.png`} href={image} title="下载二维码">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img alt={`${name}专属领用二维码`} className="w-full max-w-64 rounded-lg border border-[var(--color-border)] bg-white p-2" src={image} />
    </a> : <p>正在生成二维码…</p>}
    <div className="flex flex-wrap gap-3 text-sm">
      {image ? <a className="text-[var(--color-info)] underline" download={`${name}-二维码.png`} href={image}>下载二维码</a> : null}
      <button className="text-[var(--color-info)] underline" onClick={() => void copy()} type="button">复制扫码链接</button>
    </div>
    <p className="break-all text-xs text-[var(--color-text-muted)]">{url}</p>
    {message ? <p className="text-xs" role="status">{message}</p> : null}
  </div>;
}
