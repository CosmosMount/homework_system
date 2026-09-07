import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TeamProfileDirectory } from "@/components/competitions/team-profile-directory";
import { csrfFetch } from "@/lib/api/client";
import type {
  TeamInvitation,
  TeamProfile,
  TeamProfilePage,
} from "@/lib/api/types";

const push = vi.fn();
const refresh = vi.fn();
const csrfFetchMock = vi.mocked(csrfFetch);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  csrfFetch: vi.fn(),
}));

const targetProfile: TeamProfile = {
  user_id: "student-2",
  full_name: "候选同学",
  direction_name: "视觉组",
  introduction: "熟悉 OpenCV，希望寻找嵌入式方向队友。",
  updated_at: "2026-09-07T01:00:00Z",
  revision: 1,
  can_invite: true,
  invitation_pending: false,
};

const profilePage: TeamProfilePage = {
  items: [targetProfile],
  total: 1,
  page: 1,
  page_size: 20,
};

const invitation: TeamInvitation = {
  id: "invite-1",
  team_id: "team-1",
  team_name: "第一队",
  invited_by_full_name: "发起同学",
  status: "pending",
  created_at: "2026-09-07T02:00:00Z",
  responded_at: null,
  revision: 1,
};

function renderDirectory(
  overrides: Partial<React.ComponentProps<typeof TeamProfileDirectory>> = {},
) {
  render(
    <TeamProfileDirectory
      currentUserId="student-1"
      hasTeam
      initialInvitations={[]}
      initialProfile={null}
      initialProfiles={profilePage}
      query=""
      teamCanInvite
      {...overrides}
    />,
  );
}

describe("team profile invitations", () => {
  beforeEach(() => {
    csrfFetchMock.mockReset();
    push.mockReset();
    refresh.mockReset();
  });

  it("publishes a voluntary profile without rendering HTML", async () => {
    const saved: TeamProfile = {
      user_id: "student-1",
      full_name: "当前同学",
      direction_name: null,
      introduction: "我喜欢控制。",
      updated_at: "2026-09-07T03:00:00Z",
      revision: 1,
      can_invite: false,
      invitation_pending: false,
    };
    csrfFetchMock.mockResolvedValue(saved);
    renderDirectory();

    fireEvent.change(screen.getByLabelText("个人简介"), {
      target: { value: "  我喜欢控制。  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "发布简介" }));

    await waitFor(() =>
      expect(csrfFetchMock).toHaveBeenCalledWith("/team-profiles/me", {
        method: "PUT",
        body: JSON.stringify({ introduction: "我喜欢控制。", revision: null }),
      }),
    );
    expect(await screen.findByText("个人简介已发布。")).toBeInTheDocument();
  });

  it("lets a regular team member invite from a submitted profile", async () => {
    csrfFetchMock.mockResolvedValue(invitation);
    renderDirectory();

    expect(screen.getByText(targetProfile.introduction)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "邀请组队" }));

    await waitFor(() =>
      expect(csrfFetchMock).toHaveBeenCalledWith("/team-invitations", {
        method: "POST",
        body: JSON.stringify({ invitee_user_id: "student-2" }),
      }),
    );
    expect(await screen.findByText("已邀请")).toBeInTheDocument();
    expect(
      screen.getByText("组队邀请已发送，对方确认后才会加入队伍。"),
    ).toBeInTheDocument();
  });

  it("accepts an invitation and opens the resulting team", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    csrfFetchMock.mockResolvedValue({ id: "team-1" });
    renderDirectory({
      hasTeam: false,
      initialInvitations: [invitation],
      teamCanInvite: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "接受" }));

    await waitFor(() =>
      expect(csrfFetchMock).toHaveBeenCalledWith(
        "/team-invitations/invite-1/accept",
        { method: "POST" },
      ),
    );
    expect(push).toHaveBeenCalledWith("/competitions");
  });

  it("declines an invitation without joining", async () => {
    csrfFetchMock.mockResolvedValue({ status: "ok" });
    renderDirectory({
      hasTeam: false,
      initialInvitations: [invitation],
      teamCanInvite: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "拒绝" }));

    expect(await screen.findByText("已拒绝邀请。")).toBeInTheDocument();
    expect(screen.queryByText("第一队")).not.toBeInTheDocument();
  });
});
