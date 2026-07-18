import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CodeBlock from "../app/dashboard/query/_components/CodeBlock";
import TableBlock from "../app/dashboard/query/_components/TableBlock";

const xlsxMocks = vi.hoisted(() => ({
  writeFileXLSX: vi.fn(),
  bookAppendSheet: vi.fn(),
}));

vi.mock("xlsx", () => ({
  default: {
    utils: {
      aoa_to_sheet: vi.fn((rows: unknown[][]) => ({ rows })),
      book_new: vi.fn(() => ({ sheets: [] })),
      book_append_sheet: xlsxMocks.bookAppendSheet,
    },
    writeFileXLSX: xlsxMocks.writeFileXLSX,
  },
  utils: {
    aoa_to_sheet: vi.fn((rows: unknown[][]) => ({ rows })),
    book_new: vi.fn(() => ({ sheets: [] })),
    book_append_sheet: xlsxMocks.bookAppendSheet,
  },
  writeFileXLSX: xlsxMocks.writeFileXLSX,
}));

describe("query block actions", () => {
  beforeEach(() => {
    xlsxMocks.writeFileXLSX.mockReset();
    xlsxMocks.bookAppendSheet.mockReset();
    vi.restoreAllMocks();
  });

  it("saves code blocks with the exact language extension", () => {
    const createObjectUrl = vi.fn(() => "blob:python");
    const revokeObjectUrl = vi.fn();
    const click = vi.fn();
    const appendChild = vi.spyOn(document.body, "appendChild");
    const remove = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectUrl,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectUrl,
    });

    const anchor = document.createElement("a");
    Object.defineProperty(anchor, "click", { value: click });
    Object.defineProperty(anchor, "remove", { value: remove });
    const createElement = vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      if (tagName === "a") {
        return anchor;
      }
      return originalCreateElement(tagName);
    });

    render(<CodeBlock language="python" value={'print("hello")'} />);

    fireEvent.click(screen.getByText("Save"));

    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(appendChild).toHaveBeenCalledWith(anchor);
    expect(anchor.download).toBe("snippet.py");
    expect(click).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledTimes(1);

    createElement.mockRestore();
  });

  it("copies tables and exports them as excel workbooks", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText,
      },
    });

    render(
      <TableBlock
        block={{
          type: "table",
          headers: ["Name", "Value"],
          rows: [["A", "1"]],
          title: "Metrics Table",
        }}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByLabelText("Copy table"));
    });
    expect(writeText).toHaveBeenCalledWith("Name\tValue\nA\t1");

    fireEvent.click(screen.getByLabelText("Export table as Excel"));
    expect(xlsxMocks.bookAppendSheet).toHaveBeenCalledTimes(1);
    expect(xlsxMocks.writeFileXLSX).toHaveBeenCalledWith(expect.any(Object), "metrics-table.xlsx");
  });

  it("renders highlighted code tokens with distinct styles", () => {
    const { getByTestId } = render(
      <CodeBlock
        language="typescript"
        value={`function greet(name: string) {\n  return { message: "hi", count: 2 };\n}`}
      />,
    );

    const block = getByTestId("highlighted-code-block");
    const spans = Array.from(block.querySelectorAll("span"));
    const styledSpans = spans.filter((span) => span.getAttribute("style")?.includes("color"));

    expect(styledSpans.length).toBeGreaterThan(6);
    expect(styledSpans.some((span) => span.textContent === "function")).toBe(true);
    expect(styledSpans.some((span) => span.textContent === "greet")).toBe(true);
    expect(styledSpans.some((span) => span.textContent === '"hi"')).toBe(true);
    expect(styledSpans.some((span) => span.textContent === "2")).toBe(true);
    expect(new Set(styledSpans.map((span) => span.getAttribute("style"))).size).toBeGreaterThan(3);
  });

  it("caps tall collapsed code blocks to an internal scroll height", async () => {
    const scrollHeightGetter = vi
      .spyOn(HTMLElement.prototype, "scrollHeight", "get")
      .mockReturnValue(1600);

    render(
      <CodeBlock
        language="python"
        value={Array.from({ length: 80 }, (_, index) => `print(${index})`).join("\n")}
      />,
    );

    const block = await screen.findByTestId("highlighted-code-block");
    expect(block).toHaveStyle({ height: "560px" });

    scrollHeightGetter.mockRestore();
  });
});
