import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ProviderHealthBadge from "../app/components/providers/ProviderHealthBadge";
import type { ProviderHealth } from "../lib/providers-api";

const healthFor = (status: string): ProviderHealth => ({
  status,
  latency_ms: 18,
  http_status: 200,
  error_code: null,
  error_message_redacted: null,
  metadata_json: {},
  checked_at: null,
});

describe("provider health badge", () => {
  it.each([
    ["healthy", "border-success/30", "bg-success/10", "text-success"],
    ["degraded", "border-warning/30", "bg-warning/10", "text-warning"],
    ["unhealthy", "border-danger/30", "bg-danger/10", "text-danger"],
  ])(
    "uses semantic theme colors for compact %s runtime-card status",
    (status, border, bg, text) => {
      render(<ProviderHealthBadge health={healthFor(status)} size="compact" />);

      const badge = screen.getByText(status);
      expect(badge).toHaveClass("rounded-lg", "px-2", "py-0.5", "text-[10px]", border, bg, text);
    },
  );

  it("preserves the default badge styling for other provider surfaces", () => {
    render(<ProviderHealthBadge health={healthFor("healthy")} />);

    const badge = screen.getByText("healthy");
    expect(badge).toHaveClass("rounded-full", "px-3", "py-1", "text-[11px]", "text-green-400");
    expect(badge).not.toHaveClass("rounded-lg");
    expect(badge).not.toHaveClass("text-success");
  });
});
