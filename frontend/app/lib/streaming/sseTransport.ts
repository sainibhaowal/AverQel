"use client";

const TRANSIENT_STREAM_ERROR_PATTERNS = [
  "err_network_changed",
  "network changed",
  "failed to fetch",
  "load failed",
  "networkerror",
  "network request failed",
  "the network connection was lost",
];

const RETRYABLE_STREAM_STATUS_CODES = new Set([408, 425, 429, 502, 503, 504]);

export function isRetryableStreamTransportError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const message = error.message.trim().toLowerCase();
  return TRANSIENT_STREAM_ERROR_PATTERNS.some((pattern) => message.includes(pattern));
}

export function isRetryableStreamStatus(status: number): boolean {
  return RETRYABLE_STREAM_STATUS_CODES.has(status);
}

export function normalizeStreamTransportMessage(
  error: unknown,
  fallback: string,
  retryable: boolean,
): string {
  if (error instanceof Error && error.message.trim()) {
    if (retryable && isRetryableStreamTransportError(error)) {
      return `${error.message}. The browser dropped the live stream before any data arrived. This usually happens when the local network route, VPN, proxy, or localhost DNS target changes during the request.`;
    }
    return error.message;
  }
  return fallback;
}
