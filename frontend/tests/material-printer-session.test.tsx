import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MaterialPrinter } from "@/components/materials/material-printer";

const mocks = vi.hoisted(() => ({
  connect: vi.fn(), disconnect: vi.fn(), printPage: vi.fn(), render: vi.fn(),
  connected: false,
}));
vi.mock("@/lib/materials/d110-label-renderer", () => ({ renderD110Label: mocks.render }));
vi.mock("@mmote/niimbluelib", () => ({
  ImageEncoder: { encodeCanvas: vi.fn(() => "image") },
  PageColorType: { SingleColor: 1 }, LabelType: { WithGaps: 1 },
  NiimbotSerialClient: class {
    connect = mocks.connect;
    disconnect = mocks.disconnect;
    isConnected = () => mocks.connected;
    getModelMetadata = () => ({ model: "D110" });
    getPrintTaskType = () => "D110";
    abstraction = { newPrintTask: () => ({
      printInit: vi.fn().mockResolvedValue(undefined), printPage: mocks.printPage,
      waitForPageFinished: vi.fn().mockResolvedValue(undefined),
      waitForFinished: vi.fn().mockResolvedValue(undefined),
      printEnd: vi.fn().mockResolvedValue(true),
    }) };
  },
}));
const items = [{ materialName: "物资", price: "¥1", techGroup: "机械", scanUrl: "https://example.com" }];
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("isSecureContext", true);
  Object.defineProperty(navigator, "serial", { configurable: true, value: {} });
  mocks.connected = false;
  mocks.connect.mockImplementation(async () => { mocks.connected = true; });
  mocks.disconnect.mockImplementation(async () => { mocks.connected = false; });
  mocks.render.mockReturnValue({});
  mocks.printPage.mockResolvedValue(undefined);
});
afterEach(() => vi.unstubAllGlobals());

it("连续打印只选择一次设备，显式断开后才重新连接", async () => {
  render(<MaterialPrinter items={items} label="打印" />);
  const button = screen.getByRole("button", { name: "打印" });
  fireEvent.click(button);
  await screen.findByText(/连接已保留/);
  fireEvent.click(button);
  await waitFor(() => expect(mocks.printPage).toHaveBeenCalledTimes(2));
  await screen.findByText(/连接已保留/);
  expect(mocks.connect).toHaveBeenCalledTimes(1);
  expect(mocks.disconnect).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "断开打印机" }));
  await screen.findByText(/已断开打印机/);
  fireEvent.click(button);
  await waitFor(() => expect(mocks.printPage).toHaveBeenCalledTimes(3));
  expect(mocks.connect).toHaveBeenCalledTimes(2);
});

it("标签不合格时不打开设备选择框", async () => {
  mocks.render.mockImplementationOnce(() => { throw new Error("QR_TOO_DENSE"); });
  render(<MaterialPrinter items={items} label="打印" />);
  fireEvent.click(screen.getByRole("button", { name: "打印" }));
  await screen.findByText(/链接过长/);
  expect(mocks.connect).not.toHaveBeenCalled();
});

it("打印失败释放连接，重试可重新选择设备", async () => {
  mocks.printPage.mockRejectedValueOnce(new Error("device removed"));
  render(<MaterialPrinter items={items} label="打印" />);
  fireEvent.click(screen.getByRole("button", { name: "打印" }));
  await waitFor(() => expect(mocks.disconnect).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "打印" }));
  await screen.findByText(/连接已保留/);
  expect(mocks.connect).toHaveBeenCalledTimes(2);
});

it("离开页面释放已连接的打印机", async () => {
  const { unmount } = render(<MaterialPrinter items={items} label="打印" />);
  fireEvent.click(screen.getByRole("button", { name: "打印" }));
  await screen.findByText(/连接已保留/);
  unmount();
  expect(mocks.disconnect).toHaveBeenCalledTimes(1);
});
