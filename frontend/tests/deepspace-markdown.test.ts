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

  it("recovers provider tables whose rows and separator are emitted on one line", () => {
    const normalized = normalizeMarkdown(
      "| Game | Release | Genre | |------|---------| | **Avowed** | Feb 18, 2025 | RPG (Game Pass) | | **Monster Hunter Wilds** | Feb 28, 2025 | Action | | **Battlefield 6** | 2025 | FPS (top player-rated) | | **Cronos: The New Dawn** | Sep 5, 2025 | Horror | | **Borderlands 4** | 2025 | Shooter |",
    );

    expect(normalized).toContain("| Game | Release | Genre |");
    expect(normalized).toContain("| **Avowed** | Feb 18, 2025 | RPG (Game Pass) |");
    expect(normalized).toContain("| **Borderlands 4** | 2025 | Shooter |");
  });

  it("joins a table header and separator when a provider inserts a blank line", () => {
    const normalized = normalizeMarkdown(
      "| Section | What's Inside |\n\n|---|---------------| | 1 | **PET Scans** — hospital imaging | | 2 | **Theranostics** — targeted therapy |",
    );

    expect(normalized).toBe(
      "| Section | What's Inside |\n| --- | --- |\n| 1 | **PET Scans** — hospital imaging |\n| 2 | **Theranostics** — targeted therapy |",
    );
  });
});
