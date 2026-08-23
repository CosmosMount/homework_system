import { describe, expect, it } from "vitest";

import { GET } from "@/app/health/route";

describe("frontend health route", () => {
  it("returns a non-cached live response", async () => {
    const response = GET();

    await expect(response.json()).resolves.toEqual({
      status: "ok",
      service: "frontend",
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
  });
});
