import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const nextHeaders = vi.hoisted(() => ({
  cookies: vi.fn(),
  headers: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => nextHeaders);
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));

import {
  getAdminAssignmentSubmissions,
  getOptionalUser,
} from "@/lib/api/server";

const userResponse = {
  id: "01900000-0000-7000-8000-000000000001",
  role: "student",
};

describe("服务端 API 来源 IP 转发", () => {
  beforeEach(() => {
    nextHeaders.cookies.mockResolvedValue({
      toString: () => "pnx_session=test-session",
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("同时向内部 Backend 转发 Cookie 和 Nginx 已清洗的来源 IP", async () => {
    nextHeaders.headers.mockResolvedValue(
      new Headers({ "x-forwarded-for": "198.51.100.42" }),
    );
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(userResponse), {
        headers: { "content-type": "application/json" },
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const user = await getOptionalUser();

    expect(user?.id).toBe(userResponse.id);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const forwardedHeaders = new Headers(init.headers);
    expect(url).toBe("http://backend:8000/api/v1/auth/me");
    expect(forwardedHeaders.get("cookie")).toBe("pnx_session=test-session");
    expect(forwardedHeaders.get("x-forwarded-for")).toBe("198.51.100.42");
  });

  it("入站请求没有来源 IP 时不自行伪造转发头", async () => {
    nextHeaders.headers.mockResolvedValue(new Headers());
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(userResponse), {
        headers: { "content-type": "application/json" },
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getOptionalUser();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const forwardedHeaders = new Headers(init.headers);
    expect(forwardedHeaders.get("cookie")).toBe("pnx_session=test-session");
    expect(forwardedHeaders.has("x-forwarded-for")).toBe(false);
  });

  it("读取管理员作业提交名单的全部分页", async () => {
    nextHeaders.headers.mockResolvedValue(new Headers());
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = new URL(String(input));
      const page = Number(url.searchParams.get("page"));
      return Promise.resolve(
        new Response(
          JSON.stringify({
            items: [{ user_id: `student-${page}` }],
            page,
            page_size: 100,
            total: 205,
          }),
          {
            headers: { "content-type": "application/json" },
            status: 200,
          },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getAdminAssignmentSubmissions("assignment-1");

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(result.items.map((item) => item.user_id)).toEqual([
      "student-1",
      "student-2",
      "student-3",
    ]);
    expect(
      fetchMock.mock.calls.map(([input]) => new URL(String(input)).searchParams.get("page")),
    ).toEqual(["1", "2", "3"]);
  });
});
