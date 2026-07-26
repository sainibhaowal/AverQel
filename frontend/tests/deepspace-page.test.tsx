import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import type { MockInstance } from "vitest";
import { afterEach, beforeEach, vi } from "vitest";

import DeepSpacePageClient from "../app/dashboard/deepspace/_components/DeepSpacePageClient";
import DeepSpaceThread from "../app/dashboard/deepspace/_components/DeepSpaceThread";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: Parameters<typeof fetchWithAuthMock>) => fetchWithAuthMock(...args),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceChatClient", () => ({
  default: ({ onInsertLatestAnswer }: { onInsertLatestAnswer?: (content: string) => void }) => (
    <div>
      <div>Mock DeepSpace Chat</div>
      <button
        aria-label="Insert latest answer"
        onClick={() => onInsertLatestAnswer?.("DeepSpace answer for the draft.")}
      >
        Insert Mock Answer
      </button>
    </div>
  ),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceEditor", () => {
  return {
    __esModule: true,
    default: React.forwardRef(function MockDeepSpaceEditor(
      {
        initialContent,
        onChange,
      }: {
        initialContent?: string;
        onChange?: (html: string) => void;
      },
      ref: React.ForwardedRef<{ insertMarkdown: (content: string) => void }>,
    ) {
      const [content, setContent] = React.useState(initialContent ?? "");

      React.useImperativeHandle(ref, () => ({
        insertMarkdown(markdown: string) {
          setContent(markdown);
          onChange?.(markdown);
        },
      }));

      return (
        <textarea
          aria-label="Writing canvas editor"
          value={content}
          onChange={(event) => {
            setContent(event.target.value);
            onChange?.(event.target.value);
          }}
        />
      );
    }),
  };
});

let observedWidth = 1280;
let boundingRectSpy: MockInstance | null = null;

class ResizeObserverMock {
  private readonly callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(target: Element) {
    this.callback(
      [
        {
          target,
          contentRect: {
            width: observedWidth,
            height: 900,
            x: 0,
            y: 0,
            top: 0,
            left: 0,
            bottom: 900,
            right: observedWidth,
            toJSON: () => ({}),
          },
        } as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }

  unobserve() {}

  disconnect() {}
}

describe("deepspace page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockImplementation(async (endpoint: string, options?: RequestInit) => {
      if (endpoint === "/deepspace/chats" && !options?.method) {
        return {
          ok: true,
          json: async () => ({ items: [] }),
        } satisfies Partial<Response>;
      }

      if (endpoint === "/deepspace/chats" && options?.method === "POST") {
        return {
          ok: true,
          json: async () => ({
            id: "note-1",
            title: "Untitled Note",
            updated_at: new Date().toISOString(),
            content_html: "",
          }),
        } satisfies Partial<Response>;
      }

      if (endpoint === "/deepspace/chats/note-1" && options?.method === "PATCH") {
        return {
          ok: true,
          json: async () => ({}),
        } satisfies Partial<Response>;
      }

      throw new Error(`Unhandled fetchWithAuth call: ${endpoint} (${options?.method ?? "GET"})`);
    });

    observedWidth = 1280;
    boundingRectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
      () =>
        ({
          width: observedWidth,
          height: 900,
          top: 0,
          left: 0,
          right: observedWidth,
          bottom: 900,
          x: 0,
          y: 0,
          toJSON: () => ({}),
        }) as DOMRect,
    );
    window.innerWidth = observedWidth;
    Object.defineProperty(window, "visualViewport", {
      configurable: true,
      writable: true,
      value: {
        width: observedWidth,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    });

    Object.defineProperty(window, "ResizeObserver", {
      configurable: true,
      writable: true,
      value: ResizeObserverMock,
    });
    Object.defineProperty(globalThis, "ResizeObserver", {
      configurable: true,
      writable: true,
      value: ResizeObserverMock,
    });
  });

  afterEach(() => {
    boundingRectSpy?.mockRestore();
    fetchWithAuthMock.mockReset();
  });

  it("renders the split deepspace shell", async () => {
    window.innerWidth = 1280;
    Object.defineProperty(window, "visualViewport", {
      configurable: true,
      writable: true,
      value: {
        width: 1280,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    });
    window.dispatchEvent(new Event("resize"));

    render(<DeepSpacePageClient />);

    expect(await screen.findByLabelText(/writing canvas editor/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/writing canvas editor/i)).toBeInTheDocument();
    expect(screen.getByText(/mock deepspace chat/i)).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: /resize deepspace panels/i })).toBeInTheDocument();
  });

  it("switches to a stacked layout when the available width gets narrow", async () => {
    observedWidth = 900;
    window.innerWidth = 900;
    Object.defineProperty(window, "visualViewport", {
      configurable: true,
      writable: true,
      value: {
        width: 900,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    });
    window.dispatchEvent(new Event("resize"));

    render(<DeepSpacePageClient />);

    // separator is hidden in stacked layout
    expect(
      screen.queryByRole("separator", { name: /resize deepspace panels/i }),
    ).not.toBeInTheDocument();
  });

  it(
    "compacts long deep space threads and reveals older messages in batches",
    { timeout: 10000 },
    () => {
      const longMessages = Array.from({ length: 60 }, (_, index) => ({
        id: `msg-${index + 1}`,
        role: (index % 2 === 0 ? "user" : "assistant") as "user" | "assistant",
        content: `Message ${index + 1}`,
        rawContent: `Message ${index + 1}`,
        createdAt: new Date().toISOString(),
        status: "ready" as const,
      }));

      render(
        <DeepSpaceThread
          messages={longMessages}
          emptyPrompts={[]}
          onPromptSelect={() => {}}
          onInsertLatestAnswer={() => {}}
        />,
      );

      expect(screen.getByText(/showing the most recent 14 of 60 messages/i)).toBeInTheDocument();
      expect(screen.queryByText(/^Message 1$/)).not.toBeInTheDocument();
      expect(screen.getByText("Message 47")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /load older messages/i }));

      expect(screen.getByText(/showing the most recent 34 of 60 messages/i)).toBeInTheDocument();
      expect(screen.getByText(/^Message 27$/)).toBeInTheDocument();
      expect(screen.queryByText(/^Message 1$/)).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /load older messages/i }));

      expect(screen.getByText(/showing the most recent 54 of 60 messages/i)).toBeInTheDocument();
      expect(screen.queryByText(/^Message 1$/)).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /load older messages/i }));

      expect(screen.queryByText(/showing the most recent/i)).not.toBeInTheDocument();
      expect(screen.getByText(/^Message 1$/)).toBeInTheDocument();
    },
  );

  it("inserts assistant output into the draft", async () => {
    render(<DeepSpacePageClient />);

    await screen.findByLabelText(/writing canvas editor/i);
    fireEvent.click(screen.getByRole("button", { name: /insert latest answer/i }));

    expect(
      await screen.findByDisplayValue(/deepspace answer for the draft\./i),
    ).toBeInTheDocument();
  });

  it("renders assistant markdown content in deepspace", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_1",
            role: "assistant",
            content: "## Heading\n\n| A | B |\n| --- | --- |\n| 1 | 2 |",
            rawContent: "## Heading\n\n| A | B |\n| --- | --- |\n| 1 | 2 |",
            createdAt: new Date().toISOString(),
            status: "ready",
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("renders an explicit chart fence as a chart block in deepspace", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_chart_1",
            role: "assistant",
            content:
              'Trend summary.\n\n```chart\n{"chart_type":"line","title":"Chart Data","series":[{"label":"Jan","value":10},{"label":"Feb","value":12},{"label":"Mar","value":18}]}\n```\n',
            rawContent:
              'Trend summary.\n\n```chart\n{"chart_type":"line","title":"Chart Data","series":[{"label":"Jan","value":10},{"label":"Feb","value":12},{"label":"Mar","value":18}]}\n```\n',
            createdAt: new Date().toISOString(),
            status: "ready",
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByText("Trend summary.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Chart Data" })).toBeInTheDocument();
    expect(screen.getByText(/3 points/i)).toBeInTheDocument();
    expect(screen.getByText(/json/i)).toBeInTheDocument();
    expect(screen.queryByText(/No diagram type detected/i)).not.toBeInTheDocument();
  });

  it("renders chart fences independently from Mermaid diagrams in deepspace", () => {
    render(
      <DeepSpaceThread
        messages={[
          {
            id: "assistant_chart_mermaid_1",
            role: "assistant",
            content:
              'Trend view\n\n```chart\n{"chart_type":"line","title":"Monthly Sales Trend","series":[{"label":"2023-01","value":150},{"label":"2023-02","value":175},{"label":"2023-03","value":200},{"label":"2023-04","value":225},{"label":"2023-05","value":210}]}\n```\n',
            rawContent:
              'Trend view\n\n```chart\n{"chart_type":"line","title":"Monthly Sales Trend","series":[{"label":"2023-01","value":150},{"label":"2023-02","value":175},{"label":"2023-03","value":200},{"label":"2023-04","value":225},{"label":"2023-05","value":210}]}\n```\n',
            createdAt: new Date().toISOString(),
            status: "ready",
          },
        ]}
        emptyPrompts={[]}
        onPromptSelect={() => {}}
        onInsertLatestAnswer={() => {}}
      />,
    );

    expect(screen.getByText("Trend view")).toBeInTheDocument();
    expect(screen.queryByText(/No diagram type detected/i)).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Monthly Sales Trend/i })).toBeInTheDocument();
    expect(screen.getByText(/5 points/i)).toBeInTheDocument();
    expect(screen.getAllByText(/line/i).length).toBeGreaterThan(0);
  });
});
