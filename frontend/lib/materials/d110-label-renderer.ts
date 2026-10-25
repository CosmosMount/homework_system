import QRCode from "qrcode";

import {
  D110_LABEL_HEIGHT_PX,
  D110_LABEL_WIDTH_PX,
  D110_QR_MARGIN_MODULES,
  fitD110LabelLines,
  type D110LabelContent,
} from "@/lib/materials/d110-label";

export function renderD110Label(content: D110LabelContent): HTMLCanvasElement {
  const qr = QRCode.create(content.scanUrl, { errorCorrectionLevel: "M" });
  const moduleCount = qr.modules.size;
  const totalModules = moduleCount + 2 * D110_QR_MARGIN_MODULES;
  // Reserve paper-edge clearance, then give the QR the largest whole-dot scale.
  const scale = Math.floor((D110_LABEL_HEIGHT_PX - 4) / totalModules);
  if (scale < 2) throw new Error("QR_TOO_DENSE");
  const qrSize = totalModules * scale;
  const qrX = 8;
  const qrY = Math.floor((D110_LABEL_HEIGHT_PX - qrSize) / 2);
  const textX = qrX + qrSize + 4;
  const textWidth = D110_LABEL_WIDTH_PX - textX - 4;

  const canvas = document.createElement("canvas");
  canvas.width = D110_LABEL_WIDTH_PX;
  canvas.height = D110_LABEL_HEIGHT_PX;
  const context = canvas.getContext("2d", { alpha: false });
  if (!context) throw new Error("CANVAS_UNAVAILABLE");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#000000";
  // Draw modules directly: resizing a QR bitmap distorts its finder patterns.
  for (let row = 0; row < moduleCount; row += 1) {
    for (let column = 0; column < moduleCount; column += 1) {
      if (qr.modules.get(row, column)) {
        context.fillRect(
          qrX + (column + D110_QR_MARGIN_MODULES) * scale,
          qrY + (row + D110_QR_MARGIN_MODULES) * scale,
          scale, scale,
        );
      }
    }
  }

  // Text is confined to the remaining space, including its antialiased edges.
  context.save();
  context.beginPath();
  context.rect(textX, 0, textWidth, canvas.height);
  context.clip();
  context.textBaseline = "top";
  context.font = "700 14px sans-serif";
  fitD110LabelLines(context, content.materialName, textWidth, 2).forEach(
    (line, index) => context.fillText(line, textX, 6 + index * 17),
  );
  context.font = "11px sans-serif";
  context.fillText(`组别：${content.techGroup}`, textX, 45, textWidth);
  context.font = "700 12px sans-serif";
  context.fillText(content.price, textX, 62, textWidth);
  context.font = "10px sans-serif";
  context.fillText("扫码领用 / 归还", textX, 81, textWidth);
  context.restore();
  return canvas;
}
