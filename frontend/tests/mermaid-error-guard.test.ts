import { describe, expect, it } from "vitest";

import { isMermaidErrorSvg } from "../app/dashboard/query/_lib/mermaid";

describe("Mermaid error SVG guard", () => {
  it("rejects Mermaid's parser-error SVG output", () => {
    expect(
      isMermaidErrorSvg(
        '<svg><text>Syntax error in text</text><text>mermaid version 11.13.0</text></svg>',
      ),
    ).toBe(true);
  });

  it("accepts a normal rendered diagram", () => {
    expect(isMermaidErrorSvg('<svg><path d="M0 0L10 10" /></svg>')).toBe(false);
  });
});
