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

import UnifiedBrainDocsPage from "../app/documentation/unified-brain/page";

describe("UnifiedBrainDocsPage", () => {
  it("renders the unified brain checklist page", () => {
    render(<UnifiedBrainDocsPage />);

    expect(screen.getByText(/Unified Brain Checklist/i)).toBeInTheDocument();
    expect(
      screen.getByText(/The master orchestrator decides the mission structure/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/You type a request into AverQel or DeepSpace/i)).toBeInTheDocument();
  });
});
