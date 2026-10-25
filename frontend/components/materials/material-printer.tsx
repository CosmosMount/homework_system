"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  ImageEncoder,
  LabelType,
  NiimbotSerialClient,
  PageColorType,
} from "@mmote/niimbluelib";

import {
  D110_PRINT_DIRECTION,
  d110BrowserAvailability,
  d110PrintErrorMessage,
  isD110PrinterModel,
  resolveD110PrintTaskName,
  runD110MultiPagePrintSequence,
  type D110LabelContent,
} from "@/lib/materials/d110-label";
import { renderD110Label } from "@/lib/materials/d110-label-renderer";
import { buttonClassName } from "@/components/ui/form-controls";

const subscribe = () => () => undefined;

export function MaterialPrinter({ items, label }: Readonly<{ items: D110LabelContent[]; label: string }>) {
  const clientRef = useRef<NiimbotSerialClient | null>(null);
  const mountedRef = useRef(true);
  const [connected, setConnected] = useState(false);
  const browserReady = useSyncExternalStore(subscribe, () => true, () => false);
  const availability = browserReady
    ? d110BrowserAvailability({
        isSecureContext: window.isSecureContext,
        hasSerial: "serial" in navigator,
      })
    : null;
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const client = clientRef.current;
      clientRef.current = null;
      if (client?.isConnected()) void client.disconnect().catch(() => undefined);
    };
  }, []);

  async function print() {
    if (!availability?.available || busy || items.length === 0) return;
    setBusy(true);
    setMessage(connected ? "正在准备标签…" : "正在准备标签并连接打印机…");
    try {
      const encoded = items.map((item) => ImageEncoder.encodeCanvas(
        renderD110Label(item), PageColorType.SingleColor, D110_PRINT_DIRECTION,
      ));
      let client = clientRef.current;
      if (!client?.isConnected()) {
        client = new NiimbotSerialClient();
        clientRef.current = client;
        await client.connect();
        if (!mountedRef.current || clientRef.current !== client) {
          if (client.isConnected()) await client.disconnect();
          return;
        }
      }
      if (!isD110PrinterModel(client.getModelMetadata()?.model)) {
        throw new Error("UNSUPPORTED_MODEL");
      }
      const taskName = resolveD110PrintTaskName(
        client.getModelMetadata()?.model,
        client.getPrintTaskType(),
      );
      if (!taskName) throw new Error("UNSUPPORTED_PROTOCOL");
      setConnected(true);
      const task = client.abstraction.newPrintTask(taskName, {
        density: 2,
        labelType: LabelType.WithGaps,
        pageColor: PageColorType.SingleColor,
        totalPages: encoded.length,
      });
      await runD110MultiPagePrintSequence(
        task, encoded,
        (completed, total) => setMessage(`已打印 ${completed} / ${total} 张标签`),
      );
      setMessage(`打印完成，共 ${items.length} 张。连接已保留，可继续打印。`);
    } catch (error) {
      setMessage(d110PrintErrorMessage(error));
      const client = clientRef.current;
      clientRef.current = null;
      if (client?.isConnected()) await client.disconnect().catch(() => undefined);
      setConnected(false);
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      const client = clientRef.current;
      if (client?.isConnected()) await client.disconnect();
      clientRef.current = null;
      setConnected(false);
      setMessage("已断开打印机，下次打印可重新选择设备。");
    } catch (error) {
      setMessage(d110PrintErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <button className={buttonClassName} disabled={!availability?.available || busy || items.length === 0} onClick={() => void print()} type="button">
        {busy ? "正在打印…" : label}
      </button>
      {connected ? <button className="text-sm underline" disabled={busy} onClick={() => void disconnect()} type="button">断开打印机</button> : null}
      <p className="text-xs text-[var(--color-text-muted)]" role="status" aria-live="polite">
        {message || availability?.message || "正在检查浏览器打印能力…"}
      </p>
      {availability?.available === false ? <p className="text-xs text-[var(--color-text-muted)]">可下载二维码，或在支持 Web Serial 的桌面 Chrome / Edge 中通过 HTTPS 打开本页打印。</p> : null}
    </div>
  );
}
