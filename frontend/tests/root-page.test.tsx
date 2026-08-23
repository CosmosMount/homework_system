import { beforeEach, describe, expect, it, vi } from "vitest";

import Home from "@/app/page";

const { redirectMock } = vi.hoisted(() => ({
  redirectMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

describe("root page", () => {
  beforeEach(() => {
    redirectMock.mockClear();
  });

  it("redirects to the public login entry", () => {
    Home();

    expect(redirectMock).toHaveBeenCalledWith("/login");
  });
});
