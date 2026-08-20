"use client";

import {
  useCreateBlockNote,
  SuggestionMenuController,
  getDefaultReactSlashMenuItems,
} from "@blocknote/react";
import { Link } from "@tiptap/extension-link";
import { BlockNoteView, darkDefaultTheme, lightDefaultTheme } from "@blocknote/mantine";
import "@blocknote/mantine/style.css";
import { forwardRef, useImperativeHandle, useEffect, useRef, useState } from "react";
import {
  FileEdit,
  Sigma,
  Download,
  FileText,
  Loader2,
  Columns2,
  PanelLeftClose,
  PanelRightClose,
  Maximize2,
  Save,
} from "lucide-react";
import {
  BlockNoteSchema,
  defaultBlockSpecs,
  insertOrUpdateBlockForSlashMenu,
  filterSuggestionItems,
} from "@blocknote/core";
import { fetchWithAuth } from "@/lib/api";
import { useTheme } from "@/app/context/ThemeContext";
import { MathBlock } from "./MathBlock";
import DeepSpaceMarkdownRenderer from "./DeepSpaceMarkdownRenderer";

export interface DeepSpaceAgentNotePreview {
  markdown: string;
  mode: "replace" | "append";
  status: "streaming" | "failed" | "conflict";
}

export interface DeepSpaceEditorHandle {
  insertHTML: (html: string) => Promise<void>;
  insertMarkdown: (markdown: string) => Promise<void>;
  getHTML: () => Promise<string>;
  getMarkdown: () => Promise<string>;
  replaceHTML: (html: string) => Promise<void>;
  clear: () => void;
}

export interface DeepSpaceEditorProps {
  initialContent?: string;
  onChange?: (html: string) => void;
  conversationId?: string;
  isSaving?: boolean;
  onCollapseChat?: () => void;
  chatVisible?: boolean;
  showCollapseControls?: boolean;
  panelMode?: "split" | "notes" | "chat" | "memory";
  onSetPanelMode?: (mode: "split" | "notes" | "chat" | "memory") => void;
  agentPreview?: DeepSpaceAgentNotePreview | null;
}

const getCustomTheme = (theme: "light" | "dark") => {
  const baseTheme = theme === "dark" ? darkDefaultTheme : lightDefaultTheme;
  return {
    ...baseTheme,
    colors: {
      ...baseTheme.colors,
      editor: {
        text: theme === "dark" ? "#ffffff" : "#020617",
        background: "transparent",
      },
    },
  };
};

const schema = BlockNoteSchema.create({
  blockSpecs: {
    ...defaultBlockSpecs,
    math: MathBlock(),
  },
});

// Create a custom Slash Menu item for Math
type SlashMenuEditor = Parameters<typeof getDefaultReactSlashMenuItems>[0];

const getCustomSlashMenuItems = (editor: unknown) => [
  ...getDefaultReactSlashMenuItems(editor as SlashMenuEditor),
  {
    title: "Math Equation",
    onItemClick: () => {
      insertOrUpdateBlockForSlashMenu(editor as SlashMenuEditor, {
        type: "math",
        props: { formula: "e = mc^2" } as never,
      });
    },
    aliases: ["math", "equation", "katex", "latex"],
    group: "Advanced",
    icon: <Sigma size={16} />,
    hint: "Insert a LaTeX mathematical equation",
  },
];

const DeepSpaceEditor = forwardRef<DeepSpaceEditorHandle, DeepSpaceEditorProps>(
  (
    {
      initialContent = "",
      onChange,
      conversationId,
      isSaving,
      onCollapseChat,
      chatVisible,
      showCollapseControls = true,
      panelMode,
      onSetPanelMode,
      agentPreview,
    },
    ref,
  ) => {
    const { theme } = useTheme();
    const [isExporting, setIsExporting] = useState(false);
    const [exportMessage, setExportMessage] = useState<string | null>(null);
    const [showWidthMenu, setShowWidthMenu] = useState(false);
    const [showExportMenu, setShowExportMenu] = useState(false);
    const [showLibrarySave, setShowLibrarySave] = useState(false);
    const [libraryFilename, setLibraryFilename] = useState("untitled.md");
    const [librarySaveState, setLibrarySaveState] = useState<"idle" | "saving" | "saved" | "error">(
      "idle",
    );
    const [librarySaveMessage, setLibrarySaveMessage] = useState("");
    const [marginSize, setMarginSize] = useState<"narrow" | "medium" | "wide" | "full">("medium");
    const marginClasses = {
      narrow: "max-w-[600px] px-4 sm:px-8 lg:px-24",
      medium: "max-w-[900px] px-4 sm:px-8 lg:px-16",
      wide: "max-w-[1200px] px-4 sm:px-6 lg:px-8",
      full: "max-w-none px-4 sm:px-4 lg:px-6",
    };

    void onCollapseChat;
    void chatVisible;
    const editor = useCreateBlockNote({
      schema,
      // Keep BlockNote links/autolinking, but avoid its duplicate custom
      // protocol registration after linkifyjs has already initialized.
      disableExtensions: ["link"],
      _tiptapOptions: {
        extensions: [Link.configure({ protocols: [] })],
      },
    });
    const loadedConversationIdRef = useRef<string | undefined>(undefined);

    useEffect(() => {
      let cancelled = false;
      const loadInitial = async () => {
        // The editor component stays mounted while users switch notes.  Load
        // each conversation once by ID, rather than relying on the document
        // length, so the previous note never remains visible in a new note.
        if (conversationId && loadedConversationIdRef.current === conversationId) return;
        const blocks = initialContent ? await editor.tryParseHTMLToBlocks(initialContent) : [];
        if (cancelled) return;
        editor.replaceBlocks(editor.document, blocks);
        loadedConversationIdRef.current = conversationId;
      };
      void loadInitial();
      return () => {
        cancelled = true;
      };
    }, [conversationId, editor, initialContent]);

    useEffect(() => {
      if (!showWidthMenu && !showExportMenu) return;

      const closeMenus = (event: PointerEvent) => {
        const target = event.target;
        if (target instanceof Element && target.closest("[data-deepspace-toolbar-menu]")) return;
        setShowWidthMenu(false);
        setShowExportMenu(false);
      };
      const closeOnEscape = (event: KeyboardEvent) => {
        if (event.key === "Escape") {
          setShowWidthMenu(false);
          setShowExportMenu(false);
        }
      };

      document.addEventListener("pointerdown", closeMenus);
      document.addEventListener("keydown", closeOnEscape);
      return () => {
        document.removeEventListener("pointerdown", closeMenus);
        document.removeEventListener("keydown", closeOnEscape);
      };
    }, [showExportMenu, showWidthMenu]);

    useImperativeHandle(ref, () => ({
      insertHTML: async (html: string) => {
        const blocks = await editor.tryParseHTMLToBlocks(html);
        editor.insertBlocks(blocks, editor.getTextCursorPosition().block, "after");
      },
      insertMarkdown: async (markdown: string) => {
        // Intelligent conversion of $$ math blocks to interactive MathBlocks
        const parts = markdown.split(/\$\$\s*([\s\S]*?)\s*\$\$/g);

        for (let i = 0; i < parts.length; i++) {
          const part = parts[i]?.trim();
          if (!part) continue;

          if (i % 2 === 1) {
            // This is a math block
            editor.insertBlocks(
              [
                {
                  type: "math",
                  props: { formula: part } as never,
                },
              ],
              editor.getTextCursorPosition().block,
              "after",
            );
          } else {
            // Regular text/markdown
            const blocks = await editor.tryParseMarkdownToBlocks(part);
            editor.insertBlocks(blocks, editor.getTextCursorPosition().block, "after");
          }
        }
      },
      getHTML: async () => {
        return await editor.blocksToHTMLLossy(editor.document);
      },
      getMarkdown: async () => {
        return await editor.blocksToMarkdownLossy(editor.document);
      },
      replaceHTML: async (html: string) => {
        const blocks = await editor.tryParseHTMLToBlocks(html);
        editor.replaceBlocks(editor.document, blocks);
      },
      clear: () => {
        editor.replaceBlocks(editor.document, []);
      },
    }));

    const handleExport = async (format: "pdf" | "docx" | "md") => {
      if (!conversationId) {
        setExportMessage("Save the workspace before exporting it.");
        return;
      }

      setIsExporting(true);
      setExportMessage(null);
      try {
        const response = await fetchWithAuth(
          `/deepspace/export/${conversationId}?format=${format}`,
        );
        if (!response.ok) {
          let message = "Export failed";
          try {
            const data = await response.clone().json();
            message = String(data?.detail?.error || data?.detail || message);
          } catch {
            // Keep the generic message for non-JSON export failures.
          }
          throw new Error(message);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `DeepSpace_Note_${conversationId.substring(0, 8)}.${format}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        // Keep the object URL alive until the browser has started the download.
        window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
      } catch (error) {
        console.error("Export error:", error);
        setExportMessage(
          error instanceof Error ? error.message : "Failed to export document. Please try again.",
        );
      } finally {
        setIsExporting(false);
      }
    };

    const saveToLibrary = async () => {
      const filename = libraryFilename.trim();
      if (!conversationId) {
        setLibrarySaveState("error");
        setLibrarySaveMessage("Save the workspace before creating a Library file.");
        return;
      }
      if (!filename.includes(".")) {
        setLibrarySaveState("error");
        setLibrarySaveMessage("Add a filename extension, for example study-plan.md.");
        return;
      }
      const extension = filename.split(".").pop()?.toLowerCase();
      const contentType =
        extension === "md"
          ? "text/markdown"
          : extension === "json"
            ? "application/json"
            : extension === "csv"
              ? "text/csv"
              : extension === "yaml" || extension === "yml"
                ? "application/yaml"
                : extension === "xml"
                  ? "application/xml"
                  : extension === "html" || extension === "htm"
                    ? "text/html"
                    : extension === "css"
                      ? "text/css"
                      : extension === "sql"
                        ? "text/sql"
                        : extension === "pdf"
                          ? "application/pdf"
                          : extension === "docx"
                            ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            : extension === "xlsx"
                              ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                              : extension === "zip"
                                ? "application/zip"
                                : extension === "svg"
                                  ? "image/svg+xml"
                                  : extension === "png"
                                    ? "image/png"
                                    : extension === "jpg" || extension === "jpeg"
                                      ? "image/jpeg"
                                      : extension === "webp"
                                        ? "image/webp"
                                        : extension === "mp4"
                                          ? "video/mp4"
                                          : extension === "webm"
                                            ? "video/webm"
                                            : extension === "mp3"
                                              ? "audio/mpeg"
                                              : extension === "py"
                                                ? "text/x-python"
                                                : extension === "js" || extension === "mjs"
                                                  ? "text/javascript"
                                                  : "text/plain";
      setLibrarySaveState("saving");
      setLibrarySaveMessage("");
      try {
        const content = await editor.blocksToMarkdownLossy(editor.document);
        const response = (await fetchWithAuth(`/deepspace/library/${conversationId}/files`, {
          method: "POST",
          body: JSON.stringify({ name: filename, content, content_type: contentType }),
        })) as Response;
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(
            String(payload?.error?.message ?? "A file with that name may already exist."),
          );
        }
        setLibrarySaveState("saved");
        setLibrarySaveMessage(`${filename} saved to DeepSpace Library.`);
        window.dispatchEvent(new CustomEvent("deepspace-library-changed"));
      } catch (error) {
        setLibrarySaveState("error");
        setLibrarySaveMessage(
          error instanceof Error ? error.message : "Could not save this file to the Library.",
        );
      }
    };

    return (
      <div className="flex h-full w-full flex-col overflow-visible bg-transparent">
        <div className="border-glass-border bg-surface-1/40 relative z-[80] flex shrink-0 flex-col gap-3 overflow-visible border-b p-3 shadow-sm backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <div className="border-glass-border bg-surface-2 text-primary mx-1 flex h-9 w-9 items-center justify-center rounded-xl border shadow-inner">
              <FileEdit size={16} />
            </div>
            {isSaving && (
              <div className="animate-in fade-in slide-in-from-left-2 flex items-center gap-2 px-3 py-1 duration-300">
                <Loader2 size={12} className="text-primary animate-spin" />
                <span className="text-primary/60 text-[10px] font-bold tracking-wider uppercase">
                  Saving
                </span>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              disabled={!conversationId}
              onClick={() => {
                setLibrarySaveState("idle");
                setLibrarySaveMessage("");
                setShowLibrarySave(true);
              }}
              aria-label="Save a named copy to DeepSpace Library"
              data-tooltip="Save a named copy to DeepSpace Library"
              className="ui-tooltip border-glass-border bg-surface-1 text-muted-foreground hover:border-primary/40 hover:bg-surface-2 hover:text-primary inline-flex h-9 items-center gap-2 rounded-xl border px-3.5 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-45"
            >
              <Save size={13} className="text-primary/75" /> Save to Library
            </button>
            {showCollapseControls && onSetPanelMode && (
              <div className="border-glass-border bg-surface-0/40 mr-2 flex items-center gap-1 rounded-xl border p-1">
                <button
                  onClick={() => onSetPanelMode("chat")}
                  aria-label="Chat only"
                  data-tooltip="Chat only"
                  className={`ui-tooltip flex h-8 w-8 items-center justify-center rounded-lg transition ${
                    panelMode === "chat"
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-surface-2 hover:text-primary"
                  }`}
                >
                  <PanelLeftClose size={14} />
                </button>
                <button
                  onClick={() => onSetPanelMode("split")}
                  aria-label="Split view"
                  data-tooltip="Split view"
                  className={`ui-tooltip hidden h-8 w-8 items-center justify-center rounded-lg transition lg:flex ${
                    panelMode === "split"
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-surface-2 hover:text-primary"
                  }`}
                >
                  <Columns2 size={14} />
                </button>
                <button
                  onClick={() => onSetPanelMode("notes")}
                  aria-label="Notes only"
                  data-tooltip="Notes only"
                  className={`ui-tooltip flex h-8 w-8 items-center justify-center rounded-lg transition ${
                    panelMode === "notes"
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-surface-2 hover:text-primary"
                  }`}
                >
                  <PanelRightClose size={14} />
                </button>
              </div>
            )}

            {/* Page Width/Margin Selector */}
            <div className="relative mr-1" data-deepspace-toolbar-menu>
              <button
                type="button"
                onPointerDown={(event) => event.stopPropagation()}
                aria-expanded={showWidthMenu}
                aria-haspopup="menu"
                onClick={() => {
                  setShowWidthMenu((open) => !open);
                  setShowExportMenu(false);
                }}
                className="border-glass-border bg-surface-1 text-muted-foreground hover:border-primary/40 hover:bg-surface-2 hover:text-primary inline-flex h-9 items-center gap-2 rounded-xl border px-3.5 text-xs font-bold transition"
              >
                <Maximize2 size={13} className="text-primary/75" />
                <span className="capitalize">Width: {marginSize}</span>
              </button>
              <div
                className={`${showWidthMenu ? "flex" : "hidden"} pointer-events-auto absolute top-full right-0 z-[100] pt-2`}
              >
                <div className="border-glass-border bg-surface-0 flex w-36 flex-col rounded-2xl border p-1 shadow-2xl backdrop-blur-xl">
                  <button
                    type="button"
                    onPointerDown={(event) => event.stopPropagation()}
                    role="menuitem"
                    onClick={() => {
                      setMarginSize("narrow");
                      setShowWidthMenu(false);
                    }}
                    className={`flex items-center justify-between rounded-xl px-3 py-2 text-left text-xs font-medium transition ${
                      marginSize === "narrow"
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-surface-1 hover:text-primary"
                    }`}
                  >
                    Narrow (600px)
                  </button>
                  <button
                    type="button"
                    onPointerDown={(event) => event.stopPropagation()}
                    role="menuitem"
                    onClick={() => {
                      setMarginSize("medium");
                      setShowWidthMenu(false);
                    }}
                    className={`flex items-center justify-between rounded-xl px-3 py-2 text-left text-xs font-medium transition ${
                      marginSize === "medium"
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-surface-1 hover:text-primary"
                    }`}
                  >
                    Medium (900px)
                  </button>
                  <button
                    type="button"
                    onPointerDown={(event) => event.stopPropagation()}
                    role="menuitem"
                    onClick={() => {
                      setMarginSize("wide");
                      setShowWidthMenu(false);
                    }}
                    className={`flex items-center justify-between rounded-xl px-3 py-2 text-left text-xs font-medium transition ${
                      marginSize === "wide"
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-surface-1 hover:text-primary"
                    }`}
                  >
                    Wide (1200px)
                  </button>
                  <button
                    type="button"
                    onPointerDown={(event) => event.stopPropagation()}
                    role="menuitem"
                    onClick={() => {
                      setMarginSize("full");
                      setShowWidthMenu(false);
                    }}
                    className={`flex items-center justify-between rounded-xl px-3 py-2 text-left text-xs font-medium transition ${
                      marginSize === "full"
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-surface-1 hover:text-primary"
                    }`}
                  >
                    Full Width
                  </button>
                </div>
              </div>
            </div>

            <div className="relative" data-deepspace-toolbar-menu>
              <button
                type="button"
                onPointerDown={(event) => event.stopPropagation()}
                aria-expanded={showExportMenu}
                aria-haspopup="menu"
                disabled={isExporting}
                onClick={() => {
                  setShowExportMenu((open) => !open);
                  setShowWidthMenu(false);
                }}
                className="border-glass-border bg-surface-1 text-muted-foreground hover:border-primary/40 hover:bg-surface-2 hover:text-primary inline-flex h-9 items-center gap-2 rounded-xl border px-4 text-xs font-bold transition disabled:cursor-wait disabled:opacity-70"
              >
                {isExporting ? (
                  <div className="border-primary h-3 w-3 animate-spin rounded-full border-2 border-t-transparent" />
                ) : (
                  <Download size={14} />
                )}
                Export
              </button>
              <div
                className={`${showExportMenu ? "flex" : "hidden"} pointer-events-auto absolute top-full right-0 z-[100] pt-2`}
              >
                <div className="border-glass-border bg-surface-0 flex w-40 flex-col rounded-2xl border p-1 shadow-2xl backdrop-blur-xl">
                  <button
                    type="button"
                    onPointerDown={(event) => event.stopPropagation()}
                    role="menuitem"
                    onClick={() => {
                      setShowExportMenu(false);
                      void handleExport("pdf");
                    }}
                    className="text-muted-foreground hover:bg-surface-1 hover:text-primary flex items-center gap-3 rounded-xl px-3 py-2 text-left text-xs font-medium"
                  >
                    <FileText size={14} className="text-danger" />
                    Export as PDF
                  </button>
                  <button
                    type="button"
                    onPointerDown={(event) => event.stopPropagation()}
                    role="menuitem"
                    onClick={() => {
                      setShowExportMenu(false);
                      void handleExport("docx");
                    }}
                    className="text-muted-foreground hover:bg-surface-1 hover:text-primary flex items-center gap-3 rounded-xl px-3 py-2 text-left text-xs font-medium"
                  >
                    <FileText size={14} className="text-primary" />
                    Export as DOCX
                  </button>
                  <button
                    type="button"
                    onPointerDown={(event) => event.stopPropagation()}
                    role="menuitem"
                    onClick={() => {
                      setShowExportMenu(false);
                      void handleExport("md");
                    }}
                    className="text-muted-foreground hover:bg-surface-1 hover:text-primary flex items-center gap-3 rounded-xl px-3 py-2 text-left text-xs font-medium"
                  >
                    <FileText size={14} className="text-success" />
                    Export as Markdown
                  </button>
                </div>
              </div>
            </div>
            {exportMessage ? (
              <span role="status" className="text-danger max-w-48 text-[11px] leading-4">
                {exportMessage}
              </span>
            ) : null}
          </div>
        </div>
        <div className="relative flex flex-1 flex-col overflow-hidden">
          {showLibrarySave ? (
            <div className="absolute inset-0 z-40 flex items-start justify-center bg-black/45 p-5 pt-20 backdrop-blur-sm">
              <section
                role="dialog"
                aria-modal="true"
                aria-labelledby="library-save-title"
                className="border-glass-border bg-surface-0 w-full max-w-md rounded-2xl border p-5 shadow-2xl"
              >
                <h2 id="library-save-title" className="text-foreground text-sm font-semibold">
                  Save to DeepSpace Library
                </h2>
                <p className="text-muted-foreground mt-1 text-xs leading-5">
                  Save a Markdown copy of this note as a separate private file. Choose the filename
                  and extension yourself.
                </p>
                <input
                  autoFocus
                  value={libraryFilename}
                  onChange={(event) => setLibraryFilename(event.target.value)}
                  placeholder="example: research-notes.md"
                  className="border-glass-border bg-surface-1 focus:border-primary/50 mt-4 w-full rounded-xl border px-3 py-2.5 text-sm outline-none"
                />
                {librarySaveMessage ? (
                  <p
                    className={`mt-2 text-xs ${librarySaveState === "error" ? "text-rose-300" : "text-emerald-300"}`}
                  >
                    {librarySaveMessage}
                  </p>
                ) : null}
                <div className="mt-5 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setShowLibrarySave(false)}
                    className="text-muted-foreground rounded-xl px-3 py-2 text-xs font-semibold hover:bg-white/5"
                  >
                    Close
                  </button>
                  <button
                    type="button"
                    disabled={librarySaveState === "saving"}
                    onClick={() => void saveToLibrary()}
                    className="bg-primary text-primary-foreground inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-50"
                  >
                    {librarySaveState === "saving" ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Save size={13} />
                    )}{" "}
                    Save file
                  </button>
                </div>
              </section>
            </div>
          ) : null}
          <div className="custom-scrollbar scrollbar-hide w-full flex-1 overflow-y-auto">
            <div
              className={`mx-auto min-h-full transition-all duration-300 ${marginClasses[marginSize]} py-5 sm:py-8`}
            >
              <BlockNoteView
                editor={editor}
                theme={getCustomTheme(theme)}
                slashMenu={false}
                onChange={async () => {
                  const html = await editor.blocksToHTMLLossy(editor.document);
                  onChange?.(html);
                }}
              >
                <SuggestionMenuController
                  triggerCharacter={"/"}
                  getItems={async (query) =>
                    filterSuggestionItems(getCustomSlashMenuItems(editor), query)
                  }
                />
              </BlockNoteView>
              {agentPreview?.markdown ? (
                <section
                  aria-live="polite"
                  aria-label="AverQel live note draft"
                  className={`mt-5 rounded-2xl border p-4 shadow-[0_14px_42px_-28px_rgba(34,211,238,0.7)] ${
                    agentPreview.status !== "streaming"
                      ? "border-amber-400/30 bg-amber-400/[0.06]"
                      : "border-cyan-400/30 bg-cyan-400/[0.05]"
                  }`}
                  data-testid="deepspace-live-note-preview"
                >
                  <div className="mb-3 flex items-center gap-2 text-[10px] font-bold tracking-[0.14em] uppercase">
                    <FileEdit
                      size={14}
                      className={
                        agentPreview.status !== "streaming" ? "text-amber-300" : "text-cyan-300"
                      }
                    />
                    <span className="text-foreground/80">
                      {agentPreview.status === "streaming"
                        ? "AverQel is writing in this note"
                        : agentPreview.status === "conflict"
                          ? "Your newer note edit was kept"
                          : "AverQel draft was not saved"}
                    </span>
                    <span className="text-foreground/45 ml-auto normal-case">
                      {agentPreview.mode === "append" ? "append" : "replace"}
                    </span>
                  </div>
                  <DeepSpaceMarkdownRenderer
                    content={agentPreview.markdown}
                    streaming={agentPreview.status === "streaming"}
                  />
                </section>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    );
  },
);

DeepSpaceEditor.displayName = "DeepSpaceEditor";

export default DeepSpaceEditor;
