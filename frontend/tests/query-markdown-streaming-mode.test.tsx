import { render, screen } from "@testing-library/react";

import MarkdownRenderer from "../app/dashboard/query/_components/MarkdownRenderer";

describe("markdown streaming mode", () => {
  it("rerenders streaming markdown directly from the live message content", () => {
    render(<MarkdownRenderer content={"## Heading\n\nPlain streaming text."} streaming={true} />);

    expect(screen.getByText("Heading")).toBeInTheDocument();
    expect(screen.getByText("Plain streaming text.")).toBeInTheDocument();
  });

  it("normalizes collapsed headings and preserves table text during streaming", () => {
    render(
      <MarkdownRenderer
        content={
          "Memory Efficiency#### Key Improvement\n| Model | FLOPs |\n| --- | --- |\n| MegaByte | 0.125x |"
        }
        streaming={true}
      />,
    );

    expect(screen.getByText("Memory Efficiency")).toBeInTheDocument();
    expect(screen.getByText("Key Improvement")).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, element) => element?.tagName.toLowerCase() === "th" && element.textContent === "Model",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("MegaByte")).toBeInTheDocument();
  });

  it("keeps trailing bullet sections readable while streaming", () => {
    render(
      <MarkdownRenderer
        content={
          "Model-Specific Architectures\n| Model | Parameters |\n\n| --- | --- |\n\n| MegaByte | 80B |\n\n| MambaByte | 30B |\n- MegaByte's Advantage: lower BPB."
        }
        streaming={true}
      />,
    );

    expect(screen.getByText("Model-Specific Architectures")).toBeInTheDocument();
    expect(screen.getByText(/MegaByte's Advantage/i)).toBeInTheDocument();
  });

  it("renders inline markdown formatting inside streamed table cells", () => {
    render(
      <MarkdownRenderer
        content={
          "### Technical Distinctions\n\n| Feature | MegaByte | MambaByte |\n| --- | --- | --- |\n| **Architecture** | Transformer | State-space |\n| **Parameters** | ~1B+ | 353M |"
        }
        streaming={true}
      />,
    );

    const architectureCell = screen.getByText("Architecture");
    expect(architectureCell.tagName.toLowerCase()).toBe("strong");
    expect(screen.getByText("Transformer")).toBeInTheDocument();
    expect(screen.getByText("353M")).toBeInTheDocument();
  });

  it("unwraps full-answer markdown fences so they render as rich content instead of a code block", () => {
    render(
      <MarkdownRenderer
        content={
          "```markdown\n### Key Metrics\n\n| Model | Value |\n| --- | --- |\n| MambaByte | 33.0 |\n```"
        }
        streaming={true}
      />,
    );

    expect(screen.getByText("Key Metrics")).toBeInTheDocument();
    expect(screen.getByText("MambaByte")).toBeInTheDocument();
    expect(screen.queryByText(/^markdown$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Copy$/i)).not.toBeInTheDocument();
  });

  it("renders markdown inside streamed small headings without leaking stars or cyan-label styling", () => {
    render(
      <MarkdownRenderer
        content={"#### **1. Core Design Philosophy**\n\nFocuses on raw bytes directly."}
        streaming={true}
      />,
    );

    const headingText = screen.getByText("1. Core Design Philosophy");
    expect(headingText.tagName.toLowerCase()).toBe("strong");
    expect(screen.queryByText(/\*\*1\. Core Design Philosophy\*\*/i)).not.toBeInTheDocument();
  });
});
