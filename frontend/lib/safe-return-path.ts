export function safeReturnPath(value: string | null | undefined): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return null;
  }

  try {
    const base = new URL("https://return.local.invalid");
    const target = new URL(value, base);
    if (target.origin !== base.origin ||
      target.pathname === "/login" ||
      target.pathname.startsWith("/login/")) {
      return null;
    }
    return target.pathname + target.search + target.hash;
  } catch {
    return null;
  }
}
