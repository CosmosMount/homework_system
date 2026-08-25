import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  apiFetch,
  clearCsrfToken,
  csrfFetch,
  fieldReason,
} from "@/lib/api/client";

const fetchMock = vi.fn<typeof fetch>();

describe("browser API client", () => {
  beforeEach(() => {
    clearCsrfToken();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("parses unified errors, field details, and Retry-After", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "RATE_LIMITED",
            message: "请求过于频繁。",
            request_id: "request-1",
            details: [{ field: "email", reason: "INVALID_CAMPUS_EMAIL" }],
          },
        }),
        {
          status: 429,
          headers: {
            "Content-Type": "application/json",
            "Retry-After": "900",
          },
        },
      ),
    );

    let caught: unknown;
    try {
      await apiFetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: "invalid" }),
      });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(ApiError);
    expect(caught).toMatchObject({
      code: "RATE_LIMITED",
      requestId: "request-1",
      retryAfter: 900,
      status: 429,
    });
    expect(fieldReason(caught, "email")).toBe("INVALID_CAMPUS_EMAIL");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/login",
      expect.objectContaining({
        credentials: "same-origin",
        method: "POST",
      }),
    );
  });

  it("accepts a successful 202 response with an empty body", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 202 }));

    await expect(
      apiFetch<void>("/auth/email-verifications/resend", {
        method: "POST",
        body: JSON.stringify({
          email: "mail-parse-test@connect.hkust-gz.edu.cn",
        }),
      }),
    ).resolves.toBeUndefined();
  });

  it("fetches a CSRF token and adds it to a state-changing request", async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "csrf-token" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await csrfFetch<void>("/auth/logout", { method: "POST" });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/auth/csrf");
    const requestInit = fetchMock.mock.calls[1]?.[1];
    expect(new Headers(requestInit?.headers).get("X-CSRF-Token")).toBe(
      "csrf-token",
    );
  });
});
