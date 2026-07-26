import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import mermaid from "mermaid";

import StructuredBlockRenderer from "../app/dashboard/query/_components/StructuredBlockRenderer";
import CodeBlock from "../app/dashboard/query/_components/CodeBlock";
import DiagramBlock from "../app/dashboard/query/_components/DiagramBlock";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    parse: vi.fn(async () => true),
    render: vi.fn(async (_id: string, source: string) => ({
      svg: `<svg><text>${source}</text></svg>`,
    })),
  },
}));

describe("diagram block rendering", () => {
  it("renders structured tables as the supported tabular fallback", () => {
    render(
      <StructuredBlockRenderer
        blocks={[
          {
            id: "table-1",
            type: "table",
            title: "Comparison",
            headers: ["Name", "Score"],
            rows: [["Alpha", "92"]],
          },
        ]}
      />,
    );

    expect(screen.getByText("Comparison")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
  });

  it("renders inline mermaid code with an on-demand view action", async () => {
    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={"flowchart LR\nA --> B"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    expect(screen.getByTestId("highlighted-code-block")).toHaveTextContent(/flowchart LR/i);
    expect(screen.getByTitle(/view diagram/i)).toBeInTheDocument();
    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("does not call Mermaid render when parse reports invalid syntax", async () => {
    const parseMock = vi.mocked(mermaid.parse);
    const renderMock = vi.mocked(mermaid.render);
    parseMock.mockImplementationOnce(async () => false as never);
    renderMock.mockClear();

    render(
      <CodeBlock
        language="mermaid"
        value={"flowchart LR\nA --> B"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    expect(await screen.findByText("Invalid Mermaid syntax.")).toBeInTheDocument();
    expect(renderMock).not.toHaveBeenCalled();
  });

  it("centers the initial mermaid view using visible diagram bounds instead of the raw svg canvas", async () => {
    const renderMock = vi.mocked(mermaid.render);
    renderMock.mockResolvedValueOnce({
      svg: `<svg viewBox="0 0 1200 800"><g transform="translate(780, 120)"><rect x="0" y="0" width="220" height="160" /></g></svg>`,
      diagramType: "flowchart-v2",
    });

    const clientWidthSpy = vi
      .spyOn(HTMLElement.prototype, "clientWidth", "get")
      .mockReturnValue(900);
    const clientHeightSpy = vi
      .spyOn(HTMLElement.prototype, "clientHeight", "get")
      .mockReturnValue(520);
    const rafSpy = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback: FrameRequestCallback) =>
        window.setTimeout(() => callback(0), 0),
      );
    const cafSpy = vi
      .spyOn(window, "cancelAnimationFrame")
      .mockImplementation((handle: number) => window.clearTimeout(handle));
    const originalGetBBox = (
      SVGElement.prototype as SVGElement & {
        getBBox?: () => DOMRect;
      }
    ).getBBox;
    let visibleRectCalls = 0;

    Object.defineProperty(SVGElement.prototype, "getBBox", {
      configurable: true,
      value: function getBBox(this: SVGElement) {
        if (this.tagName.toLowerCase() === "rect") {
          visibleRectCalls += 1;
          if (visibleRectCalls < 3) {
            throw new Error("bbox not ready");
          }
          return {
            x: 780,
            y: 120,
            width: 220,
            height: 160,
          } as DOMRect;
        }

        return {
          x: 0,
          y: 0,
          width: 1200,
          height: 800,
        } as DOMRect;
      },
    });
    Object.defineProperty(SVGElement.prototype, "getCTM", {
      configurable: true,
      value: function getCTM(this: SVGElement) {
        if (this.tagName.toLowerCase() === "rect") {
          return {
            a: 1,
            b: 0,
            c: 0,
            d: 1,
            e: 780,
            f: 120,
          };
        }
        return {
          a: 1,
          b: 0,
          c: 0,
          d: 1,
          e: 0,
          f: 0,
        };
      },
    });

    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={"flowchart LR\nA --> B"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    await waitFor(() => {
      const stage = container.querySelector(
        '[data-testid="diagram-stage"] > div > div',
      ) as HTMLElement | null;
      expect(stage).toBeTruthy();
      const translateMatch = stage?.style.transform.match(
        /translate\(([-\d.]+)px,\s*([-\d.]+)px\)/,
      );
      expect(translateMatch).toBeTruthy();
      expect(Number(translateMatch?.[1] ?? 0)).toBeGreaterThan(150);
    });

    if (originalGetBBox) {
      Object.defineProperty(SVGElement.prototype, "getBBox", {
        configurable: true,
        value: originalGetBBox,
      });
    } else {
      delete (SVGElement.prototype as SVGElement & { getBBox?: () => DOMRect }).getBBox;
    }
    delete (
      SVGElement.prototype as SVGElement & { getCTM?: () => DOMMatrix | DOMMatrixReadOnly | null }
    ).getCTM;
    clientWidthSpy.mockRestore();
    clientHeightSpy.mockRestore();
    rafSpy.mockRestore();
    cafSpy.mockRestore();
  });

  it("keeps fit centered after viewport normalization on right-shifted flowcharts", async () => {
    const renderMock = vi.mocked(mermaid.render);
    renderMock.mockResolvedValueOnce({
      svg: `<svg viewBox="0 0 1200 800"><g transform="translate(780, 120)"><rect x="0" y="0" width="220" height="160" /></g></svg>`,
      diagramType: "flowchart-v2",
    });

    const clientWidthSpy = vi
      .spyOn(HTMLElement.prototype, "clientWidth", "get")
      .mockReturnValue(900);
    const clientHeightSpy = vi
      .spyOn(HTMLElement.prototype, "clientHeight", "get")
      .mockReturnValue(520);
    const originalGetBBox = (
      SVGElement.prototype as SVGElement & {
        getBBox?: () => DOMRect;
      }
    ).getBBox;

    Object.defineProperty(SVGElement.prototype, "getBBox", {
      configurable: true,
      value: function getBBox(this: SVGElement) {
        if (this.tagName.toLowerCase() === "rect") {
          return {
            x: 780,
            y: 120,
            width: 220,
            height: 160,
          } as DOMRect;
        }

        return {
          x: 0,
          y: 0,
          width: 1200,
          height: 800,
        } as DOMRect;
      },
    });
    Object.defineProperty(SVGElement.prototype, "getCTM", {
      configurable: true,
      value: function getCTM(this: SVGElement) {
        if (this.tagName.toLowerCase() === "rect") {
          return {
            a: 1,
            b: 0,
            c: 0,
            d: 1,
            e: 780,
            f: 120,
          };
        }
        return {
          a: 1,
          b: 0,
          c: 0,
          d: 1,
          e: 0,
          f: 0,
        };
      },
    });

    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={"flowchart LR\nA --> B"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });
    fireEvent.click(screen.getByTitle(/fit diagram/i));

    await waitFor(() => {
      const stage = container.querySelector(
        '[data-testid="diagram-stage"] > div > div',
      ) as HTMLElement | null;
      expect(stage).toBeTruthy();
      const translateMatch = stage?.style.transform.match(
        /translate\(([-\d.]+)px,\s*([-\d.]+)px\)/,
      );
      expect(translateMatch).toBeTruthy();
      expect(Number(translateMatch?.[1] ?? 0)).toBeGreaterThan(150);
    });

    if (originalGetBBox) {
      Object.defineProperty(SVGElement.prototype, "getBBox", {
        configurable: true,
        value: originalGetBBox,
      });
    } else {
      delete (SVGElement.prototype as SVGElement & { getBBox?: () => DOMRect }).getBBox;
    }
    delete (
      SVGElement.prototype as SVGElement & { getCTM?: () => DOMMatrix | DOMMatrixReadOnly | null }
    ).getCTM;
    clientWidthSpy.mockRestore();
    clientHeightSpy.mockRestore();
  });

  it("repairs punctuation-heavy mermaid labels before rendering", async () => {
    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={
          "graph TD\nK --> L[Textbooks (Klenke, Rohatgi, etc.)]\nM --> N[Tables (Table 1, Table 11)]"
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("repairs same-line graph starters with a stray leading pipe", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={"graph TD| A[Exponential Distribution] --> B[Gamma Distribution]"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await waitFor(() => {
      expect(renderMock).toHaveBeenCalled();
    });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain(
      "graph TD\nA[Exponential Distribution] --> B[Gamma Distribution]",
    );
  });

  it("repairs concatenated flowchart edges separated by double pipes", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={
          "graph TD\nA[Exponential Distribution] --> | Overlap with Gamma Distribution | B[Gamma Distribution] || A --> | Overlap with Poisson Distribution | C[Poisson Distribution]"
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await waitFor(() => {
      expect(renderMock).toHaveBeenCalled();
    });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain(
      "A[Exponential Distribution] -->|Overlap with Gamma Distribution| B[Gamma Distribution]",
    );
    expect(renderCall?.[1]).toContain(
      "\nA -->|Overlap with Poisson Distribution| C[Poisson Distribution]",
    );
    expect(renderCall?.[1]).not.toContain("] || A --> |");
    expect(renderCall?.[1]).not.toContain("--> | Overlap");
  });

  it("repairs erDiagram relationship spacing before rendering", async () => {
    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={"erDiagram\nDocument | | -- o{ Chunk : contains"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("repairs same-line erDiagram starters and quoted cardinalities", async () => {
    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={
          'erDiagram| Document | | --o{ Chunk : contains\nCollection "1" -- "many" Document : groups'
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("repairs same-line erDiagram starters without whitespace", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={"erDiagramDOCUMENT ||--o{ CHUNK : contains"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain("erDiagram\nDOCUMENT ||--o{ CHUNK : contains");
  });

  it("repairs collapsed erDiagram relations on one line", async () => {
    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={
          "erDiagram\nDocument }o--|| Collection : belongsTo |Collection ||--|{ Chunk : contains"
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("repairs pipe-wrapped erDiagram pseudo-table relations", async () => {
    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={
          "erDiagram\n| Document |  | --o{ Collection : belongsTo |\n| Collection |  | -- | { User : managedBy |"
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("repairs malformed classDiagram relation cardinalities", async () => {
    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={
          'classDiagram\nDocument "1" -- "o" Collection "1"\nChunk "1" -- "o" Document "1"\nQuery "1" -- "o" Collection "1"'
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("repairs classDiagram generic attributes and many cardinality", async () => {
    const renderMock = vi.mocked(mermaid.render);
    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={
          'classDiagram\nclass Collection {\n  +list<Document>\n}\nCollection "1" -- "many" Document : contains'
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });
    expect(container.querySelector("svg")).toBeTruthy();
    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain('Collection "1" -- "*" Document : contains');
    expect(renderCall?.[1]).not.toContain("+list<Document>");
  });

  it("drops association-like generic field types in classDiagram attributes", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={"classDiagram\nclass Collection {\n  +list<Document> documents\n}"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).not.toContain("+list<Document> documents");
  });

  it("wraps detached class members into Mermaid class blocks", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={
          'classDiagram\nQuery\n+string id\n+string text\n+string collectionId\nCollection\n+string id\n+string name\nQuery "1" --> "*" Collection : relatesTo'
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain("class Query {");
    expect(renderCall?.[1]).toContain("class Collection {");
    expect(renderCall?.[1]).toContain("+collectionId: string");
    expect(renderCall?.[1]).not.toContain("\nQuery\n+string id");
  });

  it("canonicalizes malformed class member declarations", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={
          "classDiagram\nclass Query {\n  +string id\n  -UUID queryId\n  #List<Document> documents\n}"
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain("+id: string");
    expect(renderCall?.[1]).toContain("-queryId: UUID");
    expect(renderCall?.[1]).toContain("#documents: List~Document~");
  });

  it("injects only minimal color styles for class diagrams", async () => {
    const renderMock = vi.mocked(mermaid.render);
    renderMock.mockResolvedValueOnce({
      diagramType: "classDiagram",
      svg: `
        <svg>
          <g class="classGroup">
            <text class="classTitle"><tspan>Document</tspan></text>
            <text class="classText"><tspan>+String id</tspan></text>
          </g>
        </svg>
      `,
    });

    const { container } = render(
      <CodeBlock
        language="mermaid"
        value={"classDiagram\nclass Document {\n  +String id\n}"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    await waitFor(() => {
      expect(container.querySelector('[data-testid="diagram-stage"] svg')).toBeTruthy();
    });

    const svgMarkup = container.querySelector('[data-testid="diagram-stage"] svg')?.outerHTML ?? "";
    expect(svgMarkup).toContain("<style>");
    expect(svgMarkup).toContain(".classTitle");
    expect(svgMarkup).toContain("fill: #f8fafc");
    expect(svgMarkup).not.toContain("dominant-baseline: hanging");
    expect(svgMarkup).not.toContain("font-size:");
    expect(svgMarkup).not.toContain("font-weight:");
  });

  it("keeps class diagrams on Mermaid default font metrics", async () => {
    const initializeMock = vi.mocked(mermaid.initialize);

    render(
      <CodeBlock
        language="mermaid"
        value={"classDiagram\nclass Document {\n  +String id\n}\nclass Chunk {\n  +String id\n}"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    const initializeCall = initializeMock.mock.calls.at(-1)?.[0] as
      | Record<string, unknown>
      | undefined;
    expect(initializeCall?.fontFamily).toBeUndefined();
    const themeVariables = initializeCall?.themeVariables as Record<string, unknown> | undefined;
    expect(themeVariables?.fontSize).toBeUndefined();
  });

  it("preserves scalar generic field types in classDiagram attributes", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={"classDiagram\nclass Collection {\n  +list<string> tags\n}"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain("+tags: list~string~");
  });

  it("simplifies punctuation-heavy mindmap labels before rendering", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={
          "mindmap\n  root(Unit 2: Random Variables)\n    Definition: Rule/function assigning outcomes\n    Kim, A. (2019). Exponential Distribution"
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain("root(Unit 2 Random Variables)");
    expect(renderCall?.[1]).toContain("Definition Rule/function assigning outcomes");
    expect(renderCall?.[1]).toContain("Kim A 2019 Exponential Distribution");
  });

  it("adds a single root to malformed mindmaps", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={"mindmap\nIntroduction\nBackground\nKey Ideas"}
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain("root((Introduction))");
    expect(renderCall?.[1]).toContain("    Background");
    expect(renderCall?.[1]).toContain("    Key Ideas");
  });

  it("repairs malformed journey tasks into Mermaid journey taskData", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={
          "journey\ntitle User Document Interaction Journey\nsection Upload\nUser uploads a document: $start$\n-> Upload complete"
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain("User uploads a document: 5: User");
    expect(renderCall?.[1]).toContain("Upload complete: 5: System");
  });

  it("simplifies journey labels before rendering", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <CodeBlock
        language="mermaid"
        value={
          "journey\ntitle Document workflow: upload, query, export\nsection Review & export\n  Review evidence, compare answer: 5: User, Analyst"
        }
        incomplete={false}
        enableRichPreview={true}
      />,
    );

    fireEvent.click(screen.getByTitle(/view diagram/i));
    await screen.findByRole("button", { name: "Hide View" });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain("title Document workflow upload query export");
    expect(renderCall?.[1]).toContain("section Review and export");
    expect(renderCall?.[1]).toContain("Review evidence compare answer: 5: User Analyst");
  });

  it("fits class diagrams to visible content instead of a padded svg canvas", async () => {
    const renderMock = vi.mocked(mermaid.render);
    renderMock.mockResolvedValueOnce({
      diagramType: "classDiagram",
      svg: `
        <svg viewBox="0 0 2400 1400" width="2400" height="1400">
          <g class="diagram-root">
            <rect class="classBox" x="100" y="120" width="320" height="180"></rect>
          </g>
        </svg>
      `,
    });

    const clientWidthDescriptor = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "clientWidth",
    );
    const clientHeightDescriptor = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "clientHeight",
    );
    const getBBoxDescriptor = Object.getOwnPropertyDescriptor(SVGElement.prototype, "getBBox");

    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get: () => 640,
    });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get: () => 760,
    });
    Object.defineProperty(SVGElement.prototype, "getBBox", {
      configurable: true,
      value: function getBBox() {
        const tagName = this.tagName?.toLowerCase();
        if (tagName === "rect") {
          return { x: 100, y: 120, width: 320, height: 180 };
        }
        if (tagName === "svg") {
          return { x: 0, y: 0, width: 2400, height: 1400 };
        }
        return { x: 100, y: 120, width: 320, height: 180 };
      },
    });

    try {
      const { container } = render(
        <CodeBlock
          language="mermaid"
          value={'classDiagram\nclass Document\nclass Chunk\nDocument "1" -- "*" Chunk : contains'}
          incomplete={false}
          enableRichPreview={true}
        />,
      );

      fireEvent.click(screen.getByTitle(/view diagram/i));
      await screen.findByRole("button", { name: "Hide View" });

      await waitFor(() => {
        const stage = container.querySelector(
          '[style*="transform: translate"]',
        ) as HTMLElement | null;
        expect(stage).toBeTruthy();
        const transform = stage?.style.transform ?? "";
        const scaleMatch = transform.match(/scale\(([^)]+)\)/);
        expect(scaleMatch).toBeTruthy();
        expect(Number(scaleMatch?.[1] ?? "0")).toBeGreaterThan(1.5);
      });
    } finally {
      if (clientWidthDescriptor) {
        Object.defineProperty(HTMLElement.prototype, "clientWidth", clientWidthDescriptor);
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, "clientWidth");
      }

      if (clientHeightDescriptor) {
        Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor);
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, "clientHeight");
      }

      if (getBBoxDescriptor) {
        Object.defineProperty(SVGElement.prototype, "getBBox", getBBoxDescriptor);
      } else {
        Reflect.deleteProperty(SVGElement.prototype, "getBBox");
      }
    }
  });

  it("renders a graph-json diagram block", async () => {
    render(
      <StructuredBlockRenderer
        blocks={[
          {
            id: "diagram-2",
            type: "diagram",
            title: "Service Graph",
            diagram_type: "graph_canvas",
            source: "graph_json",
            syntax: "",
            description: "High-level service graph.",
            graph: {
              layout: "horizontal",
              nodes: [
                { id: "client", label: "Client", category: "edge" },
                { id: "api", label: "API", category: "service" },
              ],
              edges: [{ source: "client", target: "api", label: "request" }],
            },
          },
        ]}
      />,
    );

    expect(screen.getByText("Service Graph")).toBeInTheDocument();
    expect(screen.getByText("High-level service graph.")).toBeInTheDocument();
    expect(screen.getByText(/graph structure is ready/i)).toBeInTheDocument();
    fireEvent.click(screen.getByTitle(/view diagram/i));
    expect((await screen.findAllByText("Client")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("API").length).toBeGreaterThan(0);
  });

  it("renders structured mermaid diagram blocks through the shared code-block pipeline", async () => {
    const renderMock = vi.mocked(mermaid.render);

    render(
      <StructuredBlockRenderer
        blocks={[
          {
            id: "diagram-mermaid-1",
            type: "diagram",
            title: "Journey",
            diagram_type: "mermaid_journey",
            source: "mermaid",
            syntax:
              "journey\ntitle User Document Interaction Journey\nsection Upload\nUser uploads a document: $start$\n-> Upload complete",
            description: "User workflow",
          },
        ]}
      />,
    );

    expect(screen.getByText("Journey")).toBeInTheDocument();
    fireEvent.click(screen.getByTitle(/view diagram/i));
    await waitFor(() => {
      expect(renderMock).toHaveBeenCalled();
    });

    const renderCall = renderMock.mock.calls.at(-1);
    expect(renderCall?.[1]).toContain("User uploads a document: 5: User");
    expect(renderCall?.[1]).toContain("Upload complete: 5: System");
  });

  it("opens structured mermaid blocks in preview mode by default", async () => {
    render(
      <DiagramBlock
        block={{
          id: "diagram-mermaid-open",
          type: "diagram",
          title: "Mindmap",
          diagram_type: "mermaid_mindmap",
          source: "mermaid",
          syntax: "mindmap\nIntroduction\nBackground\nKey Ideas",
          description: "Auto-open preview",
        }}
      />,
    );

    expect(await screen.findByRole("button", { name: "Hide View" })).toBeInTheDocument();
  });

  it("keeps mermaid preview closed after the user clicks hide view", async () => {
    render(
      <DiagramBlock
        block={{
          id: "diagram-mermaid-hide",
          type: "diagram",
          title: "Flowchart",
          diagram_type: "mermaid_flowchart",
          source: "mermaid",
          syntax: "flowchart LR\nA --> B",
          description: "Hideable preview",
        }}
      />,
    );

    const hideButton = await screen.findByRole("button", { name: "Hide View" });
    fireEvent.click(hideButton);

    expect(screen.getByTestId("highlighted-code-block")).toHaveTextContent(/flowchart LR/i);
    expect(screen.getByRole("button", { name: "View" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hide View" })).not.toBeInTheDocument();
  });

  it("keeps inline mermaid source visible while streaming", () => {
    render(
      <CodeBlock
        language="mermaid"
        value={"flowchart LR\nA -->"}
        incomplete={true}
        enableRichPreview={true}
      />,
    );

    expect(screen.getByTestId("highlighted-code-block")).toHaveTextContent(/flowchart LR/i);
    expect(screen.getByTitle(/view diagram/i)).toBeDisabled();
  });

  it("keeps query-page code blocks as plain mermaid source when rich preview is disabled", () => {
    render(
      <CodeBlock
        language="mermaid"
        value={"flowchart LR\nA --> B"}
        incomplete={false}
        enableRichPreview={false}
      />,
    );

    expect(screen.getByTestId("highlighted-code-block")).toHaveTextContent(/flowchart LR/i);
    expect(screen.queryByTitle(/expand diagram/i)).not.toBeInTheDocument();
  });
});
