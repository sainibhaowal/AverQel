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

    expect(screen.getByRole("heading", { name: "System walkthrough" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Documents Hub to Query" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Where DeepSpace fits" })).toBeInTheDocument();
    expect(
      screen.getByText(/Documents Hub manages sources\. Query finds evidence/i),
    ).toBeInTheDocument();
  });
});
