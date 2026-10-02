import { render, screen, within } from "@testing-library/react";
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
