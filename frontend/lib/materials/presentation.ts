export const MATERIAL_TECH_GROUPS = ["机械", "硬件", "电控", "算法", "宣运", "通用"] as const;

export function materialPrice(price: string): string {
  return `¥${Number(price).toFixed(2)}`;
}

export function materialScanUrl(qrToken: string, origin: string): string {
  // Scheme, host and UUID are case-insensitive; uppercase enables QR alphanumeric encoding.
  return `${origin.toUpperCase()}/materials/scan/${qrToken.toUpperCase()}`;
}
