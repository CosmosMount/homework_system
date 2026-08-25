const SHA256_CONSTANTS = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
  0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
  0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
  0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
  0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
  0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function rotateRight(value: number, shift: number): number {
  return (value >>> shift) | (value << (32 - shift));
}

export class IncrementalSha256 {
  private readonly state = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  private readonly pending = new Uint8Array(64);
  private pendingLength = 0;
  private bytesHashed = 0;
  private finished = false;

  update(input: Uint8Array): void {
    if (this.finished) {
      throw new Error("SHA-256 已经完成，不能继续写入。");
    }
    this.bytesHashed += input.length;
    let offset = 0;

    if (this.pendingLength > 0) {
      const needed = 64 - this.pendingLength;
      const consumed = Math.min(needed, input.length);
      this.pending.set(input.subarray(0, consumed), this.pendingLength);
      this.pendingLength += consumed;
      offset += consumed;
      if (this.pendingLength === 64) {
        this.process(this.pending);
        this.pendingLength = 0;
      }
    }

    while (offset + 64 <= input.length) {
      this.process(input.subarray(offset, offset + 64));
      offset += 64;
    }

    if (offset < input.length) {
      this.pending.set(input.subarray(offset), 0);
      this.pendingLength = input.length - offset;
    }
  }

  digest(): Uint8Array {
    if (this.finished) {
      throw new Error("SHA-256 digest 只能读取一次。");
    }
    this.finished = true;
    const finalBlocks = new Uint8Array(this.pendingLength < 56 ? 64 : 128);
    finalBlocks.set(this.pending.subarray(0, this.pendingLength));
    finalBlocks[this.pendingLength] = 0x80;

    const bitLength = this.bytesHashed * 8;
    const high = Math.floor(bitLength / 0x100000000);
    const low = bitLength >>> 0;
    const view = new DataView(finalBlocks.buffer);
    view.setUint32(finalBlocks.length - 8, high, false);
    view.setUint32(finalBlocks.length - 4, low, false);
    for (let offset = 0; offset < finalBlocks.length; offset += 64) {
      this.process(finalBlocks.subarray(offset, offset + 64));
    }

    const result = new Uint8Array(32);
    const resultView = new DataView(result.buffer);
    this.state.forEach((value, index) => {
      resultView.setUint32(index * 4, value, false);
    });
    return result;
  }

  private process(chunk: Uint8Array): void {
    const schedule = new Uint32Array(64);
    const view = new DataView(chunk.buffer, chunk.byteOffset, 64);
    for (let index = 0; index < 16; index += 1) {
      schedule[index] = view.getUint32(index * 4, false);
    }
    for (let index = 16; index < 64; index += 1) {
      const before15 = schedule[index - 15] ?? 0;
      const before2 = schedule[index - 2] ?? 0;
      const sigma0 =
        rotateRight(before15, 7) ^ rotateRight(before15, 18) ^ (before15 >>> 3);
      const sigma1 =
        rotateRight(before2, 17) ^ rotateRight(before2, 19) ^ (before2 >>> 10);
      schedule[index] = (
        (schedule[index - 16] ?? 0) +
        sigma0 +
        (schedule[index - 7] ?? 0) +
        sigma1
      ) >>> 0;
    }

    let a = this.state[0] ?? 0;
    let b = this.state[1] ?? 0;
    let c = this.state[2] ?? 0;
    let d = this.state[3] ?? 0;
    let e = this.state[4] ?? 0;
    let f = this.state[5] ?? 0;
    let g = this.state[6] ?? 0;
    let h = this.state[7] ?? 0;

    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temporary1 = (
        h +
        sum1 +
        choice +
        (SHA256_CONSTANTS[index] ?? 0) +
        (schedule[index] ?? 0)
      ) >>> 0;
      const sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temporary2 = (sum0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temporary1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temporary1 + temporary2) >>> 0;
    }

    this.state[0] = ((this.state[0] ?? 0) + a) >>> 0;
    this.state[1] = ((this.state[1] ?? 0) + b) >>> 0;
    this.state[2] = ((this.state[2] ?? 0) + c) >>> 0;
    this.state[3] = ((this.state[3] ?? 0) + d) >>> 0;
    this.state[4] = ((this.state[4] ?? 0) + e) >>> 0;
    this.state[5] = ((this.state[5] ?? 0) + f) >>> 0;
    this.state[6] = ((this.state[6] ?? 0) + g) >>> 0;
    this.state[7] = ((this.state[7] ?? 0) + h) >>> 0;
  }
}

export function digestHex(digest: Uint8Array): string {
  return Array.from(digest, (value) => value.toString(16).padStart(2, "0")).join("");
}

export function digestBase64(digest: Uint8Array): string {
  let binary = "";
  digest.forEach((value) => {
    binary += String.fromCharCode(value);
  });
  return btoa(binary);
}

export async function hashBlob(
  blob: Blob,
  onProgress?: (processedBytes: number) => void,
): Promise<Uint8Array> {
  const hash = new IncrementalSha256();
  const reader = blob.stream().getReader();
  let processed = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    hash.update(value);
    processed += value.length;
    onProgress?.(processed);
  }
  return hash.digest();
}
