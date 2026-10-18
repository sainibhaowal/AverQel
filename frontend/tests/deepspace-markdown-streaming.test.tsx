import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import DeepSpaceMarkdownRenderer from "../app/dashboard/deepspace/_components/DeepSpaceMarkdownRenderer";
import DeepSpaceRichContent from "../app/dashboard/deepspace/_components/DeepSpaceRichContent";
import { ThemeProvider } from "../app/context/ThemeContext";
import type { StructuredBlock } from "../app/dashboard/deepspace/_lib/deepspace-stream";

describe("DeepSpace markdown streaming", () => {
  it("renders headings and emphasis before the response finishes", () => {
    render(
      <DeepSpaceMarkdownRenderer
        streaming
        content={"## Live heading\n\nThis is **already visible** while tokens are arriving."}
      />,
    );

    expect(screen.getByText("Live heading").tagName.toLowerCase()).toBe("h2");
    expect(screen.getByText("already visible").tagName.toLowerCase()).toBe("strong");
  });

  it("gives Mermaid export options a visible hover and keyboard-focus state", async () => {
    render(<DeepSpaceMarkdownRenderer content={"```mermaid\nflowchart LR\nA --> B\n```"} />, {
      wrapper: ThemeProvider,
    });

    fireEvent.click(await screen.findByRole("button", { name: "Export Mermaid diagram" }));

    for (const label of ["Mermaid (.mmd)", "SVG", "PNG", "PDF"]) {
      expect(screen.getByRole("button", { name: label })).toHaveClass(
        "enabled:hover:bg-primary/10",
        "enabled:hover:text-primary",
        "focus-visible:ring-2",
        "transition-colors",
      );
    }
  });

  it("offers a rounded-square save action for Mermaid diagram artifacts", async () => {
    const onSaveVisualArtifact = vi.fn().mockResolvedValue(undefined);
    render(
      <DeepSpaceMarkdownRenderer
        content={"```mermaid\nflowchart LR\nA --> B\n```"}
        messageId="mermaid-message"
        onSaveVisualArtifact={onSaveVisualArtifact}
      />,
      { wrapper: ThemeProvider },
    );

    const saveButton = screen.getByRole("button", { name: "Save diagram artifact" });
    expect(saveButton).toHaveClass("visual-export-action");
    fireEvent.click(saveButton);

    await waitFor(() => expect(onSaveVisualArtifact).toHaveBeenCalledOnce());
    expect(onSaveVisualArtifact).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "diagram",
        block_id: expect.stringMatching(/^deepspace-mermaid-/),
        source: "mermaid",
        source_mermaid: "flowchart LR\nA --> B",
        source_markdown: "```mermaid\nflowchart LR\nA --> B\n```",
        schema_version: 1,
        revision: 0,
      }),
    );
    await waitFor(() => expect(saveButton).toHaveTextContent("Saved"));
  });

  it("shows Mermaid artifact save failures inline", async () => {
    const onSaveVisualArtifact = vi.fn().mockRejectedValue(new Error("Library is unavailable."));
    render(
      <DeepSpaceMarkdownRenderer
        content={"```mermaid\nflowchart LR\nA --> B\n```"}
        onSaveVisualArtifact={onSaveVisualArtifact}
      />,
      { wrapper: ThemeProvider },
    );

    fireEvent.click(screen.getByRole("button", { name: "Save diagram artifact" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Library is unavailable.");
  });

  it("keeps the Save artifact action on structured Mermaid diagram export controls", async () => {
    const onSaveVisualArtifact = vi.fn().mockResolvedValue(undefined);
    const diagram: StructuredBlock = {
      id: "saved-mermaid-diagram",
      type: "diagram",
      title: "Service flow",
      diagram_type: "mermaid_flowchart",
      source: "mermaid",
      syntax: "flowchart LR\nAPI --> Database",
    };
    render(<DeepSpaceRichContent blocks={[diagram]} onSaveVisualArtifact={onSaveVisualArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: "Save diagram artifact" }));

    await waitFor(() => expect(onSaveVisualArtifact).toHaveBeenCalledWith(diagram));
  });

  it("renders streamed table rows instead of waiting for completion", () => {
    render(
      <DeepSpaceMarkdownRenderer
        streaming
        content={"| Name | Score |\n| --- | --- |\n| Alpha | 92 |\n| Beta | 88 |"}
      />,
    );

    expect(screen.getByText("Name").tagName.toLowerCase()).toBe("th");
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("renders compact provider tables as a real table while streaming", () => {
    render(
      <DeepSpaceMarkdownRenderer
        streaming
        content={
          "| Game | Release | Genre | |------|---------| | **Avowed** | Feb 18, 2025 | RPG (Game Pass) | | **Monster Hunter Wilds** | Feb 28, 2025 | Action |"
        }
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Avowed")).toBeInTheDocument();
    expect(screen.getByText("Monster Hunter Wilds")).toBeInTheDocument();
  });

  it("saves a Markdown table to Library as an editable visual artifact", async () => {
    const onSaveVisualArtifact = vi.fn().mockResolvedValue(undefined);
    render(
      <DeepSpaceMarkdownRenderer
        messageId="message-1"
        onSaveVisualArtifact={onSaveVisualArtifact}
        content={"| Name | Score |\n| --- | --- |\n| Alpha | 92 |"}
      />,
    );

    expect(screen.getByRole("button", { name: "Copy table" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export table" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Save table to Library" }));

    await waitFor(() =>
      expect(onSaveVisualArtifact).toHaveBeenCalledWith(
        expect.objectContaining({
          id: expect.stringMatching(/^deepspace-table-message-1-/),
          type: "table",
          title: "Markdown table",
          headers: ["Name", "Score"],
          rows: [["Alpha", "92"]],
        }),
      ),
    );
  });

  it("saves a structured chat table to Library using its canonical block", async () => {
    const onSaveVisualArtifact = vi.fn().mockResolvedValue(undefined);
    const block = {
      id: "chat-table-1",
      type: "table" as const,
      title: "Scores",
      headers: ["Name", "Score"],
      rows: [["Alpha", "92"]],
    };
    render(<DeepSpaceRichContent blocks={[block]} onSaveVisualArtifact={onSaveVisualArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: "Save table to Library" }));

    await waitFor(() => expect(onSaveVisualArtifact).toHaveBeenCalledWith(block));
  });

  it("renders compact science comparison tables after history reload", () => {
    render(
      <DeepSpaceMarkdownRenderer
        streaming={false}
        content={
          "| Feature | Positron + Electron | Antiproton + Proton | |--------------------|--------------------| | Complexity | Simple — both are fundamental | Complex — both are composite | | Products | Clean: 2 gamma rays | Messy: pions, kaons, gamma rays | | Energy | 1.022 MeV total | ~1.88 GeV total | | Real-world use | PET scans (medical imaging) | Cancer therapy research, physics experiments |"
        }
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Positron + Electron")).toBeInTheDocument();
    expect(screen.getByText("Cancer therapy research, physics experiments")).toBeInTheDocument();
  });

  it("recovers provider tables with a short separator and joined rows", () => {
    render(
      <DeepSpaceMarkdownRenderer
        streaming={false}
        content={
          "| Application | Status | Impact | |-------------|--------|\n| **PET Imaging** | ✅ Widely used | Detects cancer, Alzheimer's, heart disease | | **Antiproton Therapy** | 🔬 Experimental | Potentially 4-5x more effective than protons | | **Targeted Radionuclides** | 🔬 Research | Next-gen cancer treatments | | **FLASH Therapy** | 🏥 Clinical trials | Ultra-precise radiation delivery |"
        }
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("PET Imaging")).toBeInTheDocument();
    expect(screen.getByText("FLASH Therapy")).toBeInTheDocument();
  });

  it("renders completed Markdown structure immediately as live content changes", () => {
    const view = render(
      <DeepSpaceMarkdownRenderer content="Recent AI developments." streaming={true} />,
    );

    view.rerender(
      <DeepSpaceMarkdownRenderer
        content={"Recent AI developments.\n\n### Major research\n\n- **Robotics:** New capability."}
        streaming={true}
      />,
    );

    expect(screen.getByRole("heading", { name: "Major research" })).toBeInTheDocument();
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getByText("Robotics:")).toBeInTheDocument();
  });

  it("repairs a heading boundary as soon as its trailing whitespace arrives", () => {
    const view = render(<DeepSpaceMarkdownRenderer content="Summary.###" streaming={true} />);

    view.rerender(
      <DeepSpaceMarkdownRenderer content="Summary.### Live heading" streaming={true} />,
    );

    expect(screen.getByText("Summary.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Live heading" })).toBeInTheDocument();
  });

  it("keeps internal-thinking sections in one ordered list across detail bullets", () => {
    const { container } = render(
      <DeepSpaceMarkdownRenderer
        compact
        streaming
        content={
          "1. Analyze User Input:\n• First detail\n• Second detail\n1. Identify My Capabilities:\n• Third detail\n1. Formulate Response:\n• Final detail"
        }
      />,
    );

    expect(container.querySelectorAll("ol")).toHaveLength(1);
    expect(container.querySelector("ol")?.children).toHaveLength(3);
    expect(container.querySelectorAll("ol > li > ul")).toHaveLength(3);
  });

  it("treats currency and narrow non-breaking spaces as text, not inline LaTeX", () => {
    render(
      <DeepSpaceMarkdownRenderer
        content={"Voice sessions cost $0.05 / min. Premium input costs $5\u202f/\u202fM tokens."}
      />,
    );

    expect(screen.getByText(/Voice sessions cost \$0\.05/)).toBeInTheDocument();
    expect(screen.getByText(/Premium input costs \$5/)).toBeInTheDocument();
  });

  it("promotes chart fences into an editable visual chart", () => {
    render(
      <DeepSpaceMarkdownRenderer
        content={`\`\`\`chart
{"title":"Quarterly revenue","chart_type":"line","equation":"y = mx + b","series":[{"label":"Q1","value":12},{"label":"Q2","value":19},{"label":"Q3","value":26}]}
\`\`\``}
      />,
    );

    expect(screen.getByText("Quarterly revenue")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit data" })).toBeInTheDocument();
    expect(screen.getByText("Equation")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download chart data" })).toBeInTheDocument();
  });

  it.each(["json", ""])("renders chart JSON from a %s fence", (language) => {
    const fence = String.fromCharCode(96).repeat(3);
    const payload = {
      title: "y = 2x + 1",
      chart_type: "line",
      equation: "y = 2x + 1",
      x_label: "x",
      y_label: "y",
      series: Array.from({ length: 21 }, (_, x) => ({ label: String(x), value: 2 * x + 1 })),
    };
    const view = render(
      <DeepSpaceMarkdownRenderer
        content={`${fence}${language}\n${JSON.stringify(payload, null, 2)}\n${fence}`}
      />,
    );

    expect(screen.getByRole("heading", { name: "y = 2x + 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit data" })).toBeInTheDocument();
    expect(screen.getByText("Equation")).toBeInTheDocument();
    expect(screen.queryByText(/\"chart_type\": \"line\"/)).not.toBeInTheDocument();
    expect(view.container.querySelector('[data-axis-label="x"]')).toHaveTextContent("x");
    expect(view.container.querySelector('[data-axis-label="y"]')).toHaveTextContent("y");
  });

  it("keeps recalculated chart values in sync through save and visual re-render", async () => {
    const savedBlocks: StructuredBlock[] = [];
    const onVisualBlockChange = vi.fn((_messageId: string, block: StructuredBlock) => {
      savedBlocks.push(block);
      return true;
    });
    const onSaveVisualArtifact = vi.fn().mockResolvedValue(undefined);
    const fence = String.fromCharCode(96).repeat(3);
    const initial = {
      id: "equation-chart-1",
      type: "chart",
      title: "Equation trend",
      chart_type: "line",
      equation: "y = 2*x + 1",
      x_label: "x",
      y_label: "y",
      series: Array.from({ length: 21 }, (_, x) => ({ label: String(x), value: 2 * x + 1 })),
    };
    const renderSavedBlock = (block: object) =>
      `${fence}chart\n${JSON.stringify(block, null, 2)}\n${fence}`;
    const view = render(
      <DeepSpaceMarkdownRenderer
        messageId="assistant-chart"
        onVisualBlockChange={onVisualBlockChange}
        onSaveVisualArtifact={onSaveVisualArtifact}
        content={renderSavedBlock(initial)}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Payload" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit data" }));
    fireEvent.change(screen.getByLabelText("Live equation (x → y)"), {
      target: { value: "y = 5*x + 1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Recalculate" }));
    fireEvent.change(screen.getByRole("spinbutton", { name: "Chart point 11 value" }), {
      target: { value: "83" },
    });

    expect(screen.getByRole("img", { name: "Equation trend" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => expect(savedBlocks).toHaveLength(1));
    const savedBlock = savedBlocks[0]!;
    expect(savedBlock.type).toBe("chart");
    const savedChart = savedBlock as Extract<StructuredBlock, { type: "chart" }>;
    const savedPayload = JSON.parse(String(savedChart.raw_payload)) as {
      equation: string;
      series: Array<{ label: string; value: number }>;
    };
    expect(savedChart).toMatchObject({ equation: "y = 5*x + 1", revision: 1 });
    expect(savedChart.source_markdown).toBe(savedChart.raw_payload);
    expect(savedPayload.equation).toBe("y = 5*x + 1");
    expect(savedPayload.series[10]).toEqual({ label: "10", value: 83 });
    expect(savedPayload.series[20]).toEqual({ label: "20", value: 101 });

    view.rerender(
      <DeepSpaceMarkdownRenderer
        messageId="assistant-chart"
        onVisualBlockChange={onVisualBlockChange}
        onSaveVisualArtifact={onSaveVisualArtifact}
        content={renderSavedBlock(savedChart)}
      />,
    );
    expect(screen.getByRole("img", { name: "Equation trend" })).toBeInTheDocument();
    expect(view.container.querySelector("pre")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Save chart artifact" }));
    await waitFor(() => expect(onSaveVisualArtifact).toHaveBeenCalledTimes(1));
    expect(onSaveVisualArtifact).toHaveBeenCalledWith(
      expect.objectContaining({
        equation: "y = 5*x + 1",
        series: expect.arrayContaining([expect.objectContaining({ label: "10", value: 83 })]),
      }),
    );
  });

  it("keeps chart edits open when saving the revision fails", async () => {
    const onVisualBlockChange = vi.fn().mockResolvedValue(false);
    render(
      <DeepSpaceMarkdownRenderer
        messageId="assistant-chart-failure"
        onVisualBlockChange={onVisualBlockChange}
        content={`\`\`\`chart
{"title":"Retry chart","chart_type":"line","series":[{"label":"A","value":1},{"label":"B","value":2}]}
\`\`\``}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit data" }));
    fireEvent.change(screen.getByRole("spinbutton", { name: "Chart point 1 value" }), {
      target: { value: "9" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Chart changes could not be saved. Try again.",
    );
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
  });

  it("returns to the chart when the equation is cleared", () => {
    render(
      <DeepSpaceMarkdownRenderer
        content={`\`\`\`chart
{"title":"Equation trend","chart_type":"line","equation":"y = 2*x + 1","series":[{"label":"0","value":1},{"label":"1","value":3}]}
\`\`\``}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Payload" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit data" }));
    fireEvent.change(screen.getByLabelText("Live equation (x → y)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Recalculate" }));

    expect(screen.getByRole("img", { name: "Equation trend" })).toBeInTheDocument();
    expect(screen.queryByText("Raw payload")).not.toBeInTheDocument();
  });

  it("renders card fences as actionable information cards", () => {
    render(
      <DeepSpaceMarkdownRenderer
        content={`\`\`\`card
{"title":"Decision brief","tone":"success","content":"**Ship** the verified workflow.","metrics":[{"label":"Confidence","value":"92%"}],"actions":[{"label":"Open evidence","href":"https://example.com"}]}
\`\`\``}
      />,
    );

    expect(screen.getByText("Decision brief")).toBeInTheDocument();
    expect(screen.getByText("Ship")).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open evidence/ })).toHaveAttribute(
      "href",
      "https://example.com/",
    );
  });

  it("renders screenshot-style KPI cards with model tone aliases", () => {
    const fence = String.fromCharCode(96).repeat(3);
    const view = render(
      <DeepSpaceMarkdownRenderer
        content={`${fence}card
{"title":"Revenue","subtitle":"Illustrative figure","tone":"positive","metrics":[{"label":"Revenue","value":"$4.0M"},{"label":"Growth","value":"+8.2% MoM"}],"content":"**Trend: up 8.2% — improving.**\\nRevenue reached **$4.0M** for the period."}
${fence}

${fence}card
{"title":"Quota Attainment","subtitle":"Illustrative figure","tone":"caution","metrics":[{"label":"Quota attainment","value":"96%"},{"label":"Change","value":"-1 pt"}],"content":"Slightly below target."}
${fence}`}
      />,
    );

    expect(screen.getByRole("heading", { name: "Revenue" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Quota Attainment" })).toBeInTheDocument();
    expect(screen.getAllByText("$4.0M")).toHaveLength(2);
    expect(screen.getByText("+8.2% MoM")).toBeInTheDocument();
    expect(screen.getByText("Trend: up 8.2% — improving.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Revenue" }).closest("article")).toHaveClass(
      "bg-emerald-400/[0.07]",
    );
    expect(
      screen.getByRole("heading", { name: "Quota Attainment" }).closest("article"),
    ).toHaveClass("bg-amber-400/[0.07]");
    expect(screen.queryByText(/"title":"Revenue"/)).not.toBeInTheDocument();
    expect(view.container.querySelector("pre")).toBeNull();
  });

  it("promotes generic JSON visual payloads and persisted rich-content fences", () => {
    const fence = String.fromCharCode(96).repeat(3);
    render(
      <DeepSpaceMarkdownRenderer
        content={`${fence}json
{"title":"KPI card","content":"Verified","metrics":[{"label":"Confidence","value":"94%"}]}
${fence}

<pre data-rich-content-kind="chart" data-rich-content-source="{&quot;title&quot;:&quot;Saved chart&quot;,&quot;chart_type&quot;:&quot;line&quot;,&quot;series&quot;:[{&quot;label&quot;:&quot;A&quot;,&quot;value&quot;:1},{&quot;label&quot;:&quot;B&quot;,&quot;value&quot;:2}]}"><code>${fence}chart
{"title":"Saved chart","chart_type":"line","series":[{"label":"A","value":1},{"label":"B","value":2}]}
${fence}</code></pre>`}
      />,
    );

    expect(screen.getByText("KPI card")).toBeInTheDocument();
    expect(screen.getByText("Saved chart")).toBeInTheDocument();
  });

  it("renders an editable graph canvas and its interaction toolbar", () => {
    render(
      <DeepSpaceMarkdownRenderer
        content={`\`\`\`graph
{"title":"Release flow","layout":"horizontal","nodes":[{"id":"a","label":"Build","x":160,"y":180},{"id":"b","label":"Ship","x":520,"y":180}],"edges":[{"source":"a","target":"b","label":"ready"}]}
\`\`\``}
      />,
    );

    expect(screen.getByRole("img", { name: "Release flow" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit canvas" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download diagram JSON" })).toBeInTheDocument();
  });

  it("renders a downloadable image sequence from a gallery fence", () => {
    render(
      <DeepSpaceMarkdownRenderer
        content={`\`\`\`gallery
{"title":"Research slides","items":[{"src":"https://example.com/one.png","alt":"One","caption":"First"},{"src":"https://example.com/two.png","alt":"Two"}]}
\`\`\``}
      />,
    );

    expect(screen.getByRole("img", { name: "One" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next image" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download image" })).toBeInTheDocument();
  });

  it("edits gallery fields and sends the revisioned block to chat persistence", async () => {
    const onVisualBlockChange = vi.fn().mockResolvedValue(undefined);
    render(
      <DeepSpaceMarkdownRenderer
        messageId="assistant-gallery"
        onVisualBlockChange={onVisualBlockChange}
        content={`\`\`\`gallery
{"title":"Research slides","items":[{"src":"https://example.com/one.png","alt":"One","caption":"First"}]}
\`\`\``}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit gallery" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Gallery title" }), {
      target: { value: "Updated research slides" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Gallery image 1 caption" }), {
      target: { value: "Updated caption" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save gallery" }));

    await waitFor(() => expect(onVisualBlockChange).toHaveBeenCalledTimes(1));
    expect(onVisualBlockChange).toHaveBeenCalledWith(
      "assistant-gallery",
      expect.objectContaining({
        type: "gallery",
        title: "Updated research slides",
        revision: 1,
        items: [expect.objectContaining({ caption: "Updated caption" })],
      }),
    );
  });
});
