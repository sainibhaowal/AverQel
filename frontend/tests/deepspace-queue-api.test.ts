import { describe, expect, it, vi } from "vitest";

import {
  apiResponseError,
  fetchWithSingle503Retry,
  retryAfterDelayMs,
} from "../app/dashboard/deepspace/_lib/queue-api";

describe("DeepSpace queue request recovery", () => {
  it("uses the server Retry-After delay and caps it to three seconds", () => {
    expect(retryAfterDelayMs(new Response(null, { headers: { "Retry-After": "2" } }))).toBe(2_000);
    expect(retryAfterDelayMs(new Response(null, { headers: { "Retry-After": "10" } }))).toBe(3_000);
  });

  it("retries a temporary 503 with the same request ID and body", async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { message: "Temporary database issue." } }), {
          status: 503,
          headers: { "Retry-After": "0" },
        }),
      )
      .mockResolvedValueOnce(new Response("{}", { status: 202 }));
    const body = JSON.stringify({ message: "hello", client_request_id: "stable-request-id" });

    const response = await fetchWithSingle503Retry(
      "/deepspace/chats/conversation-1/queue",
      { method: "POST", body },
      request,
    );

    expect(response.status).toBe(202);
    expect(request).toHaveBeenCalledTimes(2);
    expect(request.mock.calls[0]).toEqual([
      "/deepspace/chats/conversation-1/queue",
      { method: "POST", body },
    ]);
    expect(request.mock.calls[1]).toEqual(request.mock.calls[0]);
  });

  it("reports the API's reason when the retry also fails", async () => {
    const response = new Response(
      JSON.stringify({
        error: { message: "A temporary database issue interrupted this request." },
      }),
      { status: 503 },
    );

    await expect(apiResponseError(response, "Unable to queue this message.")).resolves.toBe(
      "A temporary database issue interrupted this request.",
    );
  });
});
