import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const composioApi = vi.hoisted(() => ({
  connectComposioToolkit: vi.fn(),
  getComposioStatus: vi.fn(),
  getComposioToolkit: vi.fn(),
  getComposioToolkits: vi.fn(),
  safeExternalUrl: (value?: string | null) => {
    if (!value) return null;
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password
        ? url.toString()
        : null;
    } catch {
      return null;
    }
  },
}));

vi.mock("@/lib/mcp-api", () => composioApi);
vi.mock("@/app/components/ui/AverQelDialogHost", () => ({ averqelConfirm: vi.fn() }));

import MCPComposioPanel from "../app/dashboard/mcp/_components/MCPComposioPanel";

describe("MCP Composio catalog panel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    composioApi.getComposioStatus.mockResolvedValue({
      configured: true,
      oauth_callback_ready: true,
    });
    composioApi.getComposioToolkits.mockResolvedValue({
      items: [
        {
          slug: "google_calendar",
          name: "Google Calendar",
          description: "Manage events",
          logo_url: "https://calendar.google.com/stale-logo.png",
          app_url: "https://calendar.google.com",
          auth_guide_url: "https://composio.dev/auth/googlecalendar",
          version: "20261001_00",
          updated_at: "2026-10-01T12:00:00Z",
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
      logo_url: "https://calendar.google.com/stale-logo.png",
      app_url: "https://calendar.google.com",
      auth_guide_url: "https://composio.dev/auth/googlecalendar",
      version: "20261001_00",
      updated_at: "2026-10-01T12:00:00Z",
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
            required: ["calendar_id"],
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

  it("shows real Composio logos and opens complete app details and tools", async () => {
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
    expect(screen.getByTestId("composio-app-logo").querySelector("img")).toHaveAttribute(
      "src",
      "https://logos.composio.dev/api/google_calendar",
    );
    expect(screen.getByTestId("composio-app-logo")).toHaveClass("dark:bg-white");
    expect(
      screen.getByRole("heading", { name: "Google Calendar" }).closest("article")?.parentElement,
    ).toHaveClass("xl:grid-cols-4", "2xl:grid-cols-5");
    fireEvent.error(
      screen.getByTestId("composio-app-logo").querySelector("img") as HTMLImageElement,
    );
    expect(screen.getByTestId("composio-logo-fallback")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View details" }));
    const detailsDialog = await screen.findByRole("dialog");
    expect(detailsDialog).toBeVisible();
    expect(within(detailsDialog).getByText("Manage events")).toBeInTheDocument();
    expect(screen.getByText("Not provided in Composio’s toolkit catalog")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /App website/ })).toHaveAttribute(
      "href",
      "https://calendar.google.com/",
    );
    expect(screen.getByRole("link", { name: /Authentication guide/ })).toHaveAttribute(
      "href",
      "https://composio.dev/auth/googlecalendar",
    );
    expect(await screen.findByText("GOOGLE_CALENDAR_LIST_EVENTS")).toBeInTheDocument();
    expect(screen.getByText("Read · may run automatically")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Input fields (1)" }));
    expect(screen.getByText("calendar_id")).toBeInTheDocument();
    expect(screen.getByText("· required")).toBeInTheDocument();
    expect(screen.getByText(/Calendar to inspect/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close app details" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Refresh catalog" }));
    await waitFor(() => expect(composioApi.getComposioToolkits).toHaveBeenCalledTimes(2));
  });

  it("loads later tool pages inside the same app details view", async () => {
    composioApi.getComposioToolkit.mockResolvedValueOnce({
      slug: "google_calendar",
      name: "Google Calendar",
      description: "Manage events",
      logo_url: "https://assets.composio.dev/logos/google-calendar.png",
      app_url: "https://calendar.google.com",
      categories: ["Productivity"],
      tool_count: 2,
      auth_schemes: ["oauth2"],
      no_auth: false,
      tools: [
        {
          name: "GOOGLE_CALENDAR_LIST_EVENTS",
          description: "Read calendar events",
          input_schema: { type: "object", properties: {} },
          risk_labels: ["read"],
        },
      ],
      tools_loaded: 1,
      tools_next_cursor: "calendar-tools-page-2",
    });
    composioApi.getComposioToolkit.mockResolvedValueOnce({
      slug: "google_calendar",
      name: "Google Calendar",
      description: "Manage events",
      logo_url: "https://assets.composio.dev/logos/google-calendar.png",
      app_url: "https://calendar.google.com",
      categories: ["Productivity"],
      tool_count: 2,
      auth_schemes: ["oauth2"],
      no_auth: false,
      tools: [
        {
          name: "GOOGLE_CALENDAR_CREATE_EVENT",
          description: "Create a calendar event",
          input_schema: { type: "object", properties: {} },
          risk_labels: ["write"],
        },
      ],
      tools_loaded: 1,
      tools_next_cursor: null,
    });

    render(
      <MCPComposioPanel
        connectedProviderSlugs={[]}
        connectingProviderSlugs={[]}
        onConnected={vi.fn()}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "View details" }));
    expect(await screen.findByText("GOOGLE_CALENDAR_LIST_EVENTS")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more tools" }));
    expect(await screen.findByText("GOOGLE_CALENDAR_CREATE_EVENT")).toBeInTheDocument();
    expect(composioApi.getComposioToolkit).toHaveBeenLastCalledWith(
      "google_calendar",
      "calendar-tools-page-2",
      { signal: expect.any(AbortSignal) },
    );
  });

  it("uses the Composio CDN instead of app-owned logo URLs", async () => {
    composioApi.getComposioToolkits.mockResolvedValue({
      items: [
        {
          slug: "google_calendar",
          name: "Google Calendar",
          description: "Manage events",
          logo_url: "https://untrusted.example/logo.svg",
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

    render(
      <MCPComposioPanel
        connectedProviderSlugs={[]}
        connectingProviderSlugs={[]}
        onConnected={vi.fn()}
      />,
    );

    await screen.findByRole("heading", { name: "Google Calendar" });
    expect(screen.getByTestId("composio-app-logo").querySelector("img")).toHaveAttribute(
      "src",
      "https://logos.composio.dev/api/google_calendar",
    );
    expect(screen.queryByTestId("composio-logo-fallback")).not.toBeInTheDocument();
  });

  it("shows Composio logos for toolkit slugs beginning with an underscore", async () => {
    composioApi.getComposioToolkits.mockResolvedValue({
      items: [
        {
          slug: "_1password",
          name: "1Password",
          description: "Password manager",
          categories: ["Security"],
          tool_count: 6,
          auth_schemes: ["API_KEY"],
          no_auth: false,
        },
        {
          slug: "_21risk",
          name: "21risk",
          description: "Compliance and risk management",
          categories: ["Business"],
          tool_count: 8,
          auth_schemes: ["API_KEY"],
          no_auth: false,
        },
      ],
      next_cursor: null,
      current_page: 1,
      total_items: 2,
    });

    render(
      <MCPComposioPanel
        connectedProviderSlugs={[]}
        connectingProviderSlugs={[]}
        onConnected={vi.fn()}
      />,
    );

    await screen.findByRole("heading", { name: "1Password" });
    await screen.findByRole("heading", { name: "21risk" });
    const logos = screen.getAllByTestId("composio-app-logo");
    expect(logos[0].querySelector("img")).toHaveAttribute(
      "src",
      "https://logos.composio.dev/api/_1password",
    );
    expect(logos[1].querySelector("img")).toHaveAttribute(
      "src",
      "https://logos.composio.dev/api/_21risk",
    );

    const passwordCard = screen.getByRole("heading", { name: "1Password" }).closest("article");
    fireEvent.click(
      within(passwordCard as HTMLElement).getByRole("button", { name: "View details" }),
    );
    await waitFor(() =>
      expect(composioApi.getComposioToolkit).toHaveBeenCalledWith("_1password", null, {
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it("does not build a logo URL from an invalid toolkit slug", async () => {
    composioApi.getComposioToolkits.mockResolvedValue({
      items: [
        {
          slug: "https://attacker.example",
          name: "Unknown toolkit",
          description: "Invalid slug",
          logo_url: "https://attacker.example/logo.svg",
          categories: [],
          tool_count: 0,
          auth_schemes: [],
          no_auth: false,
        },
      ],
      next_cursor: null,
      current_page: 1,
      total_items: 1,
    });

    render(
      <MCPComposioPanel
        connectedProviderSlugs={[]}
        connectingProviderSlugs={[]}
        onConnected={vi.fn()}
      />,
    );

    await screen.findByRole("heading", { name: "Unknown toolkit" });
    expect(screen.getByTestId("composio-logo-fallback")).toBeInTheDocument();
    expect(screen.getByTestId("composio-app-logo").querySelector("img")).not.toBeInTheDocument();
  });

  it("keeps catalog search usable while loading and cancels an obsolete request", async () => {
    composioApi.getComposioToolkits.mockReturnValueOnce(new Promise(() => undefined));

    render(
      <MCPComposioPanel
        connectedProviderSlugs={[]}
        connectingProviderSlugs={[]}
        onConnected={vi.fn()}
      />,
    );

    const search = await screen.findByRole("textbox", { name: "Search Composio apps" });
    expect(await screen.findByRole("status", { name: "Loading Composio apps…" })).toBeVisible();
    expect(search).toBeEnabled();
    expect(composioApi.getComposioToolkits).toHaveBeenNthCalledWith(
      1,
      { q: "", cursor: undefined, limit: 24 },
      { signal: expect.any(AbortSignal) },
    );

    fireEvent.change(search, { target: { value: "calendar" } });
    await waitFor(() => expect(composioApi.getComposioToolkits).toHaveBeenCalledTimes(2));
    expect(composioApi.getComposioToolkits.mock.calls[0][1].signal.aborted).toBe(true);
    expect(await screen.findByRole("heading", { name: "Google Calendar" })).toBeInTheDocument();
  });

  it("offers a retry after the live catalog request fails", async () => {
    composioApi.getComposioToolkits.mockRejectedValueOnce(new Error("Catalog unavailable"));

    render(
      <MCPComposioPanel
        connectedProviderSlugs={[]}
        connectingProviderSlugs={[]}
        onConnected={vi.fn()}
      />,
    );

    expect(await screen.findByText("Composio apps could not be loaded")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry catalog" }));
    expect(await screen.findByRole("heading", { name: "Google Calendar" })).toBeInTheDocument();
  });

  it("adds no-auth Composio apps without requiring an OAuth callback URL", async () => {
    composioApi.getComposioStatus.mockResolvedValue({
      configured: true,
      oauth_callback_ready: false,
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

  it("directs a user without a key to Providers to configure their own key", async () => {
    composioApi.getComposioStatus.mockResolvedValue({
      configured: false,
      oauth_callback_ready: false,
    });

    render(
      <MCPComposioPanel
        connectedProviderSlugs={[]}
        connectingProviderSlugs={[]}
        onConnected={vi.fn()}
      />,
    );

    expect(
      await screen.findByRole("heading", { name: "Add your Composio key to browse apps" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Providers → MCP" })).toHaveAttribute(
      "href",
      "/dashboard/settings/providers?tab=mcp",
    );
    expect(screen.queryByLabelText("Your Composio project API key")).not.toBeInTheDocument();
    expect(screen.queryByText(/allowlisted platform administrator/i)).not.toBeInTheDocument();
  });

  it("lets a user start OAuth with their own key without admin callback setup", async () => {
    render(
      <MCPComposioPanel
        connectedProviderSlugs={[]}
        connectingProviderSlugs={[]}
        onConnected={vi.fn()}
      />,
    );

    expect(await screen.findByRole("button", { name: "Connect" })).toBeEnabled();
    expect(screen.queryByText(/callback verifier/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/platform composio project key/i)).not.toBeInTheDocument();
  });
});
