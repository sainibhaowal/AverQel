import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const composioApi = vi.hoisted(() => ({
  connectComposioToolkit: vi.fn(),
  getComposioAdminStatus: vi.fn(),
  getComposioStatus: vi.fn(),
  getComposioToolkit: vi.fn(),
  getComposioToolkits: vi.fn(),
  removeComposioApiKey: vi.fn(),
  saveComposioApiKey: vi.fn(),
}));

vi.mock("@/lib/mcp-api", () => composioApi);
vi.mock("@/app/components/ui/AverQelDialogHost", () => ({ averqelConfirm: vi.fn() }));

import MCPComposioPanel from "../app/dashboard/mcp/_components/MCPComposioPanel";

describe("MCP Composio catalog panel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    composioApi.getComposioStatus.mockResolvedValue({
      configured: true,
      callback_verifier_enabled: true,
      callback_verifier_url: "https://averqel.example/dashboard/mcp/composio/callback",
    });
    composioApi.getComposioAdminStatus.mockRejectedValue(new Error("not a platform admin"));
    composioApi.getComposioToolkits.mockResolvedValue({
      items: [
        {
          slug: "google_calendar",
          name: "Google Calendar",
          description: "Manage events",
          categories: ["Productivity"],
          tool_count: 2,
          auth_schemes: ["oauth2"],
          no_auth: false,
        },
      ],
      next_cursor: null,
      current_page: 1,
      total_items: 1,
    });
    composioApi.getComposioToolkit.mockResolvedValue({
      slug: "google_calendar",
      name: "Google Calendar",
      description: "Manage events",
      categories: ["Productivity"],
      tool_count: 2,
      auth_schemes: ["oauth2"],
      no_auth: false,
      tools: [
        {
          name: "GOOGLE_CALENDAR_LIST_EVENTS",
          description: "Read calendar events",
          input_schema: {
            type: "object",
            properties: {
              calendar_id: { type: "string", description: "Calendar to inspect" },
            },
          },
          risk_labels: ["read"],
        },
      ],
      tools_loaded: 1,
      tools_next_cursor: null,
    });
  });

  it("shows live apps, tool input fields, refresh, and hides platform key controls from users", async () => {
    render(
      <MCPComposioPanel
        connectedProviderSlugs={[]}
        connectingProviderSlugs={[]}
        onConnected={vi.fn()}
      />,
    );

    expect(await screen.findByRole("heading", { name: "Google Calendar" })).toBeInTheDocument();
    expect(screen.getByText("1 Composio apps available")).toBeInTheDocument();
    expect(screen.getByText("oauth2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect" })).toBeEnabled();
    expect(screen.queryByLabelText("Composio project API key")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View tools" }));
    expect(await screen.findByText("GOOGLE_CALENDAR_LIST_EVENTS")).toBeInTheDocument();
    expect(screen.getByText("Read · may run automatically")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Input fields"));
    expect(screen.getByText("calendar_id")).toBeInTheDocument();
    expect(screen.getByText(/Calendar to inspect/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Refresh catalog" }));
    await waitFor(() => expect(composioApi.getComposioToolkits).toHaveBeenCalledTimes(2));
  });

  it("adds no-auth Composio apps without requiring the OAuth callback verifier", async () => {
    composioApi.getComposioStatus.mockResolvedValue({
      configured: true,
      callback_verifier_enabled: false,
      callback_verifier_url: null,
    });
    composioApi.getComposioToolkits.mockResolvedValue({
      items: [
        {
          slug: "open_meteo",
          name: "Open Meteo",
          description: "Weather data",
          categories: ["Utilities"],
          tool_count: 1,
          auth_schemes: [],
          no_auth: true,
        },
      ],
      next_cursor: null,
      current_page: 1,
      total_items: 1,
    });
    composioApi.connectComposioToolkit.mockResolvedValue({
      authorization_required: false,
      authorization_url: null,
      already_connected: false,
      server: {},
    });
    const onConnected = vi.fn();

    render(
      <MCPComposioPanel
        connectedProviderSlugs={[]}
        connectingProviderSlugs={[]}
        onConnected={onConnected}
      />,
    );

    const addButton = await screen.findByRole("button", { name: "Add to DeepSpace" });
    expect(addButton).toBeEnabled();
    fireEvent.click(addButton);
    await waitFor(() =>
      expect(composioApi.connectComposioToolkit).toHaveBeenCalledWith("open_meteo"),
    );
    await waitFor(() => expect(onConnected).toHaveBeenCalledOnce());
  });
});
