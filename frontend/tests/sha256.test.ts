import { createHash } from "node:crypto";

import { describe, expect, it } from "vitest";

import {
  digestBase64,
  digestHex,
  IncrementalSha256,
} from "@/lib/sha256";

function hashInChunks(bytes: Uint8Array, chunkSizes: number[]): Uint8Array {
  const hash = new IncrementalSha256();
  let offset = 0;
  for (const size of chunkSizes) {
    hash.update(bytes.subarray(offset, offset + size));
    offset += size;
  }
  if (offset < bytes.length) {
    hash.update(bytes.subarray(offset));
  }
  return hash.digest();
}

describe("incremental SHA-256", () => {
  it("matches the standard empty and abc vectors", () => {
    expect(digestHex(new IncrementalSha256().digest())).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
    const hash = new IncrementalSha256();
    hash.update(new TextEncoder().encode("abc"));
    expect(digestHex(hash.digest())).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });

  it("is stable across arbitrary stream chunk boundaries", () => {
    const bytes = Uint8Array.from(
      { length: 4097 },
      (_, index) => (index * 37 + 11) % 256,
    );
    const digest = hashInChunks(bytes, [1, 63, 64, 65, 511, 1024]);
    expect(digestHex(digest)).toBe(
      createHash("sha256").update(bytes).digest("hex"),
    );
    expect(digestBase64(digest)).toBe(
      createHash("sha256").update(bytes).digest("base64"),
    );
  });
});
