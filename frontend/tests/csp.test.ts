import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

import { buildContentSecurityPolicy } from "@/lib/security/csp";

describe("content security policy", () => {
  it("uses a per-request nonce and forbids executable object/frame content", () => {
    const policy = buildContentSecurityPolicy("nonce123", false);

    expect(policy).toContain("script-src 'self' 'nonce-nonce123' 'strict-dynamic'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).not.toContain("script-src 'self' 'unsafe-inline'");
    expect(policy).not.toContain("upgrade-insecure-requests");
  });

  it("upgrades insecure subresources in production", () => {
    expect(buildContentSecurityPolicy("secure456", true)).toContain(
      "upgrade-insecure-requests",
    );
  });

  it("forces dynamic rendering so framework scripts receive the request nonce", () => {
    const layout = readFileSync("app/layout.tsx", "utf-8");
    expect(layout).toContain('export const dynamic = "force-dynamic"');
  });
});
