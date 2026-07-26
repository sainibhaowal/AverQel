import { render, screen } from "@testing-library/react";

import AssistantMessage from "../app/dashboard/query/_components/AssistantMessage";
import MarkdownRenderer from "../app/dashboard/query/_components/MarkdownRenderer";
import type { QueryThreadMessage } from "../app/dashboard/query/_lib/stream-protocol";

const baseAssistantMessage: QueryThreadMessage = {
  id: "assistant-1",
  role: "assistant",
  content: "",
  rawContent: "",
  createdAt: new Date().toISOString(),
  status: "ready",
  citations: [],
  blocks: [],
  artifacts: [],
  trace: null,
  followups: [],
  statusHistory: [],
  output: [],
  files: [],
  structured: null,
  error: null,
  activeVersionId: "assistant-1-v1",
  activeVersionIndex: 1,
  versionCount: 1,
  versions: [
    {
      id: "assistant-1-v1",
      versionIndex: 1,
      sourceType: "initial",
      createdAt: new Date().toISOString(),
      content: "",
      rawContent: "",
      citations: [],
      blocks: [],
      artifacts: [],
      trace: null,
      followups: [],
      statusHistory: [],
      output: [],
      files: [],
      structured: null,
      error: null,
      status: "ready",
    },
  ],
};

describe("AssistantMessage", () => {
  it("does not render a blank shell when there is no payload and it is not streaming", () => {
    const { container } = render(
      <AssistantMessage
        message={baseAssistantMessage}
        isStreaming={false}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  it("renders delete action when assistant controls are enabled", () => {
    render(
      <AssistantMessage
        message={{ ...baseAssistantMessage, content: "Completed answer" }}
        isStreaming={false}
        canRegenerate={true}
        onRetry={() => {}}
        onRegenerate={() => {}}
        onActivateVersion={() => {}}
        onDelete={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Delete")).toBeInTheDocument();
  });

  it("renders a visible thinking panel above the answer when provider thinking text exists", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: "Final answer",
          thinkingContent: "First I inspect the request and outline the answer.",
        }}
        isStreaming={false}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText(/thought process/i)).toBeInTheDocument();
    expect(screen.getByText(/final answer/i)).toBeInTheDocument();
  });

  it("renders status history and generated files when present", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: "```svg\n<svg></svg>\n```",
          status: "ready",
          blocks: [
            {
              id: "diagram-1",
              type: "diagram",
              title: "Architecture",
              diagram_type: "mermaid_flowchart",
              source: "mermaid",
              syntax: "flowchart LR\nA --> B",
              description: "System flow",
            },
          ],
          artifacts: [
            {
              id: "artifact-svg-1",
              type: "svg",
              language: "svg",
              title: "Architecture SVG",
              content: "<svg></svg>",
            },
          ],
          statusHistory: [
            { label: "Searching evidence", state: "completed", detail: "1 source found" },
            { label: "Answering", state: "completed", detail: "Response ready" },
          ],
          output: [{ type: "diagram", title: "Architecture", description: "System flow" }],
          files: [{ name: "architecture.svg", url: "/artifacts/architecture.svg", type: "svg" }],
        }}
        isStreaming={false}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Generated Files")).toBeInTheDocument();
    expect(screen.getByText("Status Timeline")).toBeInTheDocument();
    expect(screen.getByText("Searching evidence")).toBeInTheDocument();
    expect(screen.getByText("Architecture SVG")).toBeInTheDocument();
    expect(screen.getByText("architecture.svg")).toBeInTheDocument();
    expect(screen.getAllByText("Architecture").length).toBeGreaterThan(0);
  });

  it("renders streaming indicator immediately for an empty active assistant message", () => {
    render(
      <AssistantMessage
        message={{ ...baseAssistantMessage, status: "streaming", streamPhase: "searching" }}
        isStreaming={true}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText(/searching evidence/i)).toBeInTheDocument();
  });

  it("renders streaming markdown directly for plain live text", () => {
    render(
      <MarkdownRenderer
        content={"### Quick Summary\n\n- Point A\n- Point B\n\nThis is still streaming."}
        streaming={true}
      />,
    );

    expect(screen.getByText("Quick Summary")).toBeInTheDocument();
    expect(screen.getByText("Point A")).toBeInTheDocument();
    expect(screen.getByText("This is still streaming.")).toBeInTheDocument();
  });

  it("suppresses raw structured json while streaming", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content:
            '```json\n{"key_findings":[],"detailed_analysis":"hello","limitations":"","conclusion":"","confidence_score":0.8,"follow_up_suggestions":[],"comparison_table":null,"chart":null,"diagram":null}\n```',
          status: "streaming",
          streamPhase: "answering",
        }}
        isStreaming={true}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.queryByText(/key_findings/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/detailed_analysis/i)).not.toBeInTheDocument();
  });

  it("renders completed mermaid fences through the code block renderer", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: "Intro text\n\n```mermaid\nflowchart LR\nA --> B\n```",
          status: "streaming",
          streamPhase: "answering",
        }}
        isStreaming={true}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Intro text")).toBeInTheDocument();
    expect(screen.getByText(/flowchart LR/i)).toBeInTheDocument();
    expect(screen.queryByText(/syntax error/i)).not.toBeInTheDocument();
  });

  it("renders incomplete mermaid fences during streaming", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: "Intro text\n\n```mermaid\nflowchart LR\nA --> B",
          status: "streaming",
          streamPhase: "answering",
        }}
        isStreaming={true}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Intro text")).toBeInTheDocument();
    expect(screen.getByText(/flowchart LR/i)).toBeInTheDocument();
    expect(screen.queryByText(/syntax error/i)).not.toBeInTheDocument();
  });

  it("keeps conclusion text in the normal answer body even if card metadata exists", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: "### Conclusion\n\nNo architecture decisions are present in these documents.",
          status: "ready",
          blocks: [
            {
              id: "card-conclusion",
              type: "card",
              title: "Conclusion",
              content: "No architecture decisions are present in these documents.",
              tone: "success",
            },
          ],
        }}
        isStreaming={false}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Conclusion")).toBeInTheDocument();
    expect(
      screen.getByText("No architecture decisions are present in these documents."),
    ).toBeInTheDocument();
  });

  it("keeps final answer text visible instead of converting it into a card-only surface", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: "### Final Answer\n\nSummary: Unit 2 covers random variables.",
          status: "ready",
          blocks: [
            {
              id: "card-conclusion",
              type: "card",
              title: "Conclusion",
              content: "Summary: Unit 2 covers random variables.",
              tone: "success",
            },
          ],
        }}
        isStreaming={false}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Final Answer")).toBeInTheDocument();
    expect(screen.getByText("Summary: Unit 2 covers random variables.")).toBeInTheDocument();
  });

  it("keeps mermaid source inline and hides the structured mermaid block while streaming", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: "Intro text\n\n```mermaid\nflowchart LR\nA --> B\n```",
          status: "streaming",
          streamPhase: "answering",
          blocks: [
            {
              id: "diagram-1",
              type: "diagram",
              title: "Generated Diagram",
              diagram_type: "mermaid_flowchart",
              source: "mermaid",
              syntax: "flowchart LR\nA --> B",
            },
          ],
        }}
        isStreaming={true}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Intro text")).toBeInTheDocument();
    expect(screen.getByText(/flowchart LR/i)).toBeInTheDocument();
    expect(screen.queryByText("Generated Diagram")).not.toBeInTheDocument();
  });

  it("renders chart data markdown while streaming until an additive chart view is available", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: "Summary first.\n\nChart Data\n- Jan: 10\n- Feb: 12",
          status: "streaming",
          streamPhase: "answering",
        }}
        isStreaming={true}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Summary first.")).toBeInTheDocument();
    expect(screen.getByText(/Chart Data/i)).toBeInTheDocument();
  });

  it("renders markdown tables directly while streaming", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: "Comparison below\n\n| Name | Value |\n| --- | --- |\n| A | 1 |",
          status: "streaming",
          streamPhase: "answering",
        }}
        isStreaming={true}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Comparison below")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Value")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("hides followup transport markup from the message body", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: "Answer body\n\n---suggestions---\n- Follow up one",
          status: "ready",
          followups: ["Follow up one"],
        }}
        isStreaming={false}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Answer body")).toBeInTheDocument();
    expect(screen.queryByText(/suggestions/i)).not.toBeInTheDocument();
  });

  it.skip("renders comparison answers as structured comparison panels", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: [
            "Compared 2 documents across content evidence, ingestion health, extraction quality, and runtime setup.",
            "Healthiest overall: alpha-report.pdf (92/100).",
            "Most at risk: gamma-notes.pdf (63/100).",
            "",
            "- alpha-report.pdf: status indexed, health 92/100 (strong)",
            "  Extraction: ocr_pipeline, coverage 91%, yield 96%, OCR",
            "  Runtime: sentence-transformers / BAAI/bge-small-en-v1.5, chunks 12, embedded 12, collections Research",
            "  Signals: no major low-quality signal recorded",
            "  Evidence: p.3: alpha discusses adaptive retrieval performance.",
            "",
            "- gamma-notes.pdf: status indexed, health 63/100 (watch)",
            "  Extraction: layout_vision, coverage 44%, yield 68%, Vision",
            "  Runtime: sentence-transformers / BAAI/bge-small-en-v1.5, chunks 10, embedded 10, collections Research",
            "  Signals: low yield 68%, low coverage 44%",
            "  Evidence: p.2: gamma notes mention adaptive retrieval and evaluation.",
          ].join("\n"),
          status: "ready",
        }}
        isStreaming={false}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText(/Compared 2 documents across content evidence/i)).toBeInTheDocument();
    expect(screen.getByText("alpha-report.pdf")).toBeInTheDocument();
    expect(screen.getByText("gamma-notes.pdf")).toBeInTheDocument();
    expect(screen.getByText(/ocr_pipeline/i)).toBeInTheDocument();
    expect(screen.getByText(/low yield 68%/i)).toBeInTheDocument();
  });

  it.skip("can surface comparison panels while streaming once the structure is recognizable", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: [
            "Compared 2 documents across content evidence, ingestion health, extraction quality, and runtime setup.",
            "Healthiest overall: alpha-report.pdf (92/100).",
            "Most at risk: gamma-notes.pdf (63/100).",
            "- alpha-report.pdf: status indexed, health 92/100 (strong)",
            "  Extraction: ocr_pipeline, coverage 91%, yield 96%, OCR",
            "  Runtime: sentence-transformers / BAAI/bge-small-en-v1.5, chunks 12, embedded 12, collections Research",
            "  Signals: no major low-quality signal recorded",
            "  Evidence: p.3: alpha discusses adaptive retrieval performance.",
          ].join("\n"),
          status: "streaming",
          streamPhase: "answering",
        }}
        isStreaming={true}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText(/Compared 2 documents across content evidence/i)).toBeInTheDocument();
    expect(screen.getByText("alpha-report.pdf")).toBeInTheDocument();
  });

  it.skip("renders evidence matches as investigation evidence cards", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: [
            'Documents matching "chunk drift" in the filtered workspace slice (within failed documents):',
            "- beta-analysis.pdf (failed)",
            "  Evidence p.4: beta analysis discusses retrieval failures and chunk drift.",
            "  Evidence p.7: chunk drift impacted indexing stability.",
          ].join("\n"),
          status: "ready",
        }}
        isStreaming={false}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText(/Documents matching "chunk drift"/i)).toBeInTheDocument();
    expect(screen.getByText("beta-analysis.pdf")).toBeInTheDocument();
    expect(screen.getByText(/retrieval failures and chunk drift/i)).toBeInTheDocument();
    expect(screen.getByText(/chunk drift impacted indexing stability/i)).toBeInTheDocument();
  });

  it.skip("renders collection summaries as compact collection panels", () => {
    render(
      <AssistantMessage
        message={{
          ...baseAssistantMessage,
          content: [
            'Collection summary for "Research":',
            "- Documents: 2",
            "- Total storage: 3.00 KB",
            "- Average document health: 77.5/100",
            "- Status mix: indexed=2",
            "Documents:",
            "- alpha-report.pdf: indexed, health 92/100, embedding BAAI/bge-small-en-v1.5",
            "- gamma-notes.pdf: indexed, health 63/100, embedding BAAI/bge-small-en-v1.5",
          ].join("\n"),
          status: "ready",
        }}
        isStreaming={false}
        onRetry={() => {}}
        onPreviewDocument={() => {}}
        onFollowupSelect={() => {}}
      />,
    );

    expect(screen.getByText("Collection Summary")).toBeInTheDocument();
    expect(screen.getByText('"Research"')).toBeInTheDocument();
    expect(screen.getByText("3.00 KB")).toBeInTheDocument();
    expect(screen.getByText(/77.5\/100/i)).toBeInTheDocument();
  });
});
