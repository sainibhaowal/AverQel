"use client";

import {
  useCreateBlockNote,
  SuggestionMenuController,
  getDefaultReactSlashMenuItems,
} from "@blocknote/react";
import { BlockNoteView, darkDefaultTheme, lightDefaultTheme } from "@blocknote/mantine";
import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import { forwardRef, useImperativeHandle, useEffect, useState } from "react";
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

export interface DeepSpaceEditorHandle {
  insertHTML: (html: string) => Promise<void>;
  insertMarkdown: (markdown: string) => Promise<void>;
  getHTML: () => Promise<string>;
  getMarkdown: () => Promise<string>;
  clear: () => void;
}

interface DeepSpaceEditorProps {
  initialContent?: string;
  onChange?: (html: string) => void;
  conversationId?: string;
  isSaving?: boolean;
  onCollapseChat?: () => void;
  chatVisible?: boolean;
  showCollapseControls?: boolean;
  panelMode?: "split" | "notes" | "chat" | "memory";
  onSetPanelMode?: (mode: "split" | "notes" | "chat" | "memory") => void;
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
    },
    ref,
  ) => {
    const { theme } = useTheme();
    const [isExporting, setIsExporting] = useState(false);
    const [showWidthMenu, setShowWidthMenu] = useState(false);
    const [showExportMenu, setShowExportMenu] = useState(false);
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
    });

    useEffect(() => {
      const loadInitial = async () => {
        if (initialContent && editor.document.length <= 1) {
          const blocks = await editor.tryParseHTMLToBlocks(initialContent);
          editor.replaceBlocks(editor.document, blocks);
        }
      };
      loadInitial();
    }, [editor, initialContent]);

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
      clear: () => {
        editor.replaceBlocks(editor.document, []);
      },
    }));

    const handleExport = async (format: "pdf" | "docx" | "md") => {
      if (!conversationId) {
        alert("Cannot export without a saved conversation.");
        return;
      }

      setIsExporting(true);
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
        window.URL.revokeObjectURL(url);
      } catch (error) {
        console.error("Export error:", error);
        alert(
          error instanceof Error ? error.message : "Failed to export document. Please try again.",
        );
      } finally {
        setIsExporting(false);
      }
    };

    return (
      <div className="flex h-full w-full flex-col overflow-hidden bg-transparent">
        <div className="border-glass-border bg-surface-1/40 flex flex-col gap-3 border-b p-3 shadow-sm backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between">
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
            {showCollapseControls && onSetPanelMode && (
              <div className="border-glass-border bg-surface-0/40 mr-2 flex items-center gap-1 rounded-xl border p-1">
                <button
                  onClick={() => onSetPanelMode("chat")}
                  title="Chat only"
                  className={`flex h-8 w-8 items-center justify-center rounded-lg transition ${
                    panelMode === "chat"
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-surface-2 hover:text-primary"
                  }`}
                >
                  <PanelLeftClose size={14} />
                </button>
                <button
                  onClick={() => onSetPanelMode("split")}
                  title="Split view"
                  className={`hidden h-8 w-8 items-center justify-center rounded-lg transition lg:flex ${
                    panelMode === "split"
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-surface-2 hover:text-primary"
                  }`}
                >
                  <Columns2 size={14} />
                </button>
                <button
                  onClick={() => onSetPanelMode("notes")}
                  title="Notes only"
                  className={`flex h-8 w-8 items-center justify-center rounded-lg transition ${
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
                className={`${showWidthMenu ? "flex" : "hidden"} absolute top-full right-0 z-50 pt-2`}
              >
                <div className="border-glass-border bg-surface-0 flex w-36 flex-col rounded-2xl border p-1 shadow-2xl backdrop-blur-xl">
                  <button
                    type="button"
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
                className={`${showExportMenu ? "flex" : "hidden"} absolute top-full right-0 z-50 pt-2`}
              >
                <div className="border-glass-border bg-surface-0 flex w-40 flex-col rounded-2xl border p-1 shadow-2xl backdrop-blur-xl">
                  <button
                    type="button"
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
          </div>
        </div>
        <div className="relative flex flex-1 flex-col overflow-hidden">
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
            </div>
          </div>
        </div>
      </div>
    );
  },
);

DeepSpaceEditor.displayName = "DeepSpaceEditor";

export default DeepSpaceEditor;
