import { describe, expect, it } from "vitest";

import {
  CSV_PREVIEW_MAX_COLUMNS,
  CSV_PREVIEW_MAX_ROWS,
  parseCsvPreview,
} from "@/app/dashboard/deepspace/_components/DeepSpaceLibraryPreview";

describe("DeepSpace Library CSV preview", () => {
  it("bounds a million-row-style CSV before it reaches the DOM", () => {
    const csv = `name,value\n${"row,1\n".repeat(CSV_PREVIEW_MAX_ROWS + 50)}`;

    const preview = parseCsvPreview(csv);

    expect(preview.truncated).toBe(true);
    expect(preview.rows).toHaveLength(CSV_PREVIEW_MAX_ROWS);
    expect(preview.rows[0]).toEqual(["name", "value"]);
  });

  it("bounds visible CSV columns", () => {
    const csv = Array.from({ length: CSV_PREVIEW_MAX_COLUMNS + 10 }, (_, index) => `c${index}`).join(",");

    const preview = parseCsvPreview(csv);

    expect(preview.rows[0]).toHaveLength(CSV_PREVIEW_MAX_COLUMNS);
  });
});
