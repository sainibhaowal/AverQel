import { render, screen } from "@testing-library/react";

import StructuredBlockRenderer from "../app/dashboard/query/_components/StructuredBlockRenderer";

describe("graph block rendering", () => {
  it("renders a graph-json diagram block", async () => {
    render(
      <StructuredBlockRenderer
        blocks={[
          {
            id: "diagram-graph-1",
            type: "diagram",
            title: "Service Graph",
            diagram_type: "graph_canvas",
            source: "graph_json",
            syntax: "",
            description: "High-level service graph.",
            graph: {
              layout: "horizontal",
              nodes: [
                { id: "client", label: "Client", category: "edge" },
                { id: "api", label: "API", category: "service" },
              ],
              edges: [{ source: "client", target: "api", label: "request" }],
            },
          },
        ]}
      />,
    );

    expect(screen.getByText("Service Graph")).toBeInTheDocument();
    expect(screen.getByText("Client")).toBeInTheDocument();
    expect(screen.getByText("API")).toBeInTheDocument();
  });
});
