import { describe, expect, it } from "vitest";

import { parseSseFrames } from "../app/dashboard/deepspace/_lib/deepspace-stream";

describe("durable stream reconnect", () => {
  it("reads SSE ids as durable cursors and preserves an incomplete frame", () => {
    const parsed = parseSseFrames('id: 17\nevent: agent_status\ndata: {"status":"running"}\n\npartial');
    expect(parsed.events[0]).toMatchObject({ event: "agent_status", sequence: 17, data: { sequence: 17, status: "running" } });
    expect(parsed.remainder).toBe("partial");
  });
});
