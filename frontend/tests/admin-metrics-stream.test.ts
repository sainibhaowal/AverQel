import { describe, expect, it } from "vitest";
import { readServerSentEvents } from "../app/dashboard/admin/metrics/metricsStream";

describe("admin metrics SSE parser", () => {
  it("parses events split across chunks and ignores heartbeat comments", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode(': keep-alive\r\n\r\nevent: metrics\r\ndata: {"api_requests_total":'),
        );
        controller.enqueue(
          encoder.encode('12}\r\n\r\nevent: metrics_status\ndata: {"status":"unavailable"}\n\n'),
        );
        controller.close();
      },
    });

    const messages = [];
    for await (const message of readServerSentEvents(body)) {
      messages.push(message);
    }

    expect(messages).toEqual([
      { event: "metrics", data: '{"api_requests_total":12}' },
      { event: "metrics_status", data: '{"status":"unavailable"}' },
    ]);
  });
});
