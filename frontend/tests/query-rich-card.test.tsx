import { render, screen } from "@testing-library/react";

import StructuredBlockRenderer from "../app/dashboard/query/_components/StructuredBlockRenderer";

it("renders structured information cards with safe actions", () => {
  render(
    <StructuredBlockRenderer
      blocks={[
        {
          id: "card-1",
          type: "card",
          title: "Research finding",
          tone: "info",
          content: "A **verified** result.",
          metrics: [{ label: "Confidence", value: "96%" }],
          actions: [{ label: "Open source", href: "https://example.com" }],
        },
      ]}
    />,
  );

  expect(screen.getByText("Research finding")).toBeInTheDocument();
  expect(screen.getByText("verified")).toBeInTheDocument();
  expect(screen.getByText("96%")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Open source/ })).toHaveAttribute(
    "href",
    "https://example.com/",
  );
});
