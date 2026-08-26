import { beforeEach, describe, expect, it, vi } from "vitest";

import Home from "@/app/page";

const { getOptionalUserMock, redirectMock } = vi.hoisted(() => ({
  getOptionalUserMock: vi.fn(),
  redirectMock: vi.fn(() => {
    throw new Error("NEXT_REDIRECT");
  }),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  redirect: redirectMock,
}));

vi.mock("@/lib/api/server", () => ({
  getOptionalUser: getOptionalUserMock,
}));

describe("root page", () => {
  beforeEach(() => {
    redirectMock.mockClear();
    getOptionalUserMock.mockReset();
  });

  it("redirects an anonymous visitor to the public login entry", async () => {
    getOptionalUserMock.mockResolvedValue(null);

    await expect(Home()).rejects.toThrow("NEXT_REDIRECT");

    expect(redirectMock).toHaveBeenCalledWith("/login");
  });

  it("redirects an administrator to user management", async () => {
    getOptionalUserMock.mockResolvedValue({ role: "admin" });

    await expect(Home()).rejects.toThrow("NEXT_REDIRECT");

    expect(redirectMock).toHaveBeenCalledWith("/admin/dashboard");
  });
});
