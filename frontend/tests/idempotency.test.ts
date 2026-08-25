import { afterEach, describe, expect, it, vi } from "vitest";

import { createIdempotencyKey } from "@/lib/idempotency";

describe("createIdempotencyKey", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("prefers the native randomUUID implementation", () => {
    const randomUUID = vi.fn(() => "00000000-0000-4000-8000-000000000001");
    const getRandomValues = vi.fn();
    vi.stubGlobal("crypto", { getRandomValues, randomUUID });

    expect(createIdempotencyKey()).toBe(
      "00000000-0000-4000-8000-000000000001",
    );
    expect(randomUUID).toHaveBeenCalledOnce();
    expect(getRandomValues).not.toHaveBeenCalled();
  });

  it("builds a UUID v4 with getRandomValues when randomUUID is unavailable", () => {
    const getRandomValues = vi.fn((bytes: Uint8Array) => {
      bytes.set(Array.from({ length: 16 }, (_, index) => index));
      return bytes;
    });
    vi.stubGlobal("crypto", {
      getRandomValues,
      randomUUID: undefined,
    });

    const key = createIdempotencyKey();

    expect(key).toBe("00010203-0405-4607-8809-0a0b0c0d0e0f");
    expect(key).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(getRandomValues).toHaveBeenCalledOnce();
  });

  it("does not fall back to an insecure random source", () => {
    vi.stubGlobal("crypto", {
      getRandomValues: undefined,
      randomUUID: undefined,
    });

    expect(() => createIdempotencyKey()).toThrow(
      "Secure random generation is unavailable.",
    );
  });
});
