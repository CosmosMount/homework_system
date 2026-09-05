import { beforeEach, describe, expect, it, vi } from "vitest";

import CompetitionDetailPage from "@/app/competitions/[competitionId]/page";
import CompetitionTaskPage from "@/app/competitions/[competitionId]/tasks/[taskId]/page";
import CompetitionTeamPage from "@/app/competitions/[competitionId]/team/page";

const { redirectMock } = vi.hoisted(() => ({
  redirectMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

describe("legacy competition pages", () => {
  beforeEach(() => {
    redirectMock.mockReset();
  });

  it.each([
    ["detail", CompetitionDetailPage],
    ["team", CompetitionTeamPage],
    ["task", CompetitionTaskPage],
  ])("redirects the legacy %s route to the independent team center", (_name, page) => {
    page();
    expect(redirectMock).toHaveBeenCalledWith("/competitions");
  });
});
