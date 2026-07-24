import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MCPProviderDetails from "../app/dashboard/mcp/_components/MCPProviderDetails";
import { marketplaceEntry } from "./mcp-test-fixtures";

describe("MCPProviderDetails", () => {
  it("renders provider identity, scopes, links, tools, and safe health", () => {
    render(<MCPProviderDetails entry={marketplaceEntry} onConnect={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Community Mail" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/community connector/i);
    expect(screen.getByText("mail.read")).toBeInTheDocument();
    expect(screen.getByText("https://provider.example/mcp")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /documentation/i })).toHaveAttribute("href", "https://provider.example/docs");
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("search_mail")).toBeInTheDocument();
  });
});
