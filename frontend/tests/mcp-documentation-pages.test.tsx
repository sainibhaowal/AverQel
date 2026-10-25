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
  it("documents the Composio marketplace, user setup, and approval limits", () => {
    render(<ConnectorsMcpDocsPage />);

    expect(screen.getAllByRole("heading", { name: "Connect an app" })).not.toHaveLength(0);
    expect(screen.getAllByRole("heading", { name: "OAuth setup" })).not.toHaveLength(0);
    expect(
      screen.getAllByRole("heading", { name: "Account isolation and data handling" }),
    ).not.toHaveLength(0);
    expect(
      screen.getAllByRole("heading", { name: "Tool permissions and approvals" }),
    ).not.toHaveLength(0);
    expect(screen.getAllByText(/Add your own Composio project API key/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/existing installed connections are retained/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/do not need to register a callback verifier/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/Always allow/i)).not.toHaveLength(0);
    expect(
      screen.queryByRole("heading", { name: "Official and community providers" }),
    ).not.toBeInTheDocument();
  });

  it("documents MCP privacy boundaries and approval controls", () => {
    render(<PrivacySecurityPage />);

    expect(
      screen.getAllByRole("heading", { name: "MCP account and tenant isolation" }),
    ).not.toHaveLength(0);
    expect(
      screen.getAllByRole("heading", { name: "OAuth consent and secret lifecycle" }),
    ).not.toHaveLength(0);
    expect(
      screen.getAllByRole("heading", { name: "Permission modes and precedence" }),
    ).not.toHaveLength(0);
    expect(
      screen.getAllByText(/Each AverQel user supplies their own Composio project API key/i),
    ).not.toHaveLength(0);
    expect(
      screen.getAllByText(/running backend decrypts it to make Composio requests/i),
    ).not.toHaveLength(0);
    expect(screen.getAllByText(/Read-only/i)).not.toHaveLength(0);
  });

  it("separates model providers from Composio and explains user-owned setup", () => {
    render(<ProvidersPage />);

    expect(
      screen.getAllByRole("heading", { name: "Model providers versus MCP providers" }),
    ).not.toHaveLength(0);
    expect(screen.getAllByRole("heading", { name: "Composio app setup" })).not.toHaveLength(0);
    expect(
      screen.getAllByRole("heading", { name: "OAuth and callback requirements" }),
    ).not.toHaveLength(0);
    expect(screen.getAllByText(/encrypts each user's Composio project key/i)).not.toHaveLength(0);
    expect(
      screen.queryByRole("heading", { name: "Google and GitHub MCP connections" }),
    ).not.toBeInTheDocument();
  });
});
