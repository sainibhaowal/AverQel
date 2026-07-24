import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ConnectorsMcpDocsPage from "../app/documentation/connectors-mcp/page";
import PrivacySecurityPage from "../app/documentation/privacy-security/page";
import ProvidersPage from "../app/documentation/providers/page";

vi.mock("../app/components/marketing/ParticleBackground", () => ({
  default: () => null,
}));

afterEach(() => {
  document.body.innerHTML = "";
});

describe("MCP documentation", () => {
  it("documents the marketplace, transport limits, and policy precedence", () => {
    render(<ConnectorsMcpDocsPage />);

    expect(screen.getAllByRole("heading", { name: "Official and community providers" })).not.toHaveLength(0);
    expect(screen.getAllByRole("heading", { name: "OAuth, token storage, and revocation" })).not.toHaveLength(0);
    expect(screen.getAllByRole("heading", { name: "Tool permissions and precedence" })).not.toHaveLength(0);
    expect(screen.getAllByRole("heading", { name: "Remote transport and current limits" })).not.toHaveLength(0);
    expect(screen.getAllByText(/Local stdio processes, SSH-launched servers/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/Always allow/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/Needs approval/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/Blocked/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/New, Trending, and Interactive are catalog attributes/i)).not.toHaveLength(0);
  });

  it("documents MCP privacy boundaries and approval controls", () => {
    render(<PrivacySecurityPage />);

    expect(screen.getAllByRole("heading", { name: "MCP account and tenant isolation" })).not.toHaveLength(0);
    expect(screen.getAllByRole("heading", { name: "OAuth consent and secret lifecycle" })).not.toHaveLength(0);
    expect(screen.getAllByRole("heading", { name: "Permission modes and precedence" })).not.toHaveLength(0);
    expect(screen.getAllByText(/Access tokens, refresh tokens, and client secrets/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/Read-only/i)).not.toHaveLength(0);
  });

  it("separates model providers from MCP providers and explains setup state", () => {
    render(<ProvidersPage />);

    expect(screen.getAllByRole("heading", { name: "Model providers versus MCP providers" })).not.toHaveLength(0);
    expect(screen.getAllByRole("heading", { name: "Google and GitHub MCP connections" })).not.toHaveLength(0);
    expect(screen.getAllByRole("heading", { name: "Why AverQel does not clone MCP repositories" })).not.toHaveLength(0);
    expect(screen.getAllByText(/Setup pending/i)).not.toHaveLength(0);
  });
});
