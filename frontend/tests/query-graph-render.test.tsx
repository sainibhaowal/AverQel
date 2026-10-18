import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import StructuredBlockRenderer from "../app/dashboard/query/_components/StructuredBlockRenderer";
import GraphBlock from "../app/dashboard/query/_components/GraphBlock";

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

  it("commits canvas edits through the persistence callback", () => {
    const onChange = vi.fn();
    render(
      <GraphBlock
        onChange={onChange}
        block={{
          id: "diagram-graph-persist",
          type: "diagram",
          title: "Editable graph",
          diagram_type: "graph_canvas",
          source: "graph_json",
          syntax: "",
          graph: {
            layout: "horizontal",
            nodes: [{ id: "one", label: "One", x: 120, y: 120 }],
            edges: [],
          },
        }}
      />,
    );

    const editButton = screen.getByRole("button", { name: "Edit canvas" });
    expect(editButton).toHaveClass("visual-block-action", "rounded-lg");
    fireEvent.click(editButton);
    const doneButton = screen.getByRole("button", { name: "Done" });
    expect(doneButton).toHaveClass("visual-block-action", "visual-block-action--active");
    fireEvent.click(doneButton);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "diagram-graph-persist",
        source: "graph_json",
        graph: expect.objectContaining({ nodes: expect.any(Array) }),
      }),
    );
  });

  it("imports a bounded DeepSpace draw file into the in-chat canvas", async () => {
    render(
      <GraphBlock
        block={{
          id: "diagram-graph-import",
          type: "diagram",
          title: "Imported graph",
          diagram_type: "graph_canvas",
          source: "graph_json",
          syntax: "",
          graph: { layout: "horizontal", nodes: [], edges: [] },
        }}
      />,
    );
    const input = screen.getByLabelText("Select DeepSpace draw file");
    const file = new File(
      [
        JSON.stringify({
          nodes: [{ id: "deploy", label: "Deploy", x: 100, y: 100 }],
          edges: [],
        }),
      ],
      "release.draw.json",
      { type: "application/json" },
    );
    Object.defineProperty(file, "text", {
      value: async () =>
        JSON.stringify({ nodes: [{ id: "deploy", label: "Deploy", x: 100, y: 100 }], edges: [] }),
    });
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    fireEvent.change(input);

    expect(await screen.findByText("Deploy")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
  });

  it("rejects malformed draw files with a visible message", async () => {
    render(
      <GraphBlock
        block={{
          id: "diagram-graph-invalid-import",
          type: "diagram",
          title: "Imported graph",
          diagram_type: "graph_canvas",
          source: "graph_json",
          syntax: "",
          graph: { layout: "horizontal", nodes: [], edges: [] },
        }}
      />,
    );
    const input = screen.getByLabelText("Select DeepSpace draw file");
    const file = new File(["not graph JSON"], "broken.draw.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: async () => "not graph JSON" });
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    fireEvent.change(input);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "That file is not a valid DeepSpace .draw.json graph.",
      ),
    );
  });
});
