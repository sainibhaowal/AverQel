import { render, screen, within } from "@testing-library/react";

import type { QueryThreadMessage } from "../app/dashboard/query/_lib/stream-protocol";
import RichMessageRenderer from "../app/dashboard/query/_components/RichMessageRenderer";

describe("rich message mermaid dedup", () => {
  it("suppresses structured table blocks when markdown already contains a table", () => {
    const message: QueryThreadMessage = {
      id: "assistant-table-markdown",
      role: "assistant",
      content: "## Results\n\n| Name | Score |\n| --- | --- |\n| Alpha | 92 |\n",
      rawContent: "## Results\n\n| Name | Score |\n| --- | --- |\n| Alpha | 92 |\n",
      createdAt: new Date().toISOString(),
      status: "ready",
      blocks: [
        {
          id: "table-1",
          type: "table",
          title: "Structured Results",
          headers: ["Name", "Score"],
          rows: [["Beta", "88"]],
        },
      ],
      citations: [],
      artifacts: [],
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      confidence: undefined,
      trace: null,
      traceId: undefined,
      cached: false,
      thinkingContent: "",
      structured: null,
      error: null,
      versions: [],
      versionCount: 0,
      activeVersionId: null,
      activeVersionIndex: 0,
    };

    render(
      <RichMessageRenderer
        message={message}
        isStreaming={false}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByText("Structured Results")).not.toBeInTheDocument();
    expect(screen.queryByText("Beta")).not.toBeInTheDocument();
  });

  it("renders comparison_table from structured answers when markdown has no table", () => {
    const message: QueryThreadMessage = {
      id: "assistant-comparison-table",
      role: "assistant",
      content: "## Summary\n\nComparison is ready.",
      rawContent: "## Summary\n\nComparison is ready.",
      createdAt: new Date().toISOString(),
      status: "ready",
      blocks: [],
      citations: [],
      artifacts: [],
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      confidence: undefined,
      trace: null,
      traceId: undefined,
      cached: false,
      thinkingContent: "",
      structured: {
        key_findings: [],
        detailed_analysis: "Comparison is ready.",
        limitations: "",
        conclusion: "",
        confidence_score: 0.8,
        follow_up_suggestions: [],
        comparison_table: {
          title: "Structured Comparison",
          headers: ["Document", "Health"],
          rows: [["Alpha.pdf", "Strong"]],
        },
        chart: null,
        diagram: null,
      },
      error: null,
      versions: [],
      versionCount: 0,
      activeVersionId: null,
      activeVersionIndex: 0,
    };

    render(
      <RichMessageRenderer
        message={message}
        isStreaming={false}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Structured Comparison")).toBeInTheDocument();
    expect(screen.getByText("Alpha.pdf")).toBeInTheDocument();
    expect(screen.getByText("Strong")).toBeInTheDocument();
  });

  it("keeps structured tables visible when table-like text is inside a code fence", () => {
    const message: QueryThreadMessage = {
      id: "assistant-fenced-table",
      role: "assistant",
      content:
        "Here is the raw export.\n\n```text\n| Name | Score |\n| --- | --- |\n| Alpha | 92 |\n```",
      rawContent:
        "Here is the raw export.\n\n```text\n| Name | Score |\n| --- | --- |\n| Alpha | 92 |\n```",
      createdAt: new Date().toISOString(),
      status: "ready",
      blocks: [
        {
          id: "table-fenced-1",
          type: "table",
          title: "Structured Results",
          headers: ["Name", "Score"],
          rows: [["Alpha", "92"]],
        },
      ],
      citations: [],
      artifacts: [],
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      confidence: undefined,
      trace: null,
      traceId: undefined,
      cached: false,
      thinkingContent: "",
      structured: null,
      error: null,
      versions: [],
      versionCount: 0,
      activeVersionId: null,
      activeVersionIndex: 0,
    };

    render(
      <RichMessageRenderer
        message={message}
        isStreaming={false}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    const table = screen.getByRole("table", { name: "Structured Results" });
    expect(within(table).getByText("Alpha")).toBeInTheDocument();
    expect(within(table).getByText("92")).toBeInTheDocument();
  });

  it("strips markdown mermaid fences when a structured diagram block exists", () => {
    const message: QueryThreadMessage = {
      id: "assistant-1",
      role: "assistant",
      content:
        "Here is the diagram.\n\n```mermaid\nflowchart TD\nA[Course Book Mind Map] --> B[Units]\n```\n",
      rawContent:
        "Here is the diagram.\n\n```mermaid\nflowchart TD\nA[Course Book Mind Map] --> B[Units]\n```\n",
      createdAt: new Date().toISOString(),
      status: "ready",
      blocks: [
        {
          id: "diagram-1",
          type: "diagram",
          title: "Generated Diagram",
          diagram_type: "mermaid_flowchart",
          source: "mermaid",
          syntax: "flowchart TD\nA[Course Book Mind Map] --> B[Units]",
          description: "Flowchart",
        },
      ],
      citations: [],
      artifacts: [],
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      confidence: undefined,
      trace: null,
      traceId: undefined,
      cached: false,
      thinkingContent: "",
      structured: null,
      error: null,
      versions: [],
      versionCount: 0,
      activeVersionId: null,
      activeVersionIndex: 0,
    };

    render(
      <RichMessageRenderer
        message={message}
        isStreaming={false}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Generated Diagram")).toBeInTheDocument();
    expect(screen.queryByText(/Course Book Mind Map/)).not.toBeInTheDocument();
  });

  it("keeps markdown mermaid fences during streaming and suppresses the structured mermaid block", () => {
    const message: QueryThreadMessage = {
      id: "assistant-2",
      role: "assistant",
      content:
        "Here is the diagram.\n\n```mermaid\nflowchart TD\nA[Course Book Mind Map] --> B[Units]\n```\n",
      rawContent:
        "Here is the diagram.\n\n```mermaid\nflowchart TD\nA[Course Book Mind Map] --> B[Units]\n```\n",
      createdAt: new Date().toISOString(),
      status: "streaming",
      blocks: [
        {
          id: "diagram-2",
          type: "diagram",
          title: "Generated Diagram",
          diagram_type: "mermaid_flowchart",
          source: "mermaid",
          syntax: "flowchart TD\nA[Course Book Mind Map] --> B[Units]",
          description: "Flowchart",
        },
      ],
      citations: [],
      artifacts: [],
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      confidence: undefined,
      trace: null,
      traceId: undefined,
      cached: false,
      thinkingContent: "",
      structured: null,
      error: null,
      versions: [],
      versionCount: 0,
      activeVersionId: null,
      activeVersionIndex: 0,
    };

    render(
      <RichMessageRenderer
        message={message}
        isStreaming={true}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText(/flowchart TD/i)).toBeInTheDocument();
    expect(screen.queryByText("Generated Diagram")).not.toBeInTheDocument();
  });

  it("moves chart transport into the chart container once a chart block exists during streaming", () => {
    const message: QueryThreadMessage = {
      id: "assistant-chart-streaming",
      role: "assistant",
      content: "Summary first.\n\nChart Data\n- Jan: 10\n- Feb: 12\n",
      rawContent: "Summary first.\n\nChart Data\n- Jan: 10\n- Feb: 12\n",
      createdAt: new Date().toISOString(),
      status: "streaming",
      blocks: [
        {
          id: "chart-1",
          type: "chart",
          title: "Chart Data",
          chart_type: "line",
          series: [
            { label: "Jan", value: 10 },
            { label: "Feb", value: 12 },
          ],
        },
      ],
      citations: [],
      artifacts: [],
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      confidence: undefined,
      trace: null,
      traceId: undefined,
      cached: false,
      thinkingContent: "",
      structured: null,
      error: null,
      versions: [],
      versionCount: 0,
      activeVersionId: null,
      activeVersionIndex: 0,
    };

    render(
      <RichMessageRenderer
        message={message}
        isStreaming={true}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Summary first.")).toBeInTheDocument();
    expect(screen.queryByText(/- Jan: 10/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("Chart Data").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Jan").length).toBeGreaterThan(0);
    expect(screen.getAllByText("10").length).toBeGreaterThan(0);
  });

  it("keeps mermaid and chart rendering separate when both exist", () => {
    const message: QueryThreadMessage = {
      id: "assistant-chart-diagram",
      role: "assistant",
      content:
        "Architecture summary.\n\n```mermaid\nflowchart TD\nA --> B\n```\n\nChart Data\n- Jan: 10\n- Feb: 12\n",
      rawContent:
        "Architecture summary.\n\n```mermaid\nflowchart TD\nA --> B\n```\n\nChart Data\n- Jan: 10\n- Feb: 12\n",
      createdAt: new Date().toISOString(),
      status: "streaming",
      blocks: [
        {
          id: "chart-2",
          type: "chart",
          title: "Chart Data",
          chart_type: "bar",
          series: [
            { label: "Jan", value: 10 },
            { label: "Feb", value: 12 },
          ],
        },
        {
          id: "diagram-3",
          type: "diagram",
          title: "Generated Diagram",
          diagram_type: "mermaid_flowchart",
          source: "mermaid",
          syntax: "flowchart TD\nA --> B",
          description: "Flowchart",
        },
      ],
      citations: [],
      artifacts: [],
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      confidence: undefined,
      trace: null,
      traceId: undefined,
      cached: false,
      thinkingContent: "",
      structured: null,
      error: null,
      versions: [],
      versionCount: 0,
      activeVersionId: null,
      activeVersionIndex: 0,
    };

    render(
      <RichMessageRenderer
        message={message}
        isStreaming={true}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText(/flowchart TD/i)).toBeInTheDocument();
    expect(screen.queryByText("Generated Diagram")).not.toBeInTheDocument();
    expect(screen.queryByText(/- Jan: 10/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("Jan").length).toBeGreaterThan(0);
  });

  it("keeps advanced mermaid families separate from chart transport", () => {
    const message: QueryThreadMessage = {
      id: "assistant-c4-and-chart",
      role: "assistant",
      content:
        'System context.\n\n```mermaid\nC4Context\nPerson(user, "User")\nSystem(app, "AverQel")\nRel(user, app, "Uses")\n```\n\nChart Data\n- Jan: 10\n- Feb: 12\n',
      rawContent:
        'System context.\n\n```mermaid\nC4Context\nPerson(user, "User")\nSystem(app, "AverQel")\nRel(user, app, "Uses")\n```\n\nChart Data\n- Jan: 10\n- Feb: 12\n',
      createdAt: new Date().toISOString(),
      status: "streaming",
      blocks: [
        {
          id: "chart-c4-1",
          type: "chart",
          title: "Chart Data",
          chart_type: "bar",
          series: [
            { label: "Jan", value: 10 },
            { label: "Feb", value: 12 },
          ],
        },
        {
          id: "diagram-c4-1",
          type: "diagram",
          title: "Generated Diagram",
          diagram_type: "mermaid_c4",
          source: "mermaid",
          syntax: 'C4Context\nPerson(user, "User")\nSystem(app, "AverQel")\nRel(user, app, "Uses")',
          description: "System context",
        },
      ],
      citations: [],
      artifacts: [],
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      confidence: undefined,
      trace: null,
      traceId: undefined,
      cached: false,
      thinkingContent: "",
      structured: null,
      error: null,
      versions: [],
      versionCount: 0,
      activeVersionId: null,
      activeVersionIndex: 0,
    };

    render(
      <RichMessageRenderer
        message={message}
        isStreaming={true}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getAllByText(/C4Context/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("Generated Diagram")).not.toBeInTheDocument();
    expect(screen.queryByText(/- Jan: 10/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("Jan").length).toBeGreaterThan(0);
  });

  it("promotes markdown chart tables into dedicated chart blocks and strips the table transport", () => {
    const message: QueryThreadMessage = {
      id: "assistant-markdown-charts",
      role: "assistant",
      content:
        "## Line Chart\n\n| Month | Value |\n| --- | --- |\n| Jan | 5 |\n| Feb | 8 |\n| Mar | 12 |\n\nChart Data\n- Jan: 5\n- Feb: 8\n- Mar: 12\n\n## Pie Chart\n\n| Category | Percentage |\n| --- | --- |\n| Jan | 30% |\n| Feb | 40% |\n| Mar | 30% |\n\nChart Data\n- Jan: 30%\n- Feb: 40%\n- Mar: 30%\n",
      rawContent:
        "## Line Chart\n\n| Month | Value |\n| --- | --- |\n| Jan | 5 |\n| Feb | 8 |\n| Mar | 12 |\n\nChart Data\n- Jan: 5\n- Feb: 8\n- Mar: 12\n\n## Pie Chart\n\n| Category | Percentage |\n| --- | --- |\n| Jan | 30% |\n| Feb | 40% |\n| Mar | 30% |\n\nChart Data\n- Jan: 30%\n- Feb: 40%\n- Mar: 30%\n",
      createdAt: new Date().toISOString(),
      status: "ready",
      blocks: [],
      citations: [],
      artifacts: [],
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      confidence: undefined,
      trace: null,
      traceId: undefined,
      cached: false,
      thinkingContent: "",
      structured: null,
      error: null,
      versions: [],
      versionCount: 0,
      activeVersionId: null,
      activeVersionIndex: 0,
    };

    render(
      <RichMessageRenderer
        message={message}
        isStreaming={false}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByRole("img", { name: "Line Chart" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Pie Chart" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryAllByText("Chart Data")).toHaveLength(0);
  });
});
