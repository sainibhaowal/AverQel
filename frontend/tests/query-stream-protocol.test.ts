import { parseSseFrames, parseStructuredAnswer } from "../app/dashboard/query/_lib/stream-protocol";
import { parseVisualChart } from "../app/dashboard/query/_lib/chart-parser";

describe("query stream protocol", () => {
  it("parses multiple SSE frames and preserves remainder", () => {
    const input = [
      'event: start\ndata: {"message_id":"m1","conversation_id":"c1","started_at":"2026-03-09T00:00:00Z"}\n\n',
      'event: delta\ndata: {"text":"Hello"}\n\n',
      'event: done\ndata: {"completed":true}\n\npartial',
    ].join("");

    const parsed = parseSseFrames(input);

    expect(parsed.events).toHaveLength(3);
    expect(parsed.events[0]).toEqual({
      event: "start",
      data: {
        message_id: "m1",
        conversation_id: "c1",
        started_at: "2026-03-09T00:00:00Z",
      },
    });
    expect(parsed.events[1]).toEqual({ event: "delta", data: { text: "Hello" } });
    expect(parsed.events[2]).toEqual({ event: "done", data: { completed: true } });
    expect(parsed.remainder).toBe("partial");
  });

  it("returns a stream parse error event for invalid JSON", () => {
    const parsed = parseSseFrames("event: delta\ndata: {not-json}\n\n");
    expect(parsed.events).toEqual([
      {
        event: "error",
        data: {
          code: "STREAM_PARSE_ERROR",
          message: "Failed to parse stream frame.",
        },
      },
    ]);
  });

  it("parses diagram frames", () => {
    const parsed = parseSseFrames(
      'event: diagram\ndata: {"id":"diagram-1","title":"Pipeline","diagram_type":"mermaid_flowchart","source":"mermaid","syntax":"flowchart LR\\\\nA --> B","description":"Flow"}\n\n',
    );
    expect(parsed.events).toEqual([
      {
        event: "diagram",
        data: {
          id: "diagram-1",
          title: "Pipeline",
          diagram_type: "mermaid_flowchart",
          source: "mermaid",
          syntax: "flowchart LR\\nA --> B",
          description: "Flow",
        },
      },
    ]);
  });

  it("parses graph-json diagram frames", () => {
    const parsed = parseSseFrames(
      'event: diagram\ndata: {"id":"diagram-2","title":"Service Graph","diagram_type":"graph_canvas","source":"graph_json","syntax":"","description":"Graph","graph":{"layout":"horizontal","nodes":[{"id":"client","label":"Client"}],"edges":[]}}\n\n',
    );
    expect(parsed.events).toEqual([
      {
        event: "diagram",
        data: {
          id: "diagram-2",
          title: "Service Graph",
          diagram_type: "graph_canvas",
          source: "graph_json",
          syntax: "",
          description: "Graph",
          graph: {
            layout: "horizontal",
            nodes: [{ id: "client", label: "Client" }],
            edges: [],
          },
        },
      },
    ]);
  });

  it("parses advanced mermaid family diagram frames", () => {
    const parsed = parseSseFrames(
      'event: diagram\ndata: {"id":"diagram-3","title":"Context","diagram_type":"mermaid_c4","source":"mermaid","syntax":"C4Context\\\\nPerson(user, \\"User\\")","description":"System context"}\n\n',
    );
    expect(parsed.events).toEqual([
      {
        event: "diagram",
        data: {
          id: "diagram-3",
          title: "Context",
          diagram_type: "mermaid_c4",
          source: "mermaid",
          syntax: 'C4Context\\nPerson(user, "User")',
          description: "System context",
        },
      },
    ]);
  });

  it("normalizes advanced structured chart payloads", () => {
    const parsed = parseStructuredAnswer(
      JSON.stringify({
        key_findings: [],
        detailed_analysis: "Quarterly distribution",
        limitations: "",
        conclusion: "",
        confidence_score: 0.88,
        follow_up_suggestions: [],
        chart: {
          title: "Revenue Mix",
          chart_type: "pie",
          data: [
            { label: "Products", value: 62 },
            { label: "Services", value: 38 },
          ],
        },
      }),
    );

    expect(parsed?.chart).toEqual({
      title: "Revenue Mix",
      chart_type: "pie",
      series: [
        { label: "Products", value: 62 },
        { label: "Services", value: 38 },
      ],
      raw_payload: JSON.stringify({
        title: "Revenue Mix",
        chart_type: "pie",
        data: [
          { label: "Products", value: 62 },
          { label: "Services", value: 38 },
        ],
      }),
      parser_source: "structured",
      confidence: 0.96,
      fields: ["label", "value"],
      is_streaming: undefined,
      x_key: "label",
      y_key: "value",
      z_key: undefined,
    });
  });

  it("preserves explicit pie chart type for nested structured chart payloads", () => {
    const parsed = parseStructuredAnswer(
      JSON.stringify({
        key_findings: ["Distribution is balanced."],
        detailed_analysis: "Pie chart requested.",
        limitations: "",
        conclusion: "Pie is appropriate.",
        confidence_score: 1,
        follow_up_suggestions: [],
        chart: {
          chart_type: "pie",
          series: [
            {
              label: "Percentage Share",
              data: [
                { name: "Marketing", y: 30 },
                { name: "Sales", y: 40 },
                { name: "Support", y: 30 },
              ],
            },
          ],
          title: "Share by Team",
        },
      }),
    );

    expect(parsed?.chart?.chart_type).toBe("pie");
    expect(parsed?.chart?.series).toEqual([
      { label: "Marketing", value: 30 },
      { label: "Sales", value: 40 },
      { label: "Support", value: 30 },
    ]);
  });

  it("does not classify advanced mermaid diagrams as charts", () => {
    expect(
      parseVisualChart('xychart-beta\ntitle "Latency"\nx-axis [Retrieve, Answer]\nbar [120, 340]'),
    ).toBeNull();
    expect(parseVisualChart('C4Context\nPerson(user, "User")\nSystem(app, "AverQel")')).toBeNull();
  });

  it("parses markdown chart tables when the section has explicit chart intent", () => {
    expect(
      parseVisualChart(
        "## Line Chart\n\n| Month | Value |\n| --- | --- |\n| Jan | 5 |\n| Feb | 8 |\n| Mar | 12 |",
      ),
    ).toEqual({
      type: "line",
      title: "Line Chart",
      data: [
        { label: "Jan", value: 5 },
        { label: "Feb", value: 8 },
        { label: "Mar", value: 12 },
      ],
      xKey: "label",
      yKey: "value",
      zKey: undefined,
      metadata: {
        confidence: 0.72,
        source: "pattern",
        fields: ["Month", "Value"],
      },
    });
  });

  it("parses percentage values from markdown chart tables", () => {
    expect(
      parseVisualChart(
        "## Pie Chart\n\n| Category | Percentage |\n| --- | --- |\n| Jan | 30% |\n| Feb | 40% |\n| Mar | 30% |",
      ),
    ).toEqual({
      type: "pie",
      title: "Pie Chart",
      data: [
        { label: "Jan", value: 30 },
        { label: "Feb", value: 40 },
        { label: "Mar", value: 30 },
      ],
      xKey: "label",
      yKey: "value",
      zKey: undefined,
      metadata: {
        confidence: 0.72,
        source: "pattern",
        fields: ["Category", "Percentage"],
      },
    });
  });
});
