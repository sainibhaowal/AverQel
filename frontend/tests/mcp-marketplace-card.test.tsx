import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MCPMarketplaceCard, { resolveTrustedLogoPath } from "../app/dashboard/mcp/_components/MCPMarketplaceCard";
import { marketplaceEntry } from "./mcp-test-fixtures";

describe("MCPMarketplaceCard", () => {
  it("renders community badges, transport/auth, preview, and trusted logo path", () => {
    render(<MCPMarketplaceCard entry={marketplaceEntry} onConnect={vi.fn()} />);
    expect(screen.getByText("Community")).toBeInTheDocument();
    expect(screen.getByText("Remote HTTP")).toBeInTheDocument();
    expect(screen.getByText("OAuth")).toBeInTheDocument();
    expect(screen.getByText("search_mail")).toBeInTheDocument();
    expect(resolveTrustedLogoPath("google")).toBe("/mcp/google.svg");
    expect(resolveTrustedLogoPath("https://evil.example/logo.svg")).toBeNull();
  });
});
