import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../app/documentation/_components/DocsShell", () => ({
  DocsShell: ({
    title,
    intro,
    children,
  }: {
    title: string;
    intro: string;
    children: ReactNode;
  }) => (
    <main>
      <h1>{title}</h1>
      <p>{intro}</p>
      {children}
    </main>
  ),
  DocsSection: ({ title, children }: { title: string; children: ReactNode }) => (
    <section>
      <h2>{title}</h2>
      {children}
    </section>
  ),
  DocsCards: ({ items }: { items: Array<{ title: string; body: string; href?: string }> }) => (
    <div>
      {items.map((item) => (
        <article key={item.title}>
          <h3>{item.title}</h3>
          <p>{item.body}</p>
        </article>
      ))}
    </div>
  ),
}));

import OrchestrationDocsPage from "../app/documentation/orchestration/page";

describe("OrchestrationDocsPage", () => {
  it("renders the orchestration documentation page", () => {
    render(<OrchestrationDocsPage />);

    expect(
      screen.getByText(
        /How AverQel coordinates DeepSpace, the inline agent loop, parallel subagents/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/AverQel is the primary mission core/i)).toBeInTheDocument();
  });
});
