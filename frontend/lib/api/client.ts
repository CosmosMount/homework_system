import type { ApiErrorPayload } from "@/lib/api/types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;
  readonly details: ApiErrorPayload["error"]["details"];
  readonly retryAfter: number | null;

  constructor(response: Response, payload: ApiErrorPayload) {
    super(payload.error.message);
    this.name = "ApiError";
    this.status = response.status;
    this.code = payload.error.code;
    this.requestId = payload.error.request_id;
    this.details = payload.error.details;
    const retryAfter = response.headers.get("retry-after");
    this.retryAfter = retryAfter === null ? null : Number(retryAfter);
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: ApiErrorPayload;
  try {
    payload = (await response.json()) as ApiErrorPayload;
  } catch {
    payload = {
      error: {
        code: "NETWORK_RESPONSE_ERROR",
        message: "服务返回了无法识别的响应。",
        request_id: "unknown",
      },
    };
  }
  return new ApiError(response, payload);
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch("/api/v1" + path, {
    ...init,
    credentials: "same-origin",
    headers,
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  const body = await response.text();
  if (body.trim().length === 0) {
    return undefined as T;
  }
  return JSON.parse(body) as T;
}

let csrfToken: string | null = null;

export function clearCsrfToken(): void {
  csrfToken = null;
}

export async function csrfFetch<T>(
  path: string,
  init: RequestInit,
): Promise<T> {
  if (csrfToken === null) {
    const response = await apiFetch<{ csrf_token: string }>("/auth/csrf");
    csrfToken = response.csrf_token;
  }
  const headers = new Headers(init.headers);
  headers.set("X-CSRF-Token", csrfToken);
  try {
    return await apiFetch<T>(path, { ...init, headers });
  } catch (error) {
    if (error instanceof ApiError && error.code === "CSRF_FAILED") {
      csrfToken = null;
    }
    throw error;
  }
}

export function fieldReason(
  error: unknown,
  field: string,
): string | undefined {
  if (!(error instanceof ApiError)) {
    return undefined;
  }
  return error.details?.find((detail) => detail.field === field)?.reason;
}
