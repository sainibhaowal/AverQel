import { normalizeMarkdown } from "@/app/dashboard/deepspace/_lib/markdown";

describe("DeepSpace markdown normalization", () => {
  it("recovers a compact two-column table with an embedded separator", () => {
    const normalized = normalizeMarkdown(
      "| Detail | Value ||---| | Current Temp | 18.4 °C || Feels Like | ~18 °C || Conditions | Overcast / Light rain | | Wind | West, 18 km/h | | Humidity | 65% |",
    );

    expect(normalized).toContain("| Detail | Value |");
    expect(normalized).toContain("| --- | --- |");
    expect(normalized).toContain("| Current Temp | 18.4 °C |");
    expect(normalized).toContain("| Conditions | Overcast / Light rain |");
    expect(normalized).not.toContain("||---|");
  });
});
