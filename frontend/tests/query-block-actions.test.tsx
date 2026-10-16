import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CodeBlock from "../app/dashboard/query/_components/CodeBlock";
import MarkdownRenderer from "../app/dashboard/query/_components/MarkdownRenderer";
import TableBlock from "../app/dashboard/query/_components/TableBlock";

const excelMocks = vi.hoisted(() => ({
  addRows: vi.fn(),
  writeBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(0)),
}));

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
const originalExecCommand = Object.getOwnPropertyDescriptor(document, "execCommand");

vi.mock("exceljs", () => ({
  default: {
    Workbook: class Workbook {
      xlsx = { writeBuffer: excelMocks.writeBuffer };

      addWorksheet() {
        return { addRows: excelMocks.addRows };
      }
    },
  },
}));

describe("query block actions", () => {
  beforeEach(() => {
    excelMocks.writeBuffer.mockClear();
    excelMocks.addRows.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    if (originalClipboard) Object.defineProperty(navigator, "clipboard", originalClipboard);
    else Reflect.deleteProperty(navigator, "clipboard");
    if (originalExecCommand) Object.defineProperty(document, "execCommand", originalExecCommand);
    else Reflect.deleteProperty(document, "execCommand");
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

    fireEvent.click(screen.getByText("Export .py"));

    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(appendChild).toHaveBeenCalledWith(anchor);
    expect(anchor.download).toBe("snippet.py");
    expect(click).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledTimes(1);

    createElement.mockRestore();
  });

  it("copies tables and exports them as excel workbooks", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const clickDownload = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
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

    await act(async () => {
      fireEvent.click(screen.getByLabelText("Export table"));
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Excel (.xlsx)"));
    });
    expect(excelMocks.addRows).toHaveBeenCalledWith([
      ["Name", "Value"],
      ["A", "1"],
    ]);
    expect(excelMocks.writeBuffer).toHaveBeenCalledTimes(1);
    expect(clickDownload).toHaveBeenCalledTimes(1);
  });

  it("uses the browser copy fallback when clipboard permission is denied", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("Clipboard permission denied"));
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand,
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

    fireEvent.click(screen.getByRole("button", { name: "Copy table" }));

    await waitFor(() => expect(execCommand).toHaveBeenCalledWith("copy"));
    expect(screen.getByRole("button", { name: "Copy table" })).toHaveAttribute("title", "Copied");
  });

  it("copies complete Markdown-rendered tables", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<MarkdownRenderer content={"| Name | Score |\n| --- | --- |\n| Alpha | 92 |"} />);

    fireEvent.click(screen.getByRole("button", { name: "Copy table" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Name\tScore\nAlpha\t92"));
  });

  it("reports workbook export errors instead of leaving a rejected action", async () => {
    excelMocks.writeBuffer.mockRejectedValueOnce(new Error("Workbook generation failed"));
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

    fireEvent.click(screen.getByRole("button", { name: "Export table" }));
    fireEvent.click(screen.getByRole("button", { name: "Excel (.xlsx)" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Workbook generation failed");
  });

  it("saves a table to the Library with one click when the callback is available", async () => {
    const onSaveToLibrary = vi.fn().mockResolvedValue(undefined);
    render(
      <TableBlock
        block={{
          id: "table-1",
          type: "table",
          headers: ["Name", "Value"],
          rows: [["A", "1"]],
          title: "Metrics Table",
        }}
        onSaveToLibrary={onSaveToLibrary}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Save table to Library" }));

    await waitFor(() => expect(onSaveToLibrary).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("status")).toHaveTextContent("Table saved to Library.");
  });

  it("shows when saving a table to the Library fails", async () => {
    const onSaveToLibrary = vi.fn().mockRejectedValue(new Error("Open a conversation first"));
    render(
      <TableBlock
        block={{ headers: ["Name"], rows: [["A"]], title: "Metrics Table" }}
        onSaveToLibrary={onSaveToLibrary}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Save table to Library" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Open a conversation first");
  });

  it("exports tables as RFC-compatible CSV data", () => {
    const createObjectUrl = vi.fn(() => "blob:csv");
    const click = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    const anchor = document.createElement("a");
    Object.defineProperty(anchor, "click", { value: click });
    const createElement = vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      if (tagName === "a") return anchor;
      return originalCreateElement(tagName);
    });

    render(
      <TableBlock
        block={{ headers: ["Name", "Note"], rows: [["A", 'Say "hello"']], title: "Metrics" }}
      />,
    );

    fireEvent.click(screen.getByLabelText("Export table"));
    fireEvent.click(screen.getByText("CSV"));

    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(anchor.download).toBe("metrics.csv");
    expect(click).toHaveBeenCalledTimes(1);
    createElement.mockRestore();
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
