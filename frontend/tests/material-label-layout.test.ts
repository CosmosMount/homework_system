import QRCode from "qrcode";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderD110Label } from "@/lib/materials/d110-label-renderer";
import { materialScanUrl } from "@/lib/materials/presentation";
import { d110PrintErrorMessage } from "@/lib/materials/d110-label";

afterEach(() => vi.restoreAllMocks());

describe("标签优先保留二维码点阵和静区", () => {
  it.each(["http://10.4.150.222:5000", "https://pnx-tutorial.demonmaster.cn"])(
    "%s 的每个二维码模块均为完整整数方块，名称不进入静区",
    (origin) => {
      const pixels = new Uint8Array(240 * 96);
      const context = {
        fillStyle: "", font: "", textBaseline: "",
        fillRect: vi.fn((x: number, y: number, width: number, height: number) => {
          expect([x, y, width, height].every(Number.isInteger)).toBe(true);
          for (let row = y; row < y + height; row += 1) {
            for (let column = x; column < x + width; column += 1) {
              pixels[row * 240 + column] = context.fillStyle === "#000000" ? 1 : 0;
            }
          }
        }),
        measureText: (text: string) => ({ width: [...text].length * 14 }),
        fillText: vi.fn(), save: vi.fn(), restore: vi.fn(),
        beginPath: vi.fn(), rect: vi.fn(), clip: vi.fn(),
      };
      vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
        context as unknown as CanvasRenderingContext2D,
      );
      const token = "019a1b3c-8e7f-73de-abcd-123456789abc";
      const scanUrl = materialScanUrl(token, origin);
      const decoded = new URL(scanUrl);
      expect(decoded.origin).toBe(origin);
      expect(decoded.pathname).toBe(`/materials/scan/${token.toUpperCase()}`);
      const canvas = renderD110Label({
        materialName: "很长的物资名称".repeat(20), price: "￥100.00", techGroup: "机械", scanUrl,
      });
      expect([canvas.width, canvas.height]).toEqual([240, 96]);
      const qr = QRCode.create(scanUrl, { errorCorrectionLevel: "M" });
      const size = qr.modules.size;
      const scale = 2;
      const qrWidth = (size + 8) * scale;
      const top = Math.floor((96 - qrWidth) / 2);
      const textX = 8 + qrWidth + 4;
      // Compare all pixels, including the four-module quiet zone and paper edges.
      for (let y = 0; y < 96; y += 1) {
        for (let x = 0; x < textX; x += 1) {
          const row = Math.floor((y - top) / scale) - 4;
          const column = Math.floor((x - 8) / scale) - 4;
          const expected = row >= 0 && column >= 0 && row < size && column < size
            ? Number(qr.modules.get(row, column)) : 0;
          expect(pixels[y * 240 + x]).toBe(expected);
        }
      }
      expect(context.rect).toHaveBeenCalledWith(textX, 0, 240 - textX - 4, 96);
      const lines = context.fillText.mock.calls.slice(0, 2);
      expect(lines[1][0]).toMatch(/…$/);
      for (const [text, x] of lines) {
        expect(x).toBe(textX);
        expect(context.measureText(text).width).toBeLessThanOrEqual(240 - textX - 4);
      }
    },
  );

  it("超长链接明确拒绝打印，不压缩到单点模块", () => {
    expect(() => renderD110Label({
      materialName: "物资", price: "￥1", techGroup: "通用",
      scanUrl: `https://example.com/${"x".repeat(250)}`,
    })).toThrow("QR_TOO_DENSE");
    expect(d110PrintErrorMessage(new Error("QR_TOO_DENSE"))).toContain("链接过长");
  });
});
