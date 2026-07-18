import {
  initialQueryThreadState,
  queryThreadReducer,
} from "../app/dashboard/query/_lib/query-thread-reducer";

describe("query rich block ordering", () => {
  it("keeps rich blocks in arrival order while preserving streamed markdown", () => {
    let state = queryThreadReducer(initialQueryThreadState, {
      type: "submit_query",
      query: "Show me the architecture",
    });

    state = queryThreadReducer(state, {
      type: "stream_event",
      event: { event: "delta", data: { text: "### Architecture\n" } },
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
          description: "Flow",
        },
      },
    });
    state = queryThreadReducer(state, {
      type: "stream_event",
      event: {
        event: "table",
        data: {
          id: "table-1",
          title: "Stages",
          headers: ["Stage", "Role"],
          rows: [["A", "Input"]],
        },
      },
    });

    const assistant = state.messages[1];
    expect(assistant.content).toContain("### Architecture");
    expect(assistant.blocks.map((block) => block.type)).toEqual(["diagram", "table"]);
  });
});
