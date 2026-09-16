import { describe, expect, it } from "vitest";

import {
  libraryFileKind,
  libraryKindSupportsEditor,
  libraryKindSupportsPreview,
} from "@/app/dashboard/deepspace/_components/DeepSpaceLibraryFormats";

describe("DeepSpace Library format detection", () => {
  it("selects the dedicated renderer for supported file families", () => {
    expect(libraryFileKind("notes.md", "text/markdown")).toBe("markdown");
    expect(libraryFileKind("changes.diff", "text/plain")).toBe("diff");
    expect(libraryFileKind("rows.csv", "text/csv")).toBe("csv");
    expect(libraryFileKind("workbook.xlsx", "application/octet-stream")).toBe("spreadsheet");
    expect(libraryFileKind("slides.pptx", "application/octet-stream")).toBe("pptx");
    expect(libraryFileKind("plan.odt", "application/vnd.oasis.opendocument.text")).toBe("docx");
    expect(libraryFileKind("diagram.svg", "image/svg+xml")).toBe("svg");
    expect(libraryFileKind("recording.mp3", "audio/mpeg")).toBe("audio");
    expect(libraryFileKind("bundle.zip", "application/zip")).toBe("archive");
  });

  it("keeps binary files preview-only and text files editable", () => {
    expect(libraryKindSupportsEditor(libraryFileKind("main.py", "text/x-python"))).toBe(true);
    expect(libraryKindSupportsPreview(libraryFileKind("main.py", "text/x-python"))).toBe(false);
    expect(libraryKindSupportsEditor(libraryFileKind("report.pdf", "application/pdf"))).toBe(false);
    expect(libraryKindSupportsPreview(libraryFileKind("report.pdf", "application/pdf"))).toBe(true);
    expect(libraryFileKind("PDF Vob 7-8.txt", "text/plain")).toBe("text");
    expect(libraryKindSupportsEditor(libraryFileKind("PDF Vob 7-8.txt", "text/plain"))).toBe(true);
    expect(libraryKindSupportsPreview(libraryFileKind("PDF Vob 7-8.txt", "text/plain"))).toBe(true);
    expect(libraryKindSupportsEditor(libraryFileKind("proposal.docx", "application/octet-stream"))).toBe(true);
    expect(libraryKindSupportsPreview(libraryFileKind("proposal.docx", "application/octet-stream"))).toBe(true);
    expect(libraryKindSupportsEditor(libraryFileKind("data.csv", "text/csv"))).toBe(true);
    expect(libraryKindSupportsPreview(libraryFileKind("data.csv", "text/csv"))).toBe(true);
  });
});
