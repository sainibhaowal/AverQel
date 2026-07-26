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
}));

import SimpleSystemWalkthroughPage from "../app/documentation/simple-system-walkthrough/page";

describe("SimpleSystemWalkthroughPage", () => {
  it("renders the simple walkthrough page", () => {
    render(<SimpleSystemWalkthroughPage />);

    expect(screen.getByText(/Simple System Walkthrough/i)).toBeInTheDocument();
    expect(screen.getByText(/You type a request into chat or DeepSpace/i)).toBeInTheDocument();
    expect(screen.getByText(/Chat is the product surface/i)).toBeInTheDocument();
  });
});
