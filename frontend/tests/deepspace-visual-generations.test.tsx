import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "../app/context/ThemeContext";
import DeepSpaceMarkdownRenderer from "../app/dashboard/deepspace/_components/DeepSpaceMarkdownRenderer";
import DeepSpaceVisualArtifactWorkspace from "../app/dashboard/deepspace/_components/DeepSpaceVisualArtifactWorkspace";
import type { StructuredBlock } from "../app/dashboard/deepspace/_lib/deepspace-stream";
import { repairMismatchedVisualFences } from "../app/dashboard/query/_lib/visual-fences";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    parse: vi.fn(async () => true),
    render: vi.fn(async (_id: string, source: string) => ({
      svg: `<svg><text>${source}</text></svg>`,
    })),
  },
}));

const fence = String.fromCharCode(96).repeat(3);

describe("DeepSpace visual response formats", () => {
  it("recovers a visual JSON block when its outer code fence is longer than its closing fence", () => {
    const payload = {
      title: "Deploy a local AI model",
      layout: "steps",
      items: [
        {
          title: "Check hardware",
          description: "Match model size to available memory.",
          icon: "zap",
        },
        { title: "Install runtime", description: "Choose a local inference engine.", icon: "code" },
      ],
    };
    const longFence = `${fence}${String.fromCharCode(96)}`;
    const content = `${longFence}json\n${JSON.stringify(payload, null, 2)}\n${fence}\n\nQuick summary follows.`;

    render(<DeepSpaceMarkdownRenderer content={content} streaming />);

    expect(screen.getByRole("heading", { name: "Deploy a local AI model" })).toBeInTheDocument();
    expect(screen.getByText("Match model size to available memory.")).toBeInTheDocument();
    expect(screen.getByText("Quick summary follows.")).toBeInTheDocument();
    expect(screen.queryByText(/"layout": "steps"/)).not.toBeInTheDocument();
  });

  it("recovers a sourced place card from a mismatched JSON fence", () => {
    const payload = {
      title: "Berlin Welcome Center",
      content: "Visitor information at the airport.",
      layout: "place",
      details: ["**Hours:** 08:00–20:00"],
      sources: [{ label: "Official visitor page", href: "https://example.com/visit" }],
    };
    const longFence = `${fence}${String.fromCharCode(96)}`;
    const content = `${longFence}json\n${JSON.stringify(payload, null, 2)}\n${fence}`;

    render(<DeepSpaceMarkdownRenderer content={content} />);

    expect(screen.getByRole("heading", { name: "Berlin Welcome Center" })).toBeInTheDocument();
    expect(screen.getByText("08:00–20:00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Official visitor page" })).toHaveAttribute(
      "href",
      "https://example.com/visit",
    );
  });

  it("recovers the indented mixed-fence place response with its image, details, and research notes", () => {
    const payload = {
      title: "Berlin Brandenburg WelcomeCenter",
      subtitle: "Official tourist information at BER Airport (visitBerlin)",
      content: "The first point of contact for visitors arriving at the airport.",
      layout: "place",
      image_url: "https://example.com/welcome-center.jpg",
      image_alt: "Welcome Center service counter",
      details: ["**Address:** Willy-Brandt-Platz 1, Berlin", "**Hours:** 08:00–20:00"],
      actions: [{ label: "Official page", href: "https://example.com/visit" }],
      sources: [{ label: "Official visitor page", href: "https://example.com/visit" }],
    };
    const visualFence = `${String.fromCharCode(96).repeat(3)}json`;
    const content = `    ~~~~json\n${JSON.stringify(payload, null, 2)}\n${visualFence}\n\n**Research notes:**\n- The official page was read in full.\n\n### Sources\n[R1](https://example.com/visit)\n~~~`;

    expect(repairMismatchedVisualFences(content)).toContain("**Research notes:**");
    const { container } = render(<DeepSpaceMarkdownRenderer content={content} streaming />);

    expect(
      screen.getByRole("heading", { name: "Berlin Brandenburg WelcomeCenter" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Welcome Center service counter" })).toBeInTheDocument();
    expect(screen.getByText("Willy-Brandt-Platz 1, Berlin")).toBeInTheDocument();
    expect(screen.getByText("08:00–20:00")).toBeInTheDocument();
    expect(container.textContent).toContain("Research notes:");
    expect(container.textContent).toContain("The official page was read in full.");
    expect(screen.getByRole("link", { name: "Official visitor page" })).toHaveAttribute(
      "href",
      "https://example.com/visit",
    );
    expect(screen.queryByText(/"layout": "place"/)).not.toBeInTheDocument();
  });

  it("renders an infographic and saves edits as a new visual revision", async () => {
    const onVisualBlockChange = vi.fn().mockResolvedValue(true);
    const payload = {
      id: "process-1",
      type: "infographic",
      title: "From question to answer",
      subtitle: "A concise four-step workflow.",
      layout: "steps",
      items: [
        { title: "Research", description: "Gather source evidence.", icon: "lightbulb" },
        { title: "Synthesize", description: "Check agreement and gaps.", icon: "layers" },
      ],
      sources: [{ title: "Research method", url: "https://example.com/research" }],
    };
    const { container } = render(
      <DeepSpaceMarkdownRenderer
        messageId="assistant-1"
        content={`${fence}infographic\n${JSON.stringify(payload)}\n${fence}`}
        onVisualBlockChange={onVisualBlockChange}
      />,
    );

    expect(screen.getByRole("heading", { name: "From question to answer" })).toBeInTheDocument();
    expect(screen.getByText("Gather source evidence.")).toBeInTheDocument();
    expect(container.querySelector('[aria-label="Process infographic"]')).toHaveClass(
      "border-glass-border",
      "bg-surface-0",
      "dark:bg-surface-1",
    );
    expect(container.querySelector('[aria-label="Process infographic"] li')).toHaveClass(
      "border-glass-border",
      "bg-surface-0",
      "dark:bg-surface-1",
    );
    expect(screen.getByText("Gather source evidence.")).toHaveClass(
      "text-foreground/80",
      "dark:text-foreground/70",
    );
    expect(screen.getByRole("link", { name: "Research method" })).toHaveAttribute(
      "href",
      "https://example.com/research",
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit infographic" }));
    const editor = screen.getByRole("textbox", { name: "Edit infographic fields as JSON" });
    const updated = {
      ...payload,
      revision: 0,
      items: [payload.items[0], { ...payload.items[1], title: "Synthesize carefully" }],
    };
    fireEvent.change(editor, { target: { value: JSON.stringify(updated, null, 2) } });
    fireEvent.click(screen.getByRole("button", { name: "Save infographic" }));

    await waitFor(() => expect(onVisualBlockChange).toHaveBeenCalledOnce());
    expect(onVisualBlockChange).toHaveBeenCalledWith(
      "assistant-1",
      expect.objectContaining({
        id: "process-1",
        type: "infographic",
        revision: 1,
        items: expect.arrayContaining([expect.objectContaining({ title: "Synthesize carefully" })]),
      }),
    );
  });

  it("keeps bottom-to-top process direction visible without changing item data order", () => {
    const payload = {
      title: "Publish a release",
      layout: "steps",
      direction: "DT",
      items: [
        { title: "Prepare", description: "Confirm the build and checks." },
        { title: "Publish", description: "Make the package available." },
      ],
    };
    const { container } = render(
      <DeepSpaceMarkdownRenderer
        content={`${fence}infographic\n${JSON.stringify(payload)}\n${fence}`}
      />,
    );
    const list = container.querySelector("ol[data-flow-direction]");

    expect(list).toHaveAttribute("data-flow-direction", "DT");
    expect(list).toHaveClass("flex-col-reverse");
    expect(
      Array.from(list?.querySelectorAll("li h4") ?? []).map((heading) => heading.textContent),
    ).toEqual(["Prepare", "Publish"]);
  });

  it("renders a completed infographic before the rest of the answer finishes streaming", () => {
    const payload = {
      title: "Deploy a local AI model",
      layout: "steps",
      items: [
        {
          title: "Choose a model",
          description: "Match it to the available hardware.",
          icon: "database",
        },
        { title: "Install a runtime", description: "Set up an inference engine.", icon: "code" },
      ],
    };
    const unfinishedContent = `${fence}infographic\n${JSON.stringify(payload, null, 2)}`;
    const { rerender } = render(
      <DeepSpaceMarkdownRenderer content={unfinishedContent} streaming />,
    );
    expect(
      screen.queryByRole("heading", { name: "Deploy a local AI model" }),
    ).not.toBeInTheDocument();

    rerender(
      <DeepSpaceMarkdownRenderer
        content={`${unfinishedContent}\n${fence}\n\nNext, verify the endpoint.`}
        streaming
      />,
    );

    expect(screen.getByRole("heading", { name: "Deploy a local AI model" })).toBeInTheDocument();
    expect(screen.getByText("Next, verify the endpoint.")).toBeInTheDocument();
    expect(screen.queryByText(/"layout": "steps"/)).not.toBeInTheDocument();
  });

  it("renders a completed researched place card while the answer continues streaming", () => {
    const payload = {
      title: "Welcome Center Berlin",
      content: "Official visitor information at the airport.",
      layout: "place",
      image_url: "https://example.com/welcome-center.jpg",
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
        { label: "Email", value: "hello@example.com", icon: "info" },
      ],
      sources: [{ title: "Official visitor page", url: "https://example.com/visit" }],
    };
    const { container } = render(
      <DeepSpaceMarkdownRenderer
        content={`${fence}card\n${JSON.stringify(payload, null, 2)}\n${fence}\n\nMore details follow.`}
        streaming
      />,
    );

    expect(screen.getByRole("heading", { name: "Welcome Center Berlin" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Welcome Center entrance" })).toBeInTheDocument();
    expect(screen.getByText(/Flughafen Berlin Brandenburg/)).toBeInTheDocument();
    expect(container.querySelector('[data-card-layout="place"] dl')).toHaveClass(
      "auto-rows-fr",
      "sm:grid-cols-2",
    );
    expect(container.querySelectorAll('[data-card-layout="place"] dl > div')).toHaveLength(4);
    expect(screen.getByRole("link", { name: "Official visitor page" })).toHaveAttribute(
      "href",
      "https://example.com/visit",
    );
    expect(screen.getByText("More details follow.")).toBeInTheDocument();
  });

  it("keeps an unfinished visual fence as code until its closing marker arrives", () => {
    const payload = {
      title: "Deploy a local AI model",
      layout: "steps",
      items: [{ title: "Choose a model" }, { title: "Install a runtime" }],
    };
    render(
      <DeepSpaceMarkdownRenderer
        content={`${fence}infographic\n${JSON.stringify(payload, null, 2)}`}
        streaming
      />,
    );

    expect(
      screen.queryByRole("heading", { name: "Deploy a local AI model" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/"layout": "steps"/)).toBeInTheDocument();
  });

  it("renders a completed Mermaid diagram while later answer text streams", async () => {
    const { container } = render(
      <DeepSpaceMarkdownRenderer
        content={`${fence}mermaid\nflowchart LR\nA[Client] --> B[Gateway]\n${fence}\n\nThe diagram is complete.`}
        streaming
      />,
      { wrapper: ThemeProvider },
    );

    await waitFor(() =>
      expect(container.querySelector("svg text")).toHaveTextContent("flowchart LR"),
    );
    expect(screen.getByText("The diagram is complete.")).toBeInTheDocument();
  });

  it("repairs a two-backtick Mermaid close so following Markdown renders normally", async () => {
    const shortClose = fence.slice(0, 2);
    const { container } = render(
      <DeepSpaceMarkdownRenderer
        content={`${fence}mermaid\nflowchart LR\nA[Input] --> B[Output]\n${shortClose}\n\n## Transformer block\nThe remaining answer is Markdown.`}
      />,
      { wrapper: ThemeProvider },
    );

    await waitFor(() =>
      expect(container.querySelector("svg text")).toHaveTextContent("flowchart LR"),
    );
    expect(screen.getByRole("heading", { name: "Transformer block" })).toBeInTheDocument();
    expect(screen.getByText("The remaining answer is Markdown.")).toBeInTheDocument();
  });

  it("accepts timeline labels longer than the former server limit", async () => {
    const onVisualBlockChange = vi.fn().mockResolvedValue(true);
    const payload = {
      id: "long-timeline",
      type: "infographic",
      title: "Timeline",
      layout: "timeline",
      items: [
        {
          title: "First",
          date: `Setup: ${"prepare the environment, configure access, and verify dependencies. ".repeat(2)}`,
        },
        { title: "Second", date: "Later" },
      ],
    };
    render(
      <DeepSpaceMarkdownRenderer
        messageId="assistant-timeline"
        content={`${fence}infographic\n${JSON.stringify(payload)}\n${fence}`}
        onVisualBlockChange={onVisualBlockChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit infographic" }));
    fireEvent.click(screen.getByRole("button", { name: "Save infographic" }));

    await waitFor(() => expect(onVisualBlockChange).toHaveBeenCalledOnce());
    expect(onVisualBlockChange.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({ revision: 1 }),
    );
  });

  it("saves the active infographic draft to Library after committing it", async () => {
    const onVisualBlockChange = vi.fn().mockResolvedValue(true);
    const onSaveVisualArtifact = vi.fn().mockResolvedValue(undefined);
    const payload = {
      id: "library-draft",
      type: "infographic",
      title: "Draft title",
      layout: "steps",
      items: [{ title: "Plan" }, { title: "Ship" }],
    };
    render(
      <DeepSpaceMarkdownRenderer
        messageId="assistant-library"
        content={`${fence}infographic\n${JSON.stringify(payload)}\n${fence}`}
        onVisualBlockChange={onVisualBlockChange}
        onSaveVisualArtifact={onSaveVisualArtifact}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit infographic" }));
    const editor = screen.getByRole("textbox", { name: "Edit infographic fields as JSON" });
    fireEvent.change(editor, {
      target: {
        value: JSON.stringify({ ...payload, title: "Saved draft title" }, null, 2),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save infographic to Library" }));

    await waitFor(() => expect(onVisualBlockChange).toHaveBeenCalledOnce());
    expect(onSaveVisualArtifact).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Saved draft title", revision: 1 }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Saved to Library.");
  });

  it("renders a sourced place card with the larger photo layout", () => {
    const payload = {
      id: "place-1",
      type: "card",
      layout: "place",
      title: "Welcome Center Berlin",
      content: "Visitor information.",
      image_url: "https://example.com/welcome-center.jpg",
      image_alt: "Entrance of Welcome Center Berlin",
      details: [
        { label: "Address", value: "Potsdamer Str. 61, Berlin", icon: "map-pin" },
        { label: "Hours", value: "10:00–18:00", icon: "clock" },
      ],
      sources: [{ title: "Official visitor page", url: "https://example.com/visit" }],
    };
    const { container } = render(
      <DeepSpaceMarkdownRenderer content={`${fence}card\n${JSON.stringify(payload)}\n${fence}`} />,
    );

    expect(screen.getByRole("heading", { name: "Welcome Center Berlin" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Entrance of Welcome Center Berlin" })).toHaveClass(
      "h-24",
      "w-24",
      "sm:h-32",
    );
    expect(screen.getByText("Potsdamer Str. 61, Berlin")).toBeInTheDocument();
    expect(screen.getByText("10:00–18:00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Official visitor page" })).toBeInTheDocument();
    expect(container.querySelector('[data-card-layout="place"]')).toHaveClass(
      "border-glass-border",
      "bg-surface-0",
      "dark:bg-surface-1",
    );
    expect(screen.getByRole("link", { name: "Official visitor page" })).toHaveClass(
      "text-primary",
      "decoration-primary/40",
    );
  });

  it("keeps infographic edits open and reports a rejected revision save", async () => {
    const onVisualBlockChange = vi.fn().mockResolvedValue(false);
    const payload = {
      id: "process-conflict",
      type: "infographic",
      title: "Launch process",
      layout: "steps",
      items: [{ title: "Research" }, { title: "Ship" }],
    };
    render(
      <DeepSpaceMarkdownRenderer
        messageId="assistant-conflict"
        content={`${fence}infographic\n${JSON.stringify(payload)}\n${fence}`}
        onVisualBlockChange={onVisualBlockChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit infographic" }));
    fireEvent.click(screen.getByRole("button", { name: "Save infographic" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Your draft is still open");
    expect(
      screen.getByRole("textbox", { name: "Edit infographic fields as JSON" }),
    ).toBeInTheDocument();
  });

  it("keeps incomplete timeline data in readable code instead of rendering a broken visual", () => {
    const payload = {
      title: "Incomplete timeline",
      layout: "timeline",
      items: [{ title: "First milestone" }, { title: "Second milestone" }],
    };
    render(
      <DeepSpaceMarkdownRenderer
        content={`${fence}infographic\n${JSON.stringify(payload)}\n${fence}`}
      />,
    );

    expect(screen.queryByRole("heading", { name: "Incomplete timeline" })).not.toBeInTheDocument();
    expect(screen.getByText(/First milestone/)).toBeInTheDocument();
  });

  it("reopens and revision-saves an infographic visual artifact", async () => {
    const block: StructuredBlock = {
      id: "saved-infographic",
      block_id: "saved-infographic",
      type: "infographic",
      title: "Saved process",
      layout: "steps",
      items: [{ title: "Plan" }, { title: "Deliver" }],
      revision: 3,
      schema_version: 1,
    };
    const document = {
      block_id: block.id,
      schema_version: 1,
      revision: block.revision,
      kind: block.type,
      data: block,
    };
    const onChange = vi.fn();
    const onBlockChange = vi.fn().mockResolvedValue(undefined);
    render(
      <DeepSpaceVisualArtifactWorkspace
        value={JSON.stringify(document)}
        onChange={onChange}
        onBlockChange={onBlockChange}
      />,
    );

    expect(screen.getByRole("heading", { name: "Saved process" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit infographic" }));
    const editor = screen.getByRole("textbox", { name: "Edit infographic fields as JSON" });
    fireEvent.change(editor, {
      target: { value: JSON.stringify({ ...block, title: "Revised process" }, null, 2) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save infographic" }));

    await waitFor(() => expect(onBlockChange).toHaveBeenCalledOnce());
    expect(onBlockChange).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Revised process", revision: 4 }),
    );
    expect(JSON.parse(onChange.mock.calls[0]?.[0] as string).revision).toBe(4);
  });
});
