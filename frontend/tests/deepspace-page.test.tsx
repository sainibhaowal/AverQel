import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { MockInstance } from "vitest";
import { afterEach, beforeEach, vi } from "vitest";

import DeepSpacePageClient from "../app/dashboard/deepspace/_components/DeepSpacePageClient";
import DeepSpaceThread from "../app/dashboard/deepspace/_components/DeepSpaceThread";
import {
  noteDraftStorageKey,
  writeDeepSpaceNoteDraft,
} from "../app/dashboard/deepspace/_lib/note-drafts";

const fetchWithAuthMock = vi.fn();
let serverNotes: Array<{
  id: string;
  title: string;
  updated_at: string;
  content_html: string;
}> = [];
let failNotePatch = false;
let mismatchNotePatch = false;

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: Parameters<typeof fetchWithAuthMock>) => fetchWithAuthMock(...args),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceChatClient", () => ({
  default: ({
    onInsertLatestAnswer,
    onSelectNote,
  }: {
    onInsertLatestAnswer?: (content: string) => void;
    onSelectNote?: (noteId: string) => void;
  }) => (
    <div>
      <div>Mock DeepSpace Chat</div>
      <button onClick={() => onSelectNote?.("note-2")}>Select second note</button>
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
        conversationId,
        onChange,
        saveStatus,
        onRetrySave,
      }: {
        initialContent?: string;
        conversationId?: string;
        onChange?: (html: string) => void;
        saveStatus?: "idle" | "saving" | "saved" | "local" | "failed";
        onRetrySave?: () => void;
      },
      ref: React.ForwardedRef<{
        insertMarkdown: (content: string) => void;
        replaceHTML: (content: string) => Promise<void>;
      }>,
    ) {
      const [content, setContent] = React.useState(initialContent ?? "");
      React.useEffect(() => setContent(initialContent ?? ""), [conversationId, initialContent]);

      React.useImperativeHandle(ref, () => ({
        insertMarkdown(markdown: string) {
          setContent(markdown);
          onChange?.(markdown);
        },
        async replaceHTML(html: string) {
          setContent(html);
          onChange?.(html);
        },
      }));

      return (
        <>
          {saveStatus && saveStatus !== "idle" ? (
            <div role="status" data-testid="mock-note-save-status">
              {saveStatus === "local"
                ? "Saved on this tab"
                : saveStatus === "failed"
                  ? "Save failed"
                  : saveStatus === "saved"
                    ? "Saved"
                    : "Saving"}
              {(saveStatus === "local" || saveStatus === "failed") && onRetrySave ? (
                <button type="button" onClick={onRetrySave}>
                  Retry note save
                </button>
              ) : null}
            </div>
          ) : null}
          <textarea
            aria-label="Writing canvas editor"
            value={content}
            onChange={(event) => {
              setContent(event.target.value);
              onChange?.(event.target.value);
            }}
          />
        </>
      );
    }),
  };
});

let observedWidth = 1280;
let boundingRectSpy: MockInstance | null = null;
let headerControls: HTMLDivElement | null = null;

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
    serverNotes = [];
    failNotePatch = false;
    mismatchNotePatch = false;
    fetchWithAuthMock.mockImplementation(async (endpoint: string, options?: RequestInit) => {
      if (endpoint === "/deepspace/chats" && !options?.method) {
        return {
          ok: true,
          json: async () => ({ items: serverNotes }),
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

      if (endpoint.startsWith("/deepspace/chats/") && options?.method === "PATCH") {
        if (failNotePatch) {
          return {
            ok: false,
            status: 503,
            json: async () => ({}),
          } satisfies Partial<Response>;
        }
        if (mismatchNotePatch) {
          return {
            ok: true,
            json: async () => ({
              title: "Research note",
              content_html: "<p>Old response body</p>",
              updated_at: "2026-10-23T12:00:01.000Z",
            }),
          } satisfies Partial<Response>;
        }
        const conversationId = endpoint.slice("/deepspace/chats/".length);
        const body = JSON.parse(String(options.body ?? "{}")) as {
          title?: string;
          content_html?: string;
        };
        serverNotes = serverNotes.map((note) =>
          note.id === conversationId
            ? {
                ...note,
                ...body,
                updated_at: "2026-10-23T12:00:01.000Z",
              }
            : note,
        );
        return {
          ok: true,
          json: async () => serverNotes.find((note) => note.id === conversationId) ?? {},
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
    headerControls = document.createElement("div");
    headerControls.id = "header-layout-controls";
    document.body.append(headerControls);
  });

  afterEach(() => {
    boundingRectSpy?.mockRestore();
    fetchWithAuthMock.mockReset();
    headerControls?.remove();
    headerControls = null;
    window.sessionStorage.clear();
  });

  it("enters and exits the split shell without changing the active workspace", async () => {
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

    fireEvent.click(await screen.findByRole("button", { name: /notes/i }));
    expect(await screen.findByLabelText(/writing canvas editor/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/writing canvas editor/i)).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: /split view/i }));
    expect(screen.getByText(/mock deepspace chat/i)).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: /resize deepspace panels/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /split view/i }));
    await waitFor(() => expect(screen.queryByText(/mock deepspace chat/i)).not.toBeInTheDocument());
    expect(screen.getByLabelText(/writing canvas editor/i)).toBeInTheDocument();
  });

  it(
    "recovers a failed autosave after reopening and clears the tab draft after the server saves it",
    { timeout: 12_000 },
    async () => {
      const serverNote = {
        id: "note-1",
        title: "Research note",
        updated_at: "2026-10-23T12:00:00.000Z",
        content_html: "<p>Original server copy</p>",
      };
      serverNotes = [serverNote];
      failNotePatch = true;

      const firstPage = render(<DeepSpacePageClient />);
      fireEvent.click(await screen.findByRole("button", { name: /notes/i }));
      const editor = await screen.findByLabelText(/writing canvas editor/i);
      fireEvent.change(editor, { target: { value: "Recovered research draft" } });

      await waitFor(() => {
        expect(window.sessionStorage.getItem(noteDraftStorageKey("note-1"))).toContain(
          "Recovered research draft",
        );
      });
      await waitFor(
        () =>
          expect(screen.getByTestId("mock-note-save-status")).toHaveTextContent(
            "Saved on this tab",
          ),
        { timeout: 5_000 },
      );
      firstPage.unmount();

      failNotePatch = false;
      render(<DeepSpacePageClient />);
      fireEvent.click(await screen.findByRole("button", { name: /notes/i }));

      expect(await screen.findByLabelText(/writing canvas editor/i)).toHaveValue(
        "Recovered research draft",
      );
      await waitFor(() =>
        expect(screen.getByTestId("mock-note-save-status")).toHaveTextContent("Saved"),
      );
      await waitFor(() => {
        expect(window.sessionStorage.getItem(noteDraftStorageKey("note-1"))).toBeNull();
      });
      expect(serverNotes[0]?.content_html).toBe("Recovered research draft");
    },
  );

  it("keeps the recovery draft when the authoritative save endpoint does not confirm", async () => {
    serverNotes = [
      {
        id: "note-1",
        title: "Research note",
        updated_at: "2026-10-23T12:00:00.000Z",
        content_html: "<p>Original server copy</p>",
      },
    ];
    failNotePatch = true;

    render(<DeepSpacePageClient />);
    fireEvent.click(await screen.findByRole("button", { name: /notes/i }));
    fireEvent.change(await screen.findByLabelText(/writing canvas editor/i), {
      target: { value: "Still waiting for confirmation" },
    });

    await waitFor(
      () =>
        expect(screen.getByTestId("mock-note-save-status")).toHaveTextContent("Saved on this tab"),
      { timeout: 5_000 },
    );
    expect(window.sessionStorage.getItem(noteDraftStorageKey("note-1"))).toContain(
      "Still waiting for confirmation",
    );
    expect(serverNotes[0]?.content_html).toBe("<p>Original server copy</p>");
  });

  it("does not mark a mismatched 2xx response as saved", async () => {
    serverNotes = [
      {
        id: "note-1",
        title: "Research note",
        updated_at: "2026-10-23T12:00:00.000Z",
        content_html: "<p>Original server copy</p>",
      },
    ];
    mismatchNotePatch = true;

    render(<DeepSpacePageClient />);
    fireEvent.click(await screen.findByRole("button", { name: /notes/i }));
    fireEvent.change(await screen.findByLabelText(/writing canvas editor/i), {
      target: { value: "Response did not contain this edit" },
    });

    await waitFor(
      () =>
        expect(screen.getByTestId("mock-note-save-status")).toHaveTextContent("Saved on this tab"),
      { timeout: 5_000 },
    );
    expect(window.sessionStorage.getItem(noteDraftStorageKey("note-1"))).toContain(
      "Response did not contain this edit",
    );
    expect(serverNotes[0]?.content_html).toBe("<p>Original server copy</p>");
  });

  it("restores an edit made just before a refresh cancels its debounce timer", async () => {
    serverNotes = [
      {
        id: "note-1",
        title: "Research note",
        updated_at: "2026-10-23T12:00:00.000Z",
        content_html: "<p>Original server copy</p>",
      },
    ];
    const firstPage = render(<DeepSpacePageClient />);
    fireEvent.click(await screen.findByRole("button", { name: /notes/i }));
    fireEvent.change(await screen.findByLabelText(/writing canvas editor/i), {
      target: { value: "Typed just before refresh" },
    });

    expect(window.sessionStorage.getItem(noteDraftStorageKey("note-1"))).toContain(
      "Typed just before refresh",
    );
    firstPage.unmount();

    render(<DeepSpacePageClient />);
    fireEvent.click(await screen.findByRole("button", { name: /notes/i }));
    expect(await screen.findByLabelText(/writing canvas editor/i)).toHaveValue(
      "Typed just before refresh",
    );
    await waitFor(() =>
      expect(screen.getByTestId("mock-note-save-status")).toHaveTextContent("Saved"),
    );
    expect(serverNotes[0]?.content_html).toBe("Typed just before refresh");
  });

  it("keeps pending saves independent when switching between notes", async () => {
    serverNotes = [
      {
        id: "note-1",
        title: "First note",
        updated_at: "2026-10-23T12:00:00.000Z",
        content_html: "<p>First server copy</p>",
      },
      {
        id: "note-2",
        title: "Second note",
        updated_at: "2026-10-23T12:00:00.000Z",
        content_html: "<p>Second server copy</p>",
      },
    ];
    window.localStorage.setItem("averqel_deepspace_active_conversation", "note-1");
    render(<DeepSpacePageClient />);
    fireEvent.click(await screen.findByRole("button", { name: /notes/i }));
    fireEvent.change(await screen.findByLabelText(/writing canvas editor/i), {
      target: { value: "First note edit" },
    });
    expect(window.sessionStorage.getItem(noteDraftStorageKey("note-1"))).toContain(
      "First note edit",
    );

    fireEvent.click(await screen.findByRole("button", { name: /split view/i }));
    fireEvent.click(await screen.findByRole("button", { name: /select second note/i }));
    const editor = await screen.findByLabelText(/writing canvas editor/i);
    await waitFor(() => expect(editor).toHaveValue("<p>Second server copy</p>"));
    fireEvent.change(editor, { target: { value: "Second note edit" } });
    expect(window.sessionStorage.getItem(noteDraftStorageKey("note-2"))).toContain(
      "Second note edit",
    );

    await waitFor(
      () => {
        expect(serverNotes.find((note) => note.id === "note-1")?.content_html).toBe(
          "First note edit",
        );
        expect(serverNotes.find((note) => note.id === "note-2")?.content_html).toBe(
          "Second note edit",
        );
      },
      { timeout: 5_000 },
    );
  });

  it("asks before restoring a local draft over a newer server note", async () => {
    serverNotes = [
      {
        id: "note-1",
        title: "Research note",
        updated_at: "2026-10-23T12:00:02.000Z",
        content_html: "<p>Newer server copy</p>",
      },
    ];
    writeDeepSpaceNoteDraft(window.sessionStorage, {
      version: 1,
      conversationId: "note-1",
      contentHtml: "Older local draft",
      title: "Research note",
      baseUpdatedAt: "2026-10-23T12:00:00.000Z",
      updatedAt: Date.now(),
    });

    render(<DeepSpacePageClient />);
    fireEvent.click(await screen.findByRole("button", { name: /notes/i }));
    expect(await screen.findByLabelText(/writing canvas editor/i)).toHaveValue(
      "<p>Newer server copy</p>",
    );
    expect(screen.getByLabelText(/writing canvas editor/i).closest("[inert]")).not.toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent(/local draft and the saved note differ/i);
    expect(
      fetchWithAuthMock.mock.calls.some(
        ([endpoint, options]) =>
          endpoint === "/deepspace/chats/note-1" && options?.method === "PATCH",
      ),
    ).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /restore local draft/i }));
    await waitFor(() =>
      expect(screen.getByLabelText(/writing canvas editor/i)).toHaveValue("Older local draft"),
    );
    expect(screen.getByLabelText(/writing canvas editor/i).closest("[inert]")).toBeNull();
    await waitFor(() =>
      expect(screen.getByTestId("mock-note-save-status")).toHaveTextContent("Saved"),
    );
    expect(serverNotes[0]?.content_html).toBe("Older local draft");
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

    fireEvent.click(await screen.findByRole("button", { name: /notes/i }));
    await screen.findByLabelText(/writing canvas editor/i);
    fireEvent.click(await screen.findByRole("button", { name: /split view/i }));
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
    expect(screen.getByRole("button", { name: "Export chart source as JSON" })).toBeInTheDocument();
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
