import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TeamSettingsPanel } from "@/components/competitions/team-settings-panel";
import { DirectionSelector } from "@/components/profile/direction-selector";
import { ApiError, csrfFetch } from "@/lib/api/client";
import type { SelfDirectionOptions, TeamSettings, User } from "@/lib/api/types";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()), csrfFetch: vi.fn(),
}));
const request = vi.mocked(csrfFetch);
const student: User = {
  id: "student", email: "student@connect.hkust-gz.edu.cn", student_number: "S001",
  full_name: "测试学生", role: "student", status: "active", cohort: null, direction: null,
  email_verified_at: "2026-09-10T00:00:00Z", created_at: "2026-09-10T00:00:00Z", revision: 3,
};
const options: SelfDirectionOptions = {
  is_direction_change_open: true,
  directions: [{ id: "mechanical", code: "mechanical", name: "机械" }],
};
const settings: TeamSettings = {
  is_team_open: true, is_direction_change_open: false,
  updated_at: "2026-09-10T00:00:00Z", revision: 2,
};

describe("student direction permission", () => {
  beforeEach(() => {
    request.mockReset();
    refresh.mockReset();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("shows a closed notice without editable controls", () => {
    render(<DirectionSelector user={student} options={{ ...options, is_direction_change_open: false }} />);
    expect(screen.getByText(/管理员暂未开放自助修改/)).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it("submits only the selected direction and current revision", async () => {
    request.mockResolvedValue({ ...student, direction: options.directions[0], revision: 4 });
    render(<DirectionSelector user={student} options={options} />);
    fireEvent.change(screen.getByRole("combobox", { name: "技术方向" }), { target: { value: "mechanical" } });
    fireEvent.click(screen.getByRole("button", { name: "保存技术方向" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    expect(request).toHaveBeenCalledWith("/users/me/direction", {
      method: "PATCH", body: JSON.stringify({ direction_id: "mechanical", revision: 3 }),
    });
    expect(screen.getByRole("button", { name: "保存技术方向" })).toBeDisabled();
  });

  it("shows backend revocation or quota errors without reporting success", async () => {
    request.mockRejectedValue(new ApiError(new Response(null, { status: 403 }), {
      error: { code: "DIRECTION_CHANGE_CLOSED", message: "管理员已关闭修改权限。", request_id: "test" },
    }));
    render(<DirectionSelector user={student} options={options} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "mechanical" } });
    fireEvent.click(screen.getByRole("button", { name: "保存技术方向" }));
    expect(await screen.findByText("管理员已关闭修改权限。")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("updates direction permission without changing team enrollment", async () => {
    request.mockResolvedValue({ ...settings, is_direction_change_open: true, revision: 3 });
    render(<TeamSettingsPanel initialSettings={settings} />);
    fireEvent.click(screen.getByRole("button", { name: "开放学生修改方向" }));
    await screen.findByRole("button", { name: "关闭学生修改方向" });
    expect(screen.getByRole("button", { name: "关闭学生组队" })).toBeInTheDocument();
    expect(request).toHaveBeenCalledWith("/admin/team-settings", {
      method: "PATCH", body: JSON.stringify({ is_direction_change_open: true, revision: 2 }),
    });
  });

  it("updates enrollment without changing direction permission", async () => {
    request.mockResolvedValue({ ...settings, is_team_open: false, revision: 3 });
    render(<TeamSettingsPanel initialSettings={settings} />);
    fireEvent.click(screen.getByRole("button", { name: "关闭学生组队" }));
    await screen.findByRole("button", { name: "开放学生组队" });
    expect(screen.getByRole("button", { name: "开放学生修改方向" })).toBeInTheDocument();
    expect(request).toHaveBeenCalledWith("/admin/team-settings", {
      method: "PATCH", body: JSON.stringify({ is_team_open: false, revision: 2 }),
    });
  });
});
