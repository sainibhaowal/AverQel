import { normalizeMarkdown } from "./markdown";

describe("answer markdown normalization", () => {
  it("unwraps a complete markdown fence", () => {
    expect(normalizeMarkdown("```markdown\n## Hello\n```")).toBe("## Hello");
  });

  it("repairs collapsed headings and separated table fences", () => {
    expect(
      normalizeMarkdown(
        "Memory Efficiency#### Key Improvement\n| Model | FLOPs |\n\n| --- | --- |",
      ),
    ).toContain("Memory Efficiency\n\n#### Key Improvement\n| Model | FLOPs |\n| --- | --- |");
  });

  it("recovers rows when a provider concatenates a whole table into one line", () => {
    const normalized = normalizeMarkdown(
      "| Non-Ideality | Impact | Mitigation | | :--- | :--- | :--- | | Clock Jitter | Noise floor | PLL | | Capacitor Mismatch | kT/C noise | Larger caps |",
    );

    expect(normalized).toContain("| Non-Ideality | Impact | Mitigation |");
    expect(normalized).toContain("| Clock Jitter | Noise floor | PLL |");
    expect(normalized).toContain("| Capacitor Mismatch | kT/C noise | Larger caps |");
    expect(normalized).not.toContain("| | :---");
  });
});
