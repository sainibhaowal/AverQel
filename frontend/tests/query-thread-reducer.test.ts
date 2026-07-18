import {
  initialQueryThreadState,
  queryThreadReducer,
} from "../app/dashboard/query/_lib/query-thread-reducer";

describe("query thread reducer", () => {
  it("creates user and assistant messages on submit and finalizes on done", () => {
    const submitted = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "Explain the architecture",
    });

    expect(submitted.messages).toHaveLength(2);
    expect(submitted.messages[0].role).toBe("user");
    expect(submitted.messages[0].content).toBe("Explain the architecture");
    expect(submitted.messages[1].role).toBe("assistant");
    expect(submitted.messages[1].status).toBe("streaming");
    expect(submitted.activeAssistantId).toBe(submitted.messages[1].id);

    const withDelta = queryThreadReducer(submitted, {
      type: "stream_event",
      event: { event: "delta", data: { text: "Hello" } },
    });
    expect(withDelta.messages[1].content).toBe("Hello");

    const withFollowups = queryThreadReducer(withDelta, {
      type: "stream_event",
      event: { event: "followups", data: { items: ["What changed?"] } },
    });
    expect(withFollowups.messages[1].followups).toEqual(["What changed?"]);

    const withDiagram = queryThreadReducer(withFollowups, {
      type: "stream_event",
      event: {
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
    });
    expect(withDiagram.messages[1].blocks).toHaveLength(1);
    expect(withDiagram.messages[1].blocks[0].type).toBe("diagram");

    const finished = queryThreadReducer(withDiagram, {
      type: "stream_event",
      event: { event: "done", data: { completed: true } },
    });
    expect(finished.isStreaming).toBe(false);
    expect(finished.activeAssistantId).toBeNull();
    expect(finished.messages[1].status).toBe("ready");
  });

  it("attaches followups to the last assistant after completion", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "hello",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: { event: "delta", data: { text: "Answer body" } },
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: { event: "done", data: { completed: true } },
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: { event: "followups", data: { items: ["What changed next?"] } },
    });

    expect(state.messages[1].followups).toEqual(["What changed next?"]);
  });

  it("marks active assistant as error on stream failure", () => {
    const submitted = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "hello",
    });

    const failed = queryThreadReducer(submitted, {
      type: "stream_failed",
      error: { code: "STREAM_HTTP_ERROR", message: "boom" },
    });

    expect(failed.isStreaming).toBe(false);
    expect(failed.streamError).toEqual({ code: "STREAM_HTTP_ERROR", message: "boom" });
    expect(failed.messages[1].status).toBe("error");
    expect(failed.messages[1].error).toEqual({ code: "STREAM_HTTP_ERROR", message: "boom" });
  });

  it("keeps partial assistant output when the stream is interrupted by the user", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "hello",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: { event: "delta", data: { text: "Partial answer" } },
    });

    state = queryThreadReducer(state, { type: "stream_interrupted" });

    expect(state.isStreaming).toBe(false);
    expect(state.activeAssistantId).toBeNull();
    expect(state.streamError).toBeNull();
    expect(state.messages[1].content).toBe("Partial answer");
    expect(state.messages[1].status).toBe("ready");
  });

  it("stores streamed thinking content separately from the final answer", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "think about this",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: { event: "thinking", data: { text: "Planning the answer." } },
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: { event: "delta", data: { text: "Final answer" } },
    });

    expect(state.messages[1].thinkingContent).toBe("Planning the answer.");
    expect(state.messages[1].content).toBe("Final answer");
  });

  it("stores streamed status history, files, and output payloads", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "show generated outputs",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "status",
        data: { label: "Answering", state: "running", detail: "Drafting response" },
      },
    });
    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "files",
        data: { items: [{ name: "diagram.svg", url: "/artifacts/diagram.svg", type: "svg" }] },
      },
    });
    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "output",
        data: { items: [{ type: "diagram", title: "Architecture", description: "System flow" }] },
      },
    });

    expect(state.messages[1].statusHistory).toEqual([
      {
        code: "retrieval",
        label: "Retrieving Evidence",
        state: "running",
        detail: "Starting query pipeline",
        timestamp: expect.any(String),
      },
      {
        code: undefined,
        label: "Answering",
        state: "running",
        detail: "Drafting response",
        timestamp: undefined,
        durationMs: undefined,
      },
    ]);
    expect(state.messages[1].files).toEqual([
      { name: "diagram.svg", url: "/artifacts/diagram.svg", type: "svg" },
    ]);
    expect(state.messages[1].output).toEqual([
      { type: "diagram", title: "Architecture", description: "System flow" },
    ]);
  });

  it("updates an existing progressive block in place when a richer payload arrives", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "Show me the architecture",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "diagram",
        data: {
          id: "diagram-1",
          title: "Pipeline",
          diagram_type: "mermaid_flowchart",
          source: "mermaid",
          syntax: "flowchart LR\nA --> B",
          description: "",
        },
      },
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "diagram",
        data: {
          id: "diagram-1",
          title: "Pipeline",
          diagram_type: "mermaid_flowchart",
          source: "mermaid",
          syntax: "flowchart LR\nA --> B --> C",
          description: "Expanded flow.",
        },
      },
    });

    expect(state.messages[1].blocks).toHaveLength(1);
    expect(state.messages[1].blocks[0]).toMatchObject({
      id: "diagram-1",
      description: "Expanded flow.",
      syntax: "flowchart LR\nA --> B --> C",
    });
  });

  it("stores graph-json diagram payloads", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "Show me the service graph",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "diagram",
        data: {
          id: "diagram-graph-1",
          title: "Service Graph",
          diagram_type: "graph_canvas",
          source: "graph_json",
          syntax: "",
          description: "Dependencies",
          graph: {
            layout: "horizontal",
            nodes: [
              { id: "client", label: "Client", category: "edge" },
              { id: "api", label: "API", category: "service" },
            ],
            edges: [{ source: "client", target: "api", label: "request" }],
          },
        },
      },
    });

    expect(state.messages[1].blocks[0]).toMatchObject({
      id: "diagram-graph-1",
      diagram_type: "graph_canvas",
      source: "graph_json",
    });
  });

  it("defaults streamed diagram events without a source to mermaid", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "Show me a diagram",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "diagram",
        data: {
          id: "diagram-implicit-mermaid",
          title: "Generated Diagram",
          diagram_type: "mermaid_flowchart",
          syntax: "flowchart LR\nA --> B",
          description: "",
        } as never,
      },
    });

    expect(state.messages[1].blocks[0]).toMatchObject({
      id: "diagram-implicit-mermaid",
      source: "mermaid",
      diagram_type: "mermaid_flowchart",
    });
  });

  it("skips no-op markdown replace when visible content is already rendered", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "Show me the architecture",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "delta",
        data: {
          text: "Architecture summary\n\n```mermaid\nflowchart LR\nA --> B\n```",
        },
      },
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "diagram",
        data: {
          id: "diagram-1",
          title: "Pipeline",
          diagram_type: "mermaid_flowchart",
          source: "mermaid",
          syntax: "flowchart LR\nA --> B",
          description: "",
        },
      },
    });

    const beforeReplace = state.messages[1].content;
    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "replace",
        data: {
          content: "Architecture summary\n\n```mermaid\nflowchart LR\nA --> B\n```",
          format: "markdown",
        },
      },
    });

    expect(state.messages[1].content).toBe(beforeReplace);
  });

  it("keeps raw followup transport in reducer state for the renderer to suppress", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "Explain the paper",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "delta",
        data: {
          text: "Core answer text.\n\n*suggestions---\nWhat changed?\nWhy does it matter?\nShow the trade-offs.",
        },
      },
    });

    expect(state.messages[1].content).toContain("*suggestions---");
  });

  it("keeps markdown table syntax in the visible content stream", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "Compare systems",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "delta",
        data: {
          text: "Comparison below\n\n| Name | Value |\n| --- | --- |\n| A | 1 |\n",
        },
      },
    });

    expect(state.messages[1].content).toContain("| Name | Value |");

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "table",
        data: {
          id: "table-1",
          title: "Comparison Table",
          headers: ["Name", "Value"],
          rows: [["A", "1"]],
        },
      },
    });

    expect(state.messages[1].content).toContain("| Name | Value |");
    expect(state.messages[1].blocks[0]).toMatchObject({
      type: "table",
      headers: ["Name", "Value"],
    });
  });

  it("restores structured cards and structured content from saved history metadata", () => {
    const state = queryThreadReducer(initialQueryThreadState, {
      type: "load_history",
      conversationId: "conv-1",
      messages: [
        {
          id: "assistant-1",
          role: "assistant",
          content: "fallback plain text",
          created_at: new Date().toISOString(),
          metadata_json: {
            structured_answer: {
              key_findings: ["First point", "Second point"],
              detailed_analysis: "",
              limitations: "One limitation",
              conclusion: "Final conclusion",
              confidence_score: 0.9,
              follow_up_suggestions: [],
              comparison_table: null,
              chart: null,
              diagram: null,
            },
            blocks: [
              {
                id: "card-key-findings",
                type: "card",
                title: "Key Findings",
                content: "- First point\n- Second point",
                tone: "info",
              },
              {
                id: "card-conclusion",
                type: "card",
                title: "Conclusion",
                content: "Final conclusion",
                tone: "success",
              },
            ],
          },
        },
      ],
    });

    expect(state.messages[0].content).toContain("### Key Findings");
    expect(state.messages[0].blocks).toHaveLength(2);
    expect(state.messages[0].blocks[0]).toMatchObject({
      type: "card",
      title: "Key Findings",
    });
  });
});
