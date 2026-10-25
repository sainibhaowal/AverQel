import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import AdaptiveMarkdownTable from "@/app/dashboard/_components/AdaptiveMarkdownTable";

function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        table: ({ children: tableChildren }) => (
          <AdaptiveMarkdownTable>{tableChildren}</AdaptiveMarkdownTable>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

describe("adaptive Markdown tables", () => {
  it("keeps compact rectangular data as a semantic table", () => {
    render(<Markdown>{"| Name | Score |\n| --- | --- |\n| Alpha | 92 |"}</Markdown>);

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("table").parentElement).toHaveAttribute("data-adaptive-table", "grid");
  });

  it("shows the existing table controls above the table and removes prose table margins", () => {
    render(
      <div className="group prose prose-invert">
        <AdaptiveMarkdownTable onSaveToLibrary={vi.fn()}>
          <thead>
            <tr>
              <th>Need</th>
              <th>Available</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Deep reasoning</td>
              <td>Ultra</td>
            </tr>
          </tbody>
        </AdaptiveMarkdownTable>
      </div>,
    );

    const table = screen.getByRole("table");
    expect(table).toHaveStyle({ marginBlock: "0" });

    const actions = screen.getByRole("group", { name: "Table actions" });
    const toolbar = actions.parentElement;
    expect(toolbar).toHaveClass("flex", "min-h-8", "justify-end", "opacity-0");
    expect(toolbar).toHaveClass("group-hover/adaptive-table:opacity-100");
    expect(toolbar).toHaveClass("group-focus-within/adaptive-table:opacity-100");
    expect(toolbar).not.toHaveClass("group-hover:opacity-100");
    expect(toolbar?.nextElementSibling).toBe(table.parentElement);

    expect(screen.queryByRole("button", { name: "Table actions" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy table" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save table to Library" })).toHaveTextContent(
      "Save to Library",
    );
    const exportButton = screen.getByRole("button", { name: "Export table" });
    expect(exportButton).toHaveTextContent("Export");
    expect(screen.getAllByRole("button")).toHaveLength(3);
    vi.spyOn(exportButton, "getBoundingClientRect").mockReturnValue({
      x: 200,
      y: 24,
      width: 100,
      height: 32,
      top: 24,
      right: 300,
      bottom: 56,
      left: 200,
      toJSON: () => ({}),
    });

    fireEvent.click(exportButton);

    expect(exportButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "CSV" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Excel (.xlsx)" })).toBeInTheDocument();
    const exportMenu = screen.getByRole("button", { name: "CSV" }).parentElement;
    expect(exportMenu).toHaveClass("theme-panel", "grid", "min-w-28", "fixed", "z-[1000]");
    expect(exportMenu).toHaveStyle({ position: "fixed", top: "60px", right: "724px" });
    expect(exportMenu?.parentElement).toBe(document.body);
    expect(table.parentElement).not.toContainElement(exportMenu);
  });

  it("turns numbered records with sparse continuation rows into readable cards", () => {
    render(
      <Markdown>
        {
          "| # | Role | Company | Fit | Skills | Link |\n| --- | --- | --- | --- | --- | --- |\n| 1 | Data Analyst | Acme | Dashboard work | | |\n| Part-time and flexible | | | | | |\n| SQL basics | Excel | | | | |\n| 2 | AI Trainer | Labs | Model evaluation | Python | Apply |"
        }
      </Markdown>,
    );

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const cards = document.querySelector('[data-adaptive-table="cards"]');
    expect(cards).not.toBeNull();
    expect(within(cards as HTMLElement).getByText("Data Analyst")).toBeInTheDocument();
    expect(within(cards as HTMLElement).getByText("Part-time and flexible")).toBeInTheDocument();
    expect(within(cards as HTMLElement).getByText("SQL basics")).toBeInTheDocument();
    expect(within(cards as HTMLElement).getByText("Excel")).toBeInTheDocument();
    expect(within(cards as HTMLElement).getByText("AI Trainer")).toBeInTheDocument();
  });

  it("renders a wide research table with links without recursive traversal", () => {
    render(
      <Markdown>
        {
          "| Date | Change | Meaning |\n| --- | --- | --- |\n| Sep 10 | Agents API public beta | Durable sessions and tools |\n| Sep 8 | [Changelog](https://developers.openai.com/api/docs/changelog) | Verified official source |"
        }
      </Markdown>,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Changelog" })).toHaveAttribute(
      "href",
      "https://developers.openai.com/api/docs/changelog",
    );
  });

  it("bounds pathological nested table content instead of overflowing the call stack", () => {
    let nested: ReactNode = "safe";
    for (let depth = 0; depth < 80; depth += 1) nested = <span>{nested}</span>;
    expect(() =>
      render(
        <AdaptiveMarkdownTable>
          <thead>
            <tr>
              <th>Header</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{nested}</td>
            </tr>
          </tbody>
        </AdaptiveMarkdownTable>,
      ),
    ).not.toThrow();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
