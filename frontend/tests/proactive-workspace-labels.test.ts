import { describe, expect, it, vi } from "vitest";

import {
  getDraftQueueDescription,
  getDraftQueueLabel,
} from "../app/dashboard/proactive/_components/ProactiveWorkspaceClient";

describe("proactive workspace draft queue labels", () => {
  it("uses a morning label in the early cycle", () => {
    const date = new Date();
    vi.spyOn(date, "getHours").mockReturnValue(8);

    expect(getDraftQueueLabel(date)).toBe("Morning drafts");
    expect(getDraftQueueDescription(date)).toContain("early cycle");
  });

  it("uses a midday label during working hours", () => {
    const date = new Date();
    vi.spyOn(date, "getHours").mockReturnValue(13);

    expect(getDraftQueueLabel(date)).toBe("Midday drafts");
    expect(getDraftQueueDescription(date)).toContain("midday work");
  });

  it("uses an evening label for wrap-up time", () => {
    const date = new Date();
    vi.spyOn(date, "getHours").mockReturnValue(18);

    expect(getDraftQueueLabel(date)).toBe("Evening drafts");
    expect(getDraftQueueDescription(date)).toContain("Wrap-up");
  });

  it("uses an overnight label for late-cycle work", () => {
    const date = new Date();
    vi.spyOn(date, "getHours").mockReturnValue(2);

    expect(getDraftQueueLabel(date)).toBe("Overnight drafts");
    expect(getDraftQueueDescription(date)).toContain("Late-cycle");
  });
});
