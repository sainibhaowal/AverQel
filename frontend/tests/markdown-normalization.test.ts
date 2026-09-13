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

  it.each([
    ["Query", normalizeQueryMarkdown],
    ["DeepSpace", normalizeDeepSpaceMarkdown],
  ])("normalizes a very wide pipe row iteratively for %s", (_surface, normalize) => {
    const wideRow = `|${Array.from({ length: 6000 }, (_, index) => ` cell-${index} `).join("|")}|`;

    expect(() => normalize(wideRow)).not.toThrow();
    expect(normalize(wideRow)).toContain("cell-5999");
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

  it.each([
    ["Query", normalizeQueryMarkdown],
    ["DeepSpace", normalizeDeepSpaceMarkdown],
  ])("removes unmatched strong markers from provider text for %s", (_surface, normalize) => {
    const result = normalize(
      "**Overall demand is strong\n1. **KI-Manager / Head of AI\nThousands of openings, **= 80+\n`**literal code**`\n**Already valid** text",
    );

    expect(result).toContain("Overall demand is strong");
    expect(result).toContain("1. KI-Manager / Head of AI");
    expect(result).toContain("openings, = 80+");
    expect(result).toContain("`**literal code**`");
    expect(result).toContain("**Already valid** text");
    expect(result).not.toContain("**Overall");
    expect(result).not.toContain("**KI-Manager");
  });

  it("repairs markers after compact table rows are split", () => {
    const result = normalizeDeepSpaceMarkdown(
      "| Metric | What the data shows || --- | --- || **Machine-Learning Engineer postings | **≈ 4,0+ active listings | | **AI-Engineer postings | **≈ 2,0+ active listings |",
    );

    expect(result).not.toContain("**Machine-Learning");
    expect(result).not.toContain("**AI-Engineer");
    expect(result).not.toContain("**≈");
  });

  it("splits pipe-delimited sections packed into an ordered list item", () => {
    const result = normalizeDeepSpaceMarkdown(
      "1. First role\n2. Second role\n3. Third role\n4. KI-Manager / Head of AI | | Salary movement (2024 → 2025) | • Entry-level ML Engineer: €5k–€68k gross/yr | Experienced Lead: €80k–€110k | | Geographic hotspots | • Jena | • Backnang | | What's driving the market | 1. Digital-transformation budgets",
    );

    expect(result).not.toContain("| |");
    expect(result).not.toContain(" | ");
    expect(result).toContain("4. KI-Manager / Head of AI");
    expect(result).toContain("Salary movement (2024 → 2025)");
    expect(result).toContain("- Entry-level ML Engineer");
    expect(result).toContain("Geographic hotspots");
    expect(result).toContain("What's driving the market");
  });

  it("recovers escaped-index compact tables", () => {
    const result = normalizeDeepSpaceMarkdown(
      "# | Job title | Skills | Experience | Salary | Link |\n\\|---|---|---|---|---|---| | 1 | ML Engineer | Python | 1-3 yr | €60k | https://example.com | | 2 | AI Engineer | PyTorch | 2-5 yr | €70k | https://example.com/ai |",
    );

    expect(result).toContain("| # | Job title | Skills | Experience | Salary | Link |");
    expect(result).toContain("| 1 | ML Engineer | Python | 1-3 yr | €60k | https://example.com |");
    expect(result).toContain(
      "| 2 | AI Engineer | PyTorch | 2-5 yr | €70k | https://example.com/ai |",
    );
    expect(result).not.toContain("\\|---");
  });

  it("keeps ordered numbering across provider bullet continuations", () => {
    const result = normalizeDeepSpaceMarkdown(
      "1. First role\n• Detail one\n2. Second role\n• Detail two",
    );

    expect(result).toContain("1. First role");
    expect(result).toContain("2. Second role");
    expect(result).toContain("   - Detail one");
    expect(result).toContain("   - Detail two");
    expect(result).not.toContain("1. Second role");
  });
});
