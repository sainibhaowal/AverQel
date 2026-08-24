import toast from "react-hot-toast";

export function isElectronEnvironment(): boolean {
  return typeof window !== "undefined" && window.electron?.isElectron === true;
}

export function isDesktopEnvironment(): boolean {
  return process.env.NEXT_PUBLIC_BUILD_TARGET === "desktop" || isElectronEnvironment();
}

export function resolveApiBaseUrl(params: {
  hostname: string;
  protocol: string;
  port: string;
  envUrl?: string;
}): string {
  const { hostname, protocol, port } = params;

  if (isDesktopEnvironment()) {
    return process.env.NEXT_PUBLIC_API_URL || "https://averqel.com/api/v1";
  }

  if (typeof window !== "undefined") {
    return "/api/v1";
  }

  // Production-style local access is always same-origin behind Nginx.
  if (!port || port === "443" || port === "80") {
    return `${protocol}//${hostname}/api/v1`;
  }

  // Detect subdomain port-mapping environments (e.g. 1030-foo -> 1000-foo).
  if (hostname.includes("1030")) {
    return `${protocol}//${hostname}/api/v1`;
  }

  return `/api/v1`;
}

export const getApiBaseUrl = () => {
  if (isDesktopEnvironment()) {
    if (typeof window !== "undefined") {
      const { hostname, origin } = window.location;
      // Electron development loads the web app from the local HTTPS origin.
      // Keep API calls on that same origin; packaged builds use the production API.
      if (hostname === "localhost" || hostname === "127.0.0.1" || hostname.endsWith(".localhost")) {
        // Never construct an API URL from a non-HTTP origin.
        return origin.startsWith("http") ? `${origin}/api/v1` : "https://localhost/api/v1";
      }
    }
    return process.env.NEXT_PUBLIC_API_URL || "https://averqel.com/api/v1";
  }
  return "/api/v1";
};

let refreshPromise: Promise<string | null> | null = null;
let authSessionInvalidated = false;
const ACCESS_TOKEN_REFRESH_BUFFER_MS = 60_000;
const DEFAULT_API_TIMEOUT_MS = 30_000;
const AUTH_API_TIMEOUT_MS = 15_000;
const STREAM_API_TIMEOUT_MS = 120_000;
const REFRESH_LOCK_KEY = "averqel_refresh_lock";
const REFRESH_LOCK_TTL_MS = 15_000;
const AUTH_CHANNEL_NAME = "averqel_auth";
const PUBLIC_AUTH_ENDPOINTS = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
  "/auth/logout",
]);
const TAB_ID =
  typeof window !== "undefined"
    ? `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    : "server";

function onTokenRefreshed(token: string | null) {
  if (token) {
    authSessionInvalidated = false;
  }
}

function getAuthChannel(): BroadcastChannel | null {
  if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") {
    return null;
  }
  return new BroadcastChannel(AUTH_CHANNEL_NAME);
}

function broadcastAuthEvent(
  payload: { type: "token_refreshed"; token: string } | { type: "logout" },
) {
  const channel = getAuthChannel();
  if (!channel) {
    return;
  }
  channel.postMessage(payload);
  channel.close();
}

function clearSessionStorage() {
  localStorage.removeItem("averqel_token");
  localStorage.removeItem("averqel_tenant_id");
  localStorage.removeItem("averqel_user");
}

export function clearStoredSession() {
  if (typeof window === "undefined") {
    return;
  }
  clearSessionStorage();
}

export function resetAuthSessionState() {
  authSessionInvalidated = false;
}

export class ApiRequestTimeoutError extends Error {
  readonly endpoint: string;

  constructor(endpoint: string, timeoutMs: number) {
    super(`Request timed out after ${Math.ceil(timeoutMs / 1000)} seconds: ${endpoint}`);
    this.name = "ApiRequestTimeoutError";
    this.endpoint = endpoint;
  }
}

function requestTimeoutFor(endpoint: string, override?: number): number {
  if (typeof override === "number" && Number.isFinite(override) && override > 0) {
    return override;
  }
  if (endpoint.includes("/stream")) {
    return STREAM_API_TIMEOUT_MS;
  }
  if (normalizeEndpointPath(endpoint).startsWith("/auth/")) {
    return AUTH_API_TIMEOUT_MS;
  }
  if (normalizeEndpointPath(endpoint) === "/health/ready") {
    return 2_500;
  }
  return DEFAULT_API_TIMEOUT_MS;
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit,
  timeoutMs: number,
  endpoint: string,
): Promise<Response> {
  const controller = new AbortController();
  const externalSignal = init.signal;
  const forwardAbort = () => controller.abort(externalSignal?.reason);
  if (externalSignal) {
    if (externalSignal.aborted) {
      forwardAbort();
    } else {
      externalSignal.addEventListener("abort", forwardAbort, { once: true });
    }
  }

  const timer = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted && !externalSignal?.aborted) {
      throw new ApiRequestTimeoutError(endpoint, timeoutMs);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timer);
    externalSignal?.removeEventListener("abort", forwardAbort);
  }
}

function normalizeEndpointPath(endpoint: string): string {
  return endpoint.split(/[?#]/)[0] ?? endpoint;
}

function isPublicAuthEndpoint(endpoint: string): boolean {
  return PUBLIC_AUTH_ENDPOINTS.has(normalizeEndpointPath(endpoint));
}

function createUnauthorizedResponse(): Response {
  return new Response(JSON.stringify({ detail: "Unauthorized" }), {
    status: 401,
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export function invalidateAuthSession({ broadcast = true, notify = true } = {}) {
  authSessionInvalidated = true;
  clearSessionStorage();
  onTokenRefreshed(null);

  if (typeof window !== "undefined" && notify) {
    window.dispatchEvent(new Event("averqel_unauthorized"));
  }

  if (broadcast) {
    broadcastAuthEvent({ type: "logout" });
  }
}

function decodeJwtExpiry(token: string | null): number | null {
  if (!token) {
    return null;
  }
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }
  try {
    const normalized = parts[1]!.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    const payload = JSON.parse(atob(padded)) as { exp?: number };
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

function decodeJwtTenantId(token: string | null): string | null {
  if (!token) {
    return null;
  }
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }
  try {
    const normalized = parts[1]!.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    const payload = JSON.parse(atob(padded)) as { tenant_id?: unknown };
    return typeof payload.tenant_id === "string" && payload.tenant_id.trim()
      ? payload.tenant_id
      : null;
  } catch {
    return null;
  }
}

export function getRequestTenantId(token: string | null): string | null {
  // The signed JWT claim is authoritative. The local-storage copy is only a
  // convenience and can survive a tenant switch or an older login session.
  return decodeJwtTenantId(token) || localStorage.getItem("averqel_tenant_id");
}

export function getAccessTokenExpiry(token: string | null): number | null {
  return decodeJwtExpiry(token);
}

export function shouldRefreshAccessToken(token: string | null): boolean {
  const expiryMs = decodeJwtExpiry(token);
  if (!expiryMs) {
    return false;
  }
  return expiryMs - Date.now() <= ACCESS_TOKEN_REFRESH_BUFFER_MS;
}

function getRefreshLock(): {
  owner: string;
  expiresAt: number;
} | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(REFRESH_LOCK_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as { owner?: string; expiresAt?: number };
    if (!parsed.owner || typeof parsed.expiresAt !== "number") {
      return null;
    }
    if (parsed.expiresAt <= Date.now()) {
      window.localStorage.removeItem(REFRESH_LOCK_KEY);
      return null;
    }
    return { owner: parsed.owner, expiresAt: parsed.expiresAt };
  } catch {
    window.localStorage.removeItem(REFRESH_LOCK_KEY);
    return null;
  }
}

function acquireRefreshLock(): boolean {
  if (typeof window === "undefined") {
    return true;
  }
  const existing = getRefreshLock();
  if (existing && existing.owner !== TAB_ID) {
    return false;
  }
  window.localStorage.setItem(
    REFRESH_LOCK_KEY,
    JSON.stringify({ owner: TAB_ID, expiresAt: Date.now() + REFRESH_LOCK_TTL_MS }),
  );
  return true;
}

function releaseRefreshLock() {
  if (typeof window === "undefined") {
    return;
  }
  const existing = getRefreshLock();
  if (existing?.owner === TAB_ID) {
    window.localStorage.removeItem(REFRESH_LOCK_KEY);
  }
}

async function waitForExternalRefresh(timeoutMs = 5000): Promise<string | null> {
  if (typeof window === "undefined") {
    return null;
  }
  const token = localStorage.getItem("averqel_token");
  if (token && !shouldRefreshAccessToken(token)) {
    return token;
  }

  return new Promise<string | null>((resolve) => {
    const channel = getAuthChannel();
    const timeout = window.setTimeout(() => {
      channel?.close();
      resolve(localStorage.getItem("averqel_token"));
    }, timeoutMs);

    const cleanup = (nextToken: string | null) => {
      window.clearTimeout(timeout);
      channel?.close();
      resolve(nextToken);
    };

    if (channel) {
      channel.onmessage = (event: MessageEvent<{ type: string; token?: string }>) => {
        if (event.data?.type === "token_refreshed" && event.data.token) {
          cleanup(event.data.token);
          return;
        }
        if (event.data?.type === "logout") {
          cleanup(null);
        }
      };
    }
  });
}

export async function refreshAccessToken(tenantId: string | null): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise;
  }

  if (!acquireRefreshLock()) {
    return waitForExternalRefresh();
  }

  refreshPromise = (async () => {
    try {
      const refreshResponse = await fetchWithTimeout(
        `${getApiBaseUrl()}/auth/refresh`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(tenantId ? { "X-Tenant-Id": tenantId } : {}),
          },
          credentials: "include",
        },
        AUTH_API_TIMEOUT_MS,
        "/auth/refresh",
      );

      if (!refreshResponse.ok) {
        invalidateAuthSession();
        return null;
      }

      const data = await refreshResponse.json();
      const newToken = data.access_token as string | undefined;
      if (!newToken) {
        invalidateAuthSession();
        return null;
      }

      localStorage.setItem("averqel_token", newToken);
      onTokenRefreshed(newToken);
      broadcastAuthEvent({ type: "token_refreshed", token: newToken });
      return newToken;
    } catch {
      invalidateAuthSession();
      return null;
    } finally {
      releaseRefreshLock();
    }
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

export async function fetchWithAuth(
  endpoint: string,
  options: RequestInit & {
    _isRetry?: boolean;
    _skipAuthRefresh?: boolean;
    timeoutMs?: number;
  } = {},
) {
  const endpointPath = normalizeEndpointPath(endpoint);
  const { _isRetry, _skipAuthRefresh, timeoutMs, ...requestInit } = options;
  let token = localStorage.getItem("averqel_token");
  let tenantId = getRequestTenantId(token);

  if (authSessionInvalidated && !PUBLIC_AUTH_ENDPOINTS.has(endpointPath)) {
    return createUnauthorizedResponse();
  }

  if (
    !_isRetry &&
    !_skipAuthRefresh &&
    !isPublicAuthEndpoint(endpointPath) &&
    shouldRefreshAccessToken(token)
  ) {
    const refreshedToken = await refreshAccessToken(tenantId);
    if (!refreshedToken) {
      return createUnauthorizedResponse();
    }
    token = refreshedToken;
    tenantId = getRequestTenantId(token);
  }

  const headers = new Headers(requestInit.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (tenantId) {
    headers.set("X-Tenant-Id", tenantId);
  }

  // Set Content-Type only if it's not FormData.
  // The browser automatically sets Content-Type to multipart/form-data with the correct boundary for FormData.
  if (!(requestInit.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  // Normalize slashes to prevent double slashes
  const baseUrl = getApiBaseUrl().replace(/\/+$/, "");
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const fullUrl = `${baseUrl}${cleanEndpoint}`;

  let response: Response;
  try {
    response = await fetchWithTimeout(
      fullUrl,
      {
        ...requestInit,
        headers,
        credentials: "include",
      },
      requestTimeoutFor(endpoint, timeoutMs),
      endpointPath,
    );
  } catch (error) {
    if (error instanceof ApiRequestTimeoutError) {
      toast.error("This request took too long. No data was changed; please retry.", {
        id: "api-timeout-busy",
        duration: 4_000,
      });
    }
    throw error;
  }

  if (
    response.status === 401 &&
    endpointPath !== "/auth/refresh" &&
    !_isRetry &&
    !_skipAuthRefresh
  ) {
    const refreshedToken = await refreshAccessToken(tenantId);
    if (refreshedToken) {
      return fetchWithAuth(endpoint, { ...requestInit, timeoutMs, _isRetry: true });
    }

    // If refresh fails, the session is already invalidated; redirect the current tab.
    if (typeof window !== "undefined" && window.location.pathname !== "/auth/login") {
      window.location.href = "/auth/login";
    }
    return response; // Return early for unhandled 401s that bypassed redirect
  }

  // Global Error Interceptor for 4xx and 5xx
  if (!response.ok && response.status !== 401) {
    try {
      const errorData = await response.clone().json();

      // Handle 429 Rate Limits
      if (response.status === 429) {
        const resetUnix = response.headers.get("X-RateLimit-Reset");
        if (resetUnix) {
          const resetMs = parseInt(resetUnix, 10) * 1000 - Date.now();
          if (resetMs > 0) {
            const seconds = Math.ceil(resetMs / 1000);
            toast.error(`Too many requests. Please wait ${seconds} seconds.`, {
              id: "rate-limit-toast", // use fixed ID to prevent spamming
              duration: resetMs > 4000 ? resetMs : 4000,
            });
            // Recursively update countdown if duration is long? We'll let toast handle static for now,
            // or we could use toast.promise/custom component for a live countdown. A static toast is robust.
            return response;
          }
        }
        toast.error("Too many requests. Please try again later.", { id: "rate-limit-toast" });
        return response;
      }

      // Handle standard structured errors
      const errorDataObj = errorData?.error || {};
      const errorMessage =
        errorDataObj.message || errorData?.detail || `HTTP Error ${response.status}`;

      if (errorDataObj.code === "USER_DISABLED") {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event("averqel_user_disabled"));
        }
        return response;
      }

      toast.error(errorMessage);
    } catch {
      // Fallback if not JSON
      toast.error(`Unexpected Error (${response.status})`);
    }
  }

  return response;
}

/** Upload multipart data with real browser upload progress while preserving the
 * same bearer/tenant session used by fetchWithAuth. */
export async function uploadWithAuthProgress(
  endpoint: string,
  body: FormData | Blob,
  options: {
    method?: string;
    onProgress?: (loaded: number, total: number) => void;
    signal?: AbortSignal;
    timeoutMs?: number;
  } = {},
): Promise<Response> {
  const token = localStorage.getItem("averqel_token");
  const tenantId = getRequestTenantId(token);
  const baseUrl = getApiBaseUrl().replace(/\/+$/, "");
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const fullUrl = `${baseUrl}${cleanEndpoint}`;

  const attempt = (accessToken: string | null): Promise<Response> =>
    new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      let timedOut = false;
      const timeout = options.timeoutMs ?? 120_000;
      xhr.open(options.method ?? "POST", fullUrl, true);
      xhr.withCredentials = true;
      xhr.timeout = timeout;
      if (accessToken) xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
      if (tenantId) xhr.setRequestHeader("X-Tenant-Id", tenantId);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) options.onProgress?.(event.loaded, event.total);
      };
      const abort = () => xhr.abort();
      options.signal?.addEventListener("abort", abort, { once: true });
      xhr.onload = () => {
        const headers = new Headers();
        xhr
          .getAllResponseHeaders()
          .trim()
          .split(/[\r\n]+/)
          .forEach((line) => {
            const separator = line.indexOf(":");
            if (separator > 0)
              headers.set(line.slice(0, separator).trim(), line.slice(separator + 1).trim());
          });
        resolve(
          new Response(xhr.responseText, {
            status: xhr.status,
            statusText: xhr.statusText,
            headers,
          }),
        );
      };
      xhr.onerror = () =>
        reject(new Error("The file upload failed because the network connection was lost."));
      xhr.onabort = () =>
        reject(
          options.signal?.aborted
            ? new DOMException("Upload cancelled", "AbortError")
            : new Error("The file upload was cancelled."),
        );
      xhr.ontimeout = () => {
        timedOut = true;
        reject(new ApiRequestTimeoutError(endpoint, timeout));
      };
      try {
        xhr.send(body);
      } catch (error) {
        if (!timedOut) reject(error);
      }
    });

  let response = await attempt(token);
  if (response.status === 401) {
    const refreshedToken = await refreshAccessToken(tenantId);
    if (refreshedToken) response = await attempt(refreshedToken);
  }
  return response;
}

// Standardized API wrapper for AverQel v1.2+
export const apiV1 = {
  async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = (await fetchWithAuth(endpoint, options)) as Response;
    const text = await response.text();
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }
    if (!response.ok) {
      const errorPayload = data as { error?: { message?: string }; detail?: string } | null;
      const errorMsg =
        errorPayload?.error?.message || errorPayload?.detail || `HTTP ${response.status}`;
      throw new Error(errorMsg);
    }
    return data as T;
  },
  get<T>(endpoint: string) {
    return this.request<T>(endpoint);
  },
  post<T>(endpoint: string, body?: Record<string, unknown>) {
    return this.request<T>(endpoint, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  },
  patch<T>(endpoint: string, body?: Record<string, unknown>) {
    return this.request<T>(endpoint, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    });
  },
  delete<T>(endpoint: string) {
    return this.request<T>(endpoint, { method: "DELETE" });
  },
};
