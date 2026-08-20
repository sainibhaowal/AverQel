import { normalizeMarkdown as normalizeQueryMarkdown } from "../app/dashboard/query/_lib/markdown";
import {
  normalizeMarkdown as normalizeDeepSpaceMarkdown,
  normalizeThinkingDisplay,
} from "../app/dashboard/deepspace/_lib/markdown";

const compactTable =
  "| Non-Ideality | Impact | Mitigation | | :--- | :--- | :--- | | Clock Jitter | Noise floor | PLL | | Capacitor Mismatch | kT/C noise | Larger caps |";
const malformedFourColumnTable =
  "| Non-Ideality | Wave Theory / Circuit Origin | Impact on Audio | Mitigation Strategy | | :--- | :--- | :--- | | **Clock Jitter (t_j)** | Aperture uncertainty | Noise floor modulation | PLL with < 100fs RMS jitter | | **Capacitor Mismatch** | Thermal noise kT/C | Gain error | Large unit caps |";
const compactSectionTable =
  "| Section | What's Inside |\n|---|---------------| | 1 | **PET Scans** | How antimatter is used in hospitals | | 2 | **Theranostics** | Therapy + diagnostics |";

describe("provider Markdown normalization", () => {
  it.each([
    ["Query", normalizeQueryMarkdown],
    ["DeepSpace", normalizeDeepSpaceMarkdown],
  ])("recovers concatenated rows for %s", (_surface, normalize) => {
    const result = normalize(compactTable);

    expect(result).toContain("| Non-Ideality | Impact | Mitigation |");
    expect(result).toContain("| Clock Jitter | Noise floor | PLL |");
    expect(result).toContain("| Capacitor Mismatch | kT/C noise | Larger caps |");
    expect(result).not.toContain("| | :---");
  });

  it("pads a malformed separator row to the header column count", () => {
    const result = normalizeQueryMarkdown(malformedFourColumnTable);

    expect(result).toContain(
      "| Non-Ideality | Wave Theory / Circuit Origin | Impact on Audio | Mitigation Strategy |",
    );
    expect(result).toContain(
      "| **Clock Jitter (t_j)** | Aperture uncertainty | Noise floor modulation | PLL with < 100fs RMS jitter |",
    );
    expect(result).toContain(
      "| **Capacitor Mismatch** | Thermal noise kT/C | Gain error | Large unit caps |",
    );
  });

  it("recovers a separator and rows joined on one physical line", () => {
    const result = normalizeDeepSpaceMarkdown(compactSectionTable);

    expect(result).toContain("| Section | What's Inside |");
    expect(result).toContain("| 1 | **PET Scans** | How antimatter is used in hospitals |");
    expect(result).toContain("| 2 | **Theranostics** | Therapy + diagnostics |");
  });

  it("removes only the provider's thinking-process wrapper", () => {
    expect(normalizeThinkingDisplay("'s a thinking process:\n\n1. Check the request.")).toBe(
      "1. Check the request.",
    );
    expect(normalizeThinkingDisplay("Here's a thinking process: Check the request.")).toBe(
      "Check the request.",
    );
  });

  it("splits compact numbered citation sources into readable bullets", () => {
    const result = normalizeDeepSpaceMarkdown(
      "[1] [First source](https://example.com/1) [2] [Second source](https://example.com/2)",
    );

    expect(result).toContain("- [1] [First source](https://example.com/1)");
    expect(result).toContain("- [2] [Second source](https://example.com/2)");
  });
});
