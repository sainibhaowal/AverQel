import { normalizeMarkdown as normalizeQueryMarkdown } from "../app/dashboard/query/_lib/markdown";
import { normalizeMarkdown as normalizeDeepSpaceMarkdown } from "../app/dashboard/deepspace/_lib/markdown";

const compactTable =
  "| Non-Ideality | Impact | Mitigation | | :--- | :--- | :--- | | Clock Jitter | Noise floor | PLL | | Capacitor Mismatch | kT/C noise | Larger caps |";
const malformedFourColumnTable =
  "| Non-Ideality | Wave Theory / Circuit Origin | Impact on Audio | Mitigation Strategy | | :--- | :--- | :--- | | **Clock Jitter (t_j)** | Aperture uncertainty | Noise floor modulation | PLL with < 100fs RMS jitter | | **Capacitor Mismatch** | Thermal noise kT/C | Gain error | Large unit caps |";

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
});
