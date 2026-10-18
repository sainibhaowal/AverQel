import { fetchWithAuth } from "@/lib/api";

export type DeepSpaceRequest = (path: string, init: RequestInit) => Promise<Response>;

export function retryAfterDelayMs(response: Pick<Response, "headers">, fallbackMs = 1_000): number {
  const retryAfter = response.headers.get("Retry-After");
  const retryAfterSeconds = retryAfter ? Number(retryAfter) : Number.NaN;
  const retryAfterDate = retryAfter ? Date.parse(retryAfter) : Number.NaN;
  const waitMs = Number.isFinite(retryAfterSeconds)
    ? retryAfterSeconds * 1_000
    : Number.isFinite(retryAfterDate)
      ? retryAfterDate - Date.now()
      : fallbackMs;
  return Math.max(0, Math.min(waitMs, 3_000));
}

export async function fetchWithSingle503Retry(
  path: string,
  init: RequestInit,
  request: DeepSpaceRequest = fetchWithAuth,
): Promise<Response> {
  const response = await request(path, init);
  if (response.status !== 503) return response;

  await new Promise((resolve) => window.setTimeout(resolve, retryAfterDelayMs(response)));
  return request(path, init);
}

export async function apiResponseError(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as {
      error?: { message?: unknown };
      detail?: unknown;
    };
    const message =
      (typeof payload.error?.message === "string" && payload.error.message.trim()) ||
      (typeof payload.detail === "string" && payload.detail.trim());
    if (message) return message;
  } catch {
    // Keep the status-based fallback when a gateway returns a non-JSON body.
  }
  return `${fallback} (HTTP ${response.status}).`;
}
