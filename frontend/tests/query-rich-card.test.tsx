import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import MarkdownRenderer from "../app/dashboard/query/_components/MarkdownRenderer";
import StructuredBlockRenderer from "../app/dashboard/query/_components/StructuredBlockRenderer";

it("renders structured information cards with safe actions and theme-aware contrast", () => {
  const { container } = render(
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
  expect(container.querySelector('[data-card-layout="standard"]')).toHaveClass(
    "border-glass-border",
    "bg-surface-0",
    "dark:bg-surface-1",
  );
  expect(screen.getByText("verified")).toBeInTheDocument();
  expect(screen.getByText("96%")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Open source/ })).toHaveAttribute(
    "href",
    "https://example.com/",
  );
});

it("renders a sourced place card with a large photo, details, icon, source, and theme contrast", () => {
  const { container } = render(
    <StructuredBlockRenderer
      blocks={[
        {
          id: "place-1",
          type: "card",
          layout: "place",
          title: "Welcome Center Berlin",
          content: "Visitor information.",
          image_url: "https://example.com/place.jpg",
          image_alt: "Welcome Center entrance",
          details: [
            {
              label: "Address",
              value:
                "Flughafen Berlin Brandenburg, Willy-Brandt-Platz 1, 12529 Schönefeld (Terminal 1, Level E0)",
              icon: "map-pin",
            },
            { label: "Hours (Mon–Tue)", value: "8:00–21:00", icon: "clock" },
            { label: "Hours (Wed–Sun)", value: "8:00–20:00", icon: "clock" },
            { label: "Email", value: "hello@example.com" },
          ],
          sources: [{ title: "Official visitor page", url: "https://example.com/visit" }],
        },
      ]}
    />,
  );

  expect(screen.getByRole("heading", { name: "Welcome Center Berlin" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Welcome Center entrance" })).toHaveClass("h-24", "w-24");
  expect(screen.getByText(/Flughafen Berlin Brandenburg/)).toBeInTheDocument();
  expect(container.querySelector('[data-card-layout="place"]')).toHaveClass(
    "bg-surface-0",
    "dark:bg-surface-1",
  );
  expect(container.querySelector('[data-card-layout="place"] dl > div')).toHaveClass(
    "bg-surface-1",
    "dark:bg-surface-2",
    "border-glass-border",
    "min-h-20",
  );
  expect(container.querySelector('[data-card-layout="place"] dl')).toHaveClass(
    "auto-rows-fr",
    "sm:grid-cols-2",
  );
  expect(container.querySelectorAll('[data-card-layout="place"] dl > div')).toHaveLength(4);
  const detailIconBadges = container.querySelectorAll<HTMLElement>("[data-card-detail-icon]");
  expect(detailIconBadges).toHaveLength(4);
  expect(detailIconBadges[0]).toHaveClass(
    "bg-surface-1",
    "dark:bg-surface-2",
    "text-foreground",
    "rounded-xl",
  );
  expect(detailIconBadges[3]).toHaveClass("border-glass-border", "bg-surface-1");
  expect(Array.from(detailIconBadges).every((badge) => badge.querySelector("svg"))).toBe(true);
  expect(container.querySelector('[data-card-layout="place"]')?.className).not.toMatch(
    /violet|emerald|amber|rose|orange|slate|cyan|sky/,
  );
  expect(screen.getByRole("link", { name: "Official visitor page" })).toHaveAttribute(
    "href",
    "https://example.com/visit",
  );
});

it("renders an evaluation card with an accessible score bar and aligned test metrics", () => {
  render(
    <StructuredBlockRenderer
      blocks={[
        {
          id: "evaluation-card",
          type: "card",
          layout: "evaluation",
          title: "API evaluation",
          subtitle: "Tests from August 17 to September 21, 2026",
          content: "Source: publicly reported testing results.",
          score: { value: 51, max: 100, tone: "error" },
          metrics: [
            { label: "Valid scored tests", value: 15 },
            { label: "Claude signature checks passed", value: "0/10" },
          ],
          sources: [{ title: "Veridrop", url: "https://example.com/veridrop" }],
        },
      ]}
    />,
  );

  expect(screen.getByRole("heading", { name: "API evaluation" })).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "API evaluation score" })).toHaveAttribute(
    "aria-valuenow",
    "51",
  );
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "51 out of 100");
  expect(screen.getByText("51/100")).toBeInTheDocument();
  expect(screen.getByText("Valid scored tests")).toBeInTheDocument();
  expect(screen.getByText("Claude signature checks passed")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Veridrop" })).toHaveAttribute(
    "href",
    "https://example.com/veridrop",
  );
});

it("renders referral terms as aligned rows and lets the user copy the code", async () => {
  const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });

  try {
    render(
      <StructuredBlockRenderer
        blocks={[
          {
            id: "referral-card",
            type: "card",
            layout: "referral",
            title: "Referral terms",
            code: "81D9-627A-11",
            primary_metric: { label: "Gift tokens advertised", value: "10,000,000" },
            details: [
              { label: "Free cash", value: "No" },
              { label: "Credit card required initially", value: "No, according to site" },
              { label: "Inviter's commission", value: "5% first top-up, 2% later" },
              { label: "Gift-token restrictions", value: "Three specified models" },
            ],
            content: "Terms are published by the provider, not independently verified benefits.",
            sources: [{ title: "LarpRouter", url: "https://example.com/referral" }],
          },
        ]}
      />,
    );

    expect(screen.getByText("10,000,000")).toBeInTheDocument();
    expect(screen.getByText("Gift tokens advertised")).toBeInTheDocument();
    expect(screen.getByText("Three specified models")).toBeInTheDocument();
    expect(screen.getAllByTestId("referral-card-detail")).toHaveLength(4);
    expect(screen.getByText(/not independently verified benefits/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "LarpRouter" })).toHaveAttribute(
      "href",
      "https://example.com/referral",
    );

    fireEvent.click(screen.getByRole("button", { name: "Copy referral code" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("81D9-627A-11"));
    expect(await screen.findByRole("button", { name: "Referral code copied" })).toBeInTheDocument();
  } finally {
    if (originalClipboard) {
      Object.defineProperty(navigator, "clipboard", originalClipboard);
    } else {
      Reflect.deleteProperty(navigator, "clipboard");
    }
  }
});

it("promotes card fences with evaluation and referral layouts in Query markdown", () => {
  const fence = String.fromCharCode(96).repeat(3);
  const evaluation = {
    title: "Evaluation from Markdown",
    layout: "evaluation",
    score: { value: 51, max: 100, tone: "error" },
    metrics: [{ label: "Valid tests", value: 15 }],
  };
  const referral = {
    title: "Referral from Markdown",
    layout: "referral",
    primary_metric: { label: "Tokens", value: "10,000,000" },
    details: [{ label: "Cash", value: "No" }],
  };

  render(
    <MarkdownRenderer
      content={
        fence +
        "card\n" +
        JSON.stringify(evaluation) +
        "\n" +
        fence +
        "\n\n" +
        fence +
        "card\n" +
        JSON.stringify(referral) +
        "\n" +
        fence
      }
    />,
  );

  expect(screen.getByRole("progressbar", { name: "Evaluation from Markdown score" })).toHaveAttribute(
    "aria-valuenow",
    "51",
  );
  expect(screen.getByRole("heading", { name: "Referral from Markdown" })).toBeInTheDocument();
  expect(screen.getByText("10,000,000")).toBeInTheDocument();
});

it("shows a visible error when card content cannot be copied", async () => {
  const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockRejectedValue(new Error("Clipboard access was denied.")) },
  });

  try {
    render(
      <StructuredBlockRenderer
        blocks={[
          {
            id: "copy-error-card",
            type: "card",
            title: "Copy error card",
            content: "Private card text.",
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Copy card content" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Clipboard access was denied.");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Copy card content" })).toBeEnabled(),
    );
  } finally {
    if (originalClipboard) {
      Object.defineProperty(navigator, "clipboard", originalClipboard);
    } else {
      Reflect.deleteProperty(navigator, "clipboard");
    }
  }
});
