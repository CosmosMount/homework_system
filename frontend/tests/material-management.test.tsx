import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MaterialRegistration } from "@/components/materials/material-registration";
import { MaterialLedger } from "@/components/materials/material-ledger";
import { MaterialScanConfirmation } from "@/components/materials/material-scan-confirmation";
import type { MaterialScanView } from "@/lib/api/types";
import {
  d110BrowserAvailability,
  resolveD110PrintTaskName,
} from "@/lib/materials/d110-label";

const { apiFetchMock, csrfFetchMock, pushMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  csrfFetchMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  apiFetch: apiFetchMock,
  csrfFetch: csrfFetchMock,
  ApiError: class ApiError extends Error {},
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: vi.fn() }),
}));

const available: MaterialScanView = {
  id: "material-1",
  qr_token: "11111111-1111-4111-8111-111111111111",
  name: "示波器",
  price: "100.00",
  tech_group: "硬件",
  created_at: "2026-10-13T00:00:00Z",
  paired_material: { id: "material-2", name: "探头", deleted_at: null },
  active_loan: null,
  can_return: false,
  can_reclaim: false,
};

describe("物资扫码与登记", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    csrfFetchMock.mockReset();
    pushMock.mockReset();
  });

  it("打开扫码页只读取状态，显式确认后才领用整套物资", async () => {
    apiFetchMock.mockResolvedValue(available);
    csrfFetchMock.mockResolvedValue({
      material_id: available.id,
      related_material_ids: [available.id, "material-2"],
      material_name: "示波器 + 探头",
      operation: "CHECKOUT",
      occurred_at: "2026-10-13T01:00:00Z",
    });
    render(<MaterialScanConfirmation qrToken={available.qr_token} />);
    expect(await screen.findByText("配套物品：探头")).toBeInTheDocument();
    expect(csrfFetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认领用" }));
    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    const [path, init] = csrfFetchMock.mock.calls[0];
    expect(path).toBe("/materials/scan");
    expect(JSON.parse(init.body)).toMatchObject({
      qr_token: available.qr_token,
      operation: "CHECKOUT",
      expected_active_loan_id: null,
    });
    expect(await screen.findByText("领用成功")).toBeInTheDocument();
  });

  it("归还要求照片并以图片原始请求提交预期领用版本", async () => {
    apiFetchMock.mockResolvedValue({
      ...available,
      active_loan: {
        id: "22222222-2222-4222-8222-222222222222",
        borrower_user_id: "student-1",
        borrower_name: "测试学生",
        checked_out_at: "2026-10-13T00:00:00Z",
        returned_at: null,
        has_return_photo: false,
      },
      can_return: true,
    });
    csrfFetchMock.mockResolvedValue({ operation: "RETURN", material_name: "示波器 + 探头", occurred_at: "2026-10-13T02:00:00Z" });
    render(<MaterialScanConfirmation qrToken={available.qr_token} />);
    await screen.findByText("测试学生");
    fireEvent.click(screen.getByRole("button", { name: "确认归还" }));
    expect(screen.getByRole("alert")).toHaveTextContent("请先拍摄");
    const photo = new File(["\x89PNG\r\n\x1a\n"], "现场.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText(/归还照片/), { target: { files: [photo] } });
    fireEvent.click(screen.getByRole("button", { name: "确认归还" }));
    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    const [path, init] = csrfFetchMock.mock.calls[0];
    expect(path).toBe("/materials/scan/return");
    expect(init.body).toBe(photo);
    expect(init.headers["X-Material-Loan-Id"]).toBe("22222222-2222-4222-8222-222222222222");
    expect(init.headers["Content-Type"]).toBe("image/png");
  });

  it("批量配套登记提交两类单价和技术组", async () => {
    csrfFetchMock.mockResolvedValue({ material_id: "created-id", created_count: 6 });
    render(<MaterialRegistration />);
    fireEvent.change(screen.getByLabelText("物资名称"), { target: { value: "无线麦克" } });
    fireEvent.change(screen.getByLabelText("单件价格（元）"), { target: { value: "200" } });
    fireEvent.change(screen.getByLabelText("数量"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("所属技术组"), { target: { value: "通用" } });
    fireEvent.click(screen.getByLabelText(/配套物品（按同一序号成套）/));
    fireEvent.change(screen.getByLabelText("配套物品名称"), { target: { value: "接收器" } });
    fireEvent.change(screen.getByLabelText("配套物品单价（元）"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("配套物品技术组"), { target: { value: "硬件" } });
    fireEvent.click(screen.getByRole("button", { name: "确认登记" }));
    await waitFor(() => expect(csrfFetchMock).toHaveBeenCalledOnce());
    expect(JSON.parse(csrfFetchMock.mock.calls[0][1].body)).toMatchObject({
      name: "无线麦克", quantity: 3, paired: true,
      companion_name: "接收器", companion_price: "100", companion_tech_group: "硬件",
    });
    expect(pushMock).toHaveBeenCalledWith("/materials");
  });
});

it("D110 系列仅在安全来源和受支持协议中开放打印", () => {
  expect(d110BrowserAvailability({ isSecureContext: false, hasSerial: true }).available).toBe(false);
  expect(resolveD110PrintTaskName("D110", "D110")).toBe("D110");
  expect(resolveD110PrintTaskName("D110_M", "D110M_V4")).toBe("D110M_V4");
  expect(resolveD110PrintTaskName("B21", "B1")).toBeNull();
});

it("物资台账超过 100 件时可以翻页并保留跨页打印选择", async () => {
  apiFetchMock.mockReset();
  apiFetchMock.mockImplementation((path: string) => Promise.resolve({
    items: [{ ...available, id: path.includes("page=2") ? "material-2" : "material-1" }],
    page: path.includes("page=2") ? 2 : 1,
    page_size: 100,
    total_count: 102,
    in_use_count: 0,
    available_count: 102,
    has_more: !path.includes("page=2"),
  }));
  const { rerender } = render(<MaterialLedger filters={{ page: "1" }} />);
  await screen.findByRole("link", { name: "下一页" });
  fireEvent.click(screen.getByRole("checkbox", { name: "选择打印 示波器" }));
  rerender(<MaterialLedger filters={{ page: "2" }} />);
  await waitFor(() => expect(screen.getByText("第 2 页，显示 1 件")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("checkbox", { name: "选择打印 示波器" }));
  expect(screen.getByRole("button", { name: "打印所选标签（2）" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "上一页" })).toHaveAttribute("href", "/materials?page=1");
});
