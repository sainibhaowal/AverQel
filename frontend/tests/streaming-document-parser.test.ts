import {
  parseStreamingDocument,
  normalizeStreamingTables,
  unwrapDocumentMarkdownFence,
} from "../app/dashboard/query/_lib/streaming-document-parser";

describe("streaming document parser", () => {
  it("unwraps full-answer markdown fences", () => {
    expect(unwrapDocumentMarkdownFence("```markdown\n## Hello\n```", true)).toBe("## Hello");
  });

  it("parses headings, paragraphs, lists, and tables from streaming content", () => {
    const nodes = parseStreamingDocument(
      "Memory Efficiency#### Key Improvement\n| Model | FLOPs |\n| --- | --- |\n| MegaByte | 0.125x |\n- Advantage: lower BPB.",
      true,
    );

    expect(nodes.map((node) => node.type)).toEqual(["paragraph", "heading", "table", "list"]);
    expect(nodes[0]).toMatchObject({ type: "paragraph", content: "Memory Efficiency" });
    expect(nodes[1]).toMatchObject({ type: "heading", content: "Key Improvement" });
    expect(nodes[2]).toMatchObject({
      type: "table",
      headers: ["Model", "FLOPs"],
      rows: [["MegaByte", "0.125x"]],
    });
    expect(nodes[3]).toMatchObject({
      type: "list",
      ordered: false,
      items: [{ content: "Advantage: lower BPB." }],
    });
  });

  it("does not render markdown alignment separators as standalone table rows", () => {
    const nodes = parseStreamingDocument(
      [
        "| Subtopic | Key concepts | Why it matters |",
        "| :--- | :--- | :--- |",
        "| Quantum Field Theory | QED, Standard Model | Particle physics foundation |",
        "",
        "| :--- | :--- | :--- |",
      ].join("\n"),
      true,
    );

    const tables = nodes.filter((node) => node.type === "table");
    expect(tables).toHaveLength(1);
    expect(tables[0]).toMatchObject({
      headers: ["Subtopic", "Key concepts", "Why it matters"],
      rows: [["Quantum Field Theory", "QED, Standard Model", "Particle physics foundation"]],
    });
  });

  it("keeps incomplete fenced code blocks as provisional code nodes", () => {
    const nodes = parseStreamingDocument("```mermaid\ngraph TD\nA-->B", true);

    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toMatchObject({
      type: "code",
      language: "mermaid",
      incomplete: true,
      value: "graph TD\nA-->B",
    });
  });

  it("does not rewrite mermaid edge-label pipes inside fenced code blocks as table rows", () => {
    const normalized = normalizeStreamingTables(
      "```mermaid\ngraph TD\nA -->|Overlap with Gamma Distribution| B[Gamma Distribution]\n```",
    );

    expect(normalized).toContain("A -->|Overlap with Gamma Distribution| B[Gamma Distribution]");
    expect(normalized).not.toContain(
      "| A -->|Overlap with Gamma Distribution| B[Gamma Distribution] |",
    );
  });

  it("parses ordered lists without collapsing them into paragraphs", () => {
    const nodes = parseStreamingDocument("1. First\n2. Second\n3. Third", true);

    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toMatchObject({
      type: "list",
      ordered: true,
      items: [{ content: "First" }, { content: "Second" }, { content: "Third" }],
    });
  });

  it("parses nested task lists, images, and footnotes", () => {
    const nodes = parseStreamingDocument(
      [
        "- [x] Launch",
        "  - [ ] Verify",
        "    - Deep check",
        '![Hero nebula](https://example.com/hero.png "Hero")',
        "[^1]: Footnote line one",
        "    continued footnote detail",
      ].join("\n"),
      true,
    );

    expect(nodes[0]).toMatchObject({
      type: "list",
      ordered: false,
      items: [
        {
          content: "Launch",
          task: true,
          checked: true,
          children: [
            {
              type: "list",
              ordered: false,
              items: [
                {
                  content: "Verify",
                  task: true,
                  checked: false,
                  children: [
                    {
                      type: "list",
                      ordered: false,
                      items: [{ content: "Deep check" }],
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
    });

    expect(nodes[1]).toMatchObject({
      type: "image",
      alt: "Hero nebula",
      src: "https://example.com/hero.png",
      title: "Hero",
    });

    expect(nodes[2]).toMatchObject({
      type: "footnote",
      identifier: "1",
      content: "Footnote line one\ncontinued footnote detail",
    });
  });
});
