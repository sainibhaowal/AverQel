"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Columns2,
  GripVertical,
  Loader2,
  PanelRightClose,
  Bot,
  Database,
  FolderSearch,
  Brain,
  PanelLeftClose,
  History,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { fetchWithAuth } from "@/lib/api";
import type { Transition } from "framer-motion";
import toast from "react-hot-toast";

import DeepSpaceChatClient, { type DeepSpaceRuntimeMetrics } from "./DeepSpaceChatClient";
import FileExplorer from "./FileExplorer";
import DeepSpaceEditor, { DeepSpaceEditorHandle } from "./DeepSpaceEditor";
import AgentIntelligencePanel from "./AgentIntelligencePanel";
import type { AgentStep } from "../_lib/deepspace-stream";

export interface DeepSpaceNote {
  id: string;
  title: string;
  updated_at: string;
  content_html?: string | null;
}

interface DeepSpaceVitals {
  internet: string;
  llm: string;
  web_search: string;
  sources: number;
  connector_statuses?: Record<string, number>;
  proactive_daemon?: {
    enabled: boolean;
    phase: string;
    timestamp?: string | null;
    interval_seconds?: number | null;
    healthy: boolean;
  } | null;
}

const STORAGE_KEY = "averqel_deepspace_draft";
const ACTIVE_NOTE_KEY = "averqel_deepspace_active_conversation";
const MIN_LEFT_WIDTH = 32;
const MAX_LEFT_WIDTH = 68;
const DEFAULT_NOTE_TITLE = "Untitled Note";
const MOBILE_STACKED_BREAKPOINT = 1024;

function IconTooltipButton({
  label,
  active,
  icon,
  onClick,
}: {
  label: string;
  active: boolean;
  icon: ReactNode;
  onClick: () => void;
}) {
  const [open, setOpen] = useState(false);
  const pressTimerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (pressTimerRef.current) window.clearTimeout(pressTimerRef.current);
    },
    [],
  );

  const hide = () => {
    setOpen(false);
    if (pressTimerRef.current) {
      window.clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
  };

  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      onPointerEnter={(event) => {
        if (event.pointerType === "mouse") setOpen(true);
      }}
      onPointerLeave={hide}
      onFocus={() => setOpen(true)}
      onBlur={hide}
      onPointerDown={(event) => {
        if (event.pointerType === "touch" || event.pointerType === "pen") {
          pressTimerRef.current = window.setTimeout(() => setOpen(true), 450);
        }
      }}
      onPointerUp={hide}
      onPointerCancel={hide}
      className={`group relative inline-flex h-8 w-8 sm:h-10 sm:w-10 items-center justify-center rounded-full transition-all ${
        active
          ? "bg-primary text-primary-foreground shadow-[0_0_15px_rgba(var(--primary),0.3)]"
          : "text-foreground/70 hover:bg-surface-2 hover:text-primary"
      }`}
    >
      {icon}
      <span
        className={`pointer-events-none absolute top-full left-1/2 z-40 mt-2 -translate-x-1/2 rounded-full border border-white/10 bg-black/85 px-3 py-1 text-[10px] font-semibold tracking-[0.22em] whitespace-nowrap text-white uppercase shadow-[0_12px_30px_rgba(0,0,0,0.35)] transition ${
          open ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0"
        }`}
      >
        {label}
      </span>
    </button>
  );
}

function stripHtml(html: string): string {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function deriveNoteTitleFromContent(html: string): string | null {
  const plainText = stripHtml(html);
  if (!plainText) return null;
  const normalized = plainText.slice(0, 60).trim();
  if (!normalized) return null;
  return normalized.length < plainText.length ? `${normalized}...` : normalized;
}

export default function DeepSpacePageClient() {
  const [notes, setNotes] = useState<DeepSpaceNote[]>([]);
  const [activeNote, setActiveNote] = useState<DeepSpaceNote | null>(null);
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null);
  const [activeFolderPath, setActiveFolderPath] = useState("");
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [panelMode, setPanelMode] = useState<"split" | "notes" | "chat" | "memory">("split");
  const [isIntelligenceDrawerOpen, setIsIntelligenceDrawerOpen] = useState(false);
  const [isExplorerOpen, setIsExplorerOpen] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [metrics, setMetrics] = useState<DeepSpaceRuntimeMetrics>({
    usage: 0,
    tokens: 0,
    tools: [],
    contextLimit: null,
    contextLimitSource: null,
    contextUsedTokens: 0,
    contextRemainingTokens: null,
    modelName: null,
    providerType: null,
    phase: null,
    compaction: null,
    latencyTimeline: [],
    agentSteps: [],
  });
  const [vitals, setVitals] = useState<DeepSpaceVitals | null>(null);

  const editorRef = useRef<DeepSpaceEditorHandle>(null);
  const [leftWidth, setLeftWidth] = useState(48);
  const [isDragging, setIsDragging] = useState(false);
  const [containerWidth, setContainerWidth] = useState(0);
  const [viewportWidth, setViewportWidth] = useState(0);
  const splitContainerRef = useRef<HTMLDivElement | null>(null);
  const activeDividerPointerIdRef = useRef<number | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Load workspace root and restore last active folder path from localStorage
  useEffect(() => {
    const initializeFolder = async () => {
      try {
        const savedFolder = window.localStorage.getItem("deepspace_active_folder_path");
        if (savedFolder) {
          setActiveFolderPath(savedFolder);
        } else {
          const res = (await fetchWithAuth("/workspace/root")) as Response;
          if (res.ok) {
            const data = await res.json();
            if (data.path) {
              setActiveFolderPath(data.path);
              window.localStorage.setItem("deepspace_active_folder_path", data.path);
            }
          }
        }
      } catch (err) {
        console.error("Failed to initialize workspace folder path", err);
      }
    };
    void initializeFolder();
  }, []);

  const handleFolderSelect = (path: string) => {
    setActiveFolderPath(path);
    window.localStorage.setItem("deepspace_active_folder_path", path);
  };

  // ── Data Fetching ────────────────────────────────────────────────────────

  const fetchNotes = useCallback(async () => {
    try {
      const res = (await fetchWithAuth("/deepspace/chats")) as Response;
      if (res.ok) {
        const data = await res.json();
        const items = data.items as DeepSpaceNote[];
        setNotes(items);
        return items;
      }
    } catch (err) {
      console.error("Failed to fetch notes", err);
    }
    return null;
  }, []);

  const createNote = async (title = "Untitled Note", content = "") => {
    try {
      const res = (await fetchWithAuth("/deepspace/chats", {
        method: "POST",
        body: JSON.stringify({ title, content_html: content }),
      })) as Response;
      if (res.ok) {
        const newNote = await res.json();
        setNotes((prev) => [newNote, ...prev]);
        setActiveNote(newNote);
        return newNote;
      }
    } catch (err) {
      console.error("Failed to create note", err);
    }
    return null;
  };

  const handleFileSelect = async (path: string) => {
    try {
      const res = (await fetchWithAuth(
        `/workspace/file/content?path=${encodeURIComponent(path)}`,
      )) as Response;
      if (res.ok) {
        const data = await res.json();
        const fileContent = data.content || "";

        if (editorRef.current) {
          editorRef.current.clear();
          const extension = path.split(".").pop() || "txt";
          const formatted = path.endsWith(".md")
            ? fileContent
            : `# ${path}\n\n\`\`\`${extension}\n${fileContent}\n\`\`\``;

          await editorRef.current.insertMarkdown(formatted);
          setActiveFilePath(path);
          toast.success(`Loaded ${path}`);
          if (panelMode === "chat") setPanelMode("split");
        }
      }
    } catch (err) {
      console.error("Failed to load file", err);
      toast.error("Failed to load file");
    }
  };

  const handleSaveFile = async () => {
    if (!activeFilePath || !editorRef.current) return;
    setIsSaving(true);
    try {
      const markdown = await editorRef.current.getMarkdown();

      let rawContent = markdown;
      if (!activeFilePath.endsWith(".md")) {
        const codeBlockRegex = /^\s*#\s+.*?\n+```[a-z]*\n([\s\S]*?)```\s*$/i;
        const match = markdown.match(codeBlockRegex);
        if (match) {
          rawContent = match[1];
        } else {
          const headerRegex = /^\s*#\s+.*?\n+([\s\S]*)$/i;
          const headerMatch = markdown.match(headerRegex);
          if (headerMatch) {
            rawContent = headerMatch[1];
          }
        }
      }

      const res = (await fetchWithAuth("/workspace/file", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          path: activeFilePath,
          content: rawContent,
        }),
      })) as Response;

      if (res.ok) {
        toast.success(`Saved successfully: ${activeFilePath}`);
      } else {
        toast.error("Failed to save file");
      }
    } catch (err) {
      console.error("Save file failed", err);
      toast.error("Failed to save file");
    } finally {
      setIsSaving(false);
    }
  };

  const activeNoteId = activeNote?.id ?? null;
  const handleCompactNow = useCallback(async () => {
    if (!activeNoteId) return;
    try {
      const res = (await fetchWithAuth(`/deepspace/chats/session/${activeNoteId}/compact`, {
        method: "POST",
      })) as Response;
      if (res.ok) {
        const compactPayload = (await res.json()) as {
          status?: string;
          compaction?: DeepSpaceRuntimeMetrics["compaction"];
        };
        const contextRes = (await fetchWithAuth(
          `/deepspace/chats/session/${activeNoteId}/context`,
        )) as Response;
        if (contextRes.ok) {
          const contextPayload = (await contextRes.json()) as {
            token_count?: number;
            usage_pct?: number;
            limit?: number | null;
            context_limit_source?: string | null;
            compaction?: DeepSpaceRuntimeMetrics["compaction"];
          };
          setMetrics((prev) => ({
            ...prev,
            usage:
              typeof contextPayload.usage_pct === "number" ? contextPayload.usage_pct : prev.usage,
            tokens:
              typeof contextPayload.token_count === "number"
                ? contextPayload.token_count
                : prev.tokens,
            contextUsedTokens:
              typeof contextPayload.token_count === "number"
                ? contextPayload.token_count
                : prev.contextUsedTokens,
            contextRemainingTokens:
              typeof contextPayload.limit === "number" &&
              typeof contextPayload.token_count === "number"
                ? Math.max(contextPayload.limit - contextPayload.token_count, 0)
                : prev.contextRemainingTokens,
            contextLimit:
              typeof contextPayload.limit === "number" ? contextPayload.limit : prev.contextLimit,
            contextLimitSource:
              typeof contextPayload.context_limit_source === "string"
                ? contextPayload.context_limit_source
                : prev.contextLimitSource,
            compaction:
              contextPayload.compaction ?? compactPayload.compaction ?? prev.compaction ?? null,
          }));
        }
        const updatedVitals = (await fetchWithAuth("/deepspace/chats/vitals")) as Response;
        if (updatedVitals.ok) {
          setVitals((await updatedVitals.json()) as DeepSpaceVitals);
        }
        toast.success("Conversation context compacted.");
      }
    } catch (error) {
      console.error("Manual compaction failed", error);
      toast.error("Context compaction failed.");
    }
  }, [activeNoteId]);

  // ── Lifecycle & Migration ────────────────────────────────────────────────

  useEffect(() => {
    const init = async () => {
      const items = await fetchNotes();
      if (items === null) {
        // Do not create a replacement conversation when the VPS is briefly
        // unavailable; that would make the real history appear lost.
        setIsInitialLoading(false);
        return;
      }
      if (items.length === 0) {
        const localDraft = window.localStorage.getItem(STORAGE_KEY);
        if (localDraft) {
          await createNote("My First Note", localDraft);
          window.localStorage.removeItem(STORAGE_KEY);
        } else {
          await createNote();
        }
      } else {
        const savedId = window.localStorage.getItem(ACTIVE_NOTE_KEY);
        setActiveNote(items.find((item) => item.id === savedId) || items[0] || null);
      }
      setIsInitialLoading(false);
    };
    init();
  }, [fetchNotes]);

  // Keep the selected conversation stable across route changes, refreshes,
  // browser restarts, and returning from another dashboard page. The message
  // history itself remains server-owned; this key stores only the selection.
  useEffect(() => {
    if (activeNote?.id) {
      window.localStorage.setItem(ACTIVE_NOTE_KEY, activeNote.id);
    }
  }, [activeNote?.id]);

  useEffect(() => {
    const loadVitals = async () => {
      try {
        const res = (await fetchWithAuth("/deepspace/chats/vitals")) as Response;
        if (res.ok) setVitals((await res.json()) as DeepSpaceVitals);
      } catch (error) {
        console.error("Failed to fetch DeepSpace vitals", error);
      }
    };
    void loadVitals();
  }, []);

  useEffect(() => {
    const loadRuntime = async () => {
      try {
        const res = (await fetchWithAuth("/deepspace/chats/runtime")) as Response;
        if (!res.ok) return;
        const runtime = await res.json();
        setMetrics((prev) => ({
          ...prev,
          contextLimit: runtime.context_limit,
          contextLimitSource: runtime.context_limit_source,
          modelName: runtime.model_name,
          providerType: runtime.provider_type,
        }));
      } catch (error) {
        console.error("Failed to fetch DeepSpace runtime", error);
      }
    };
    void loadRuntime();
  }, []);

  // ── Auto-save ────────────────────────────────────────────────────────────

  const saveTimerRef = useRef<NodeJS.Timeout | null>(null);

  const handleEditorChange = (html: string) => {
    if (!activeNote || activeFilePath) return;
    const nextAutoTitle =
      activeNote.title === DEFAULT_NOTE_TITLE ? deriveNoteTitleFromContent(html) : null;
    setActiveNote((prev) =>
      prev ? { ...prev, content_html: html, title: nextAutoTitle ?? prev.title } : null,
    );
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    setIsSaving(true);
    saveTimerRef.current = setTimeout(async () => {
      try {
        await fetchWithAuth(`/deepspace/chats/${activeNote.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            content_html: html,
            ...(nextAutoTitle ? { title: nextAutoTitle } : {}),
          }),
        });
      } finally {
        setIsSaving(false);
      }
    }, 1500);
  };

  // ── Layout & Resizing ────────────────────────────────────────────────────

  useEffect(() => {
    const container = splitContainerRef.current;
    if (!container) return;
    const updateWidth = () => setContainerWidth(container.getBoundingClientRect().width);
    updateWidth();
    const observer = new ResizeObserver(() => updateWidth());
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const updateViewport = () =>
      setViewportWidth(window.visualViewport?.width || window.innerWidth || 0);
    updateViewport();
    window.addEventListener("resize", updateViewport);
    window.visualViewport?.addEventListener("resize", updateViewport);
    return () => {
      window.removeEventListener("resize", updateViewport);
      window.visualViewport?.removeEventListener("resize", updateViewport);
    };
  }, []);

  useEffect(() => {
    if (!isDragging) return;
    const handlePointerMove = (event: PointerEvent) => {
      if (
        activeDividerPointerIdRef.current !== null &&
        event.pointerId !== activeDividerPointerIdRef.current
      )
        return;
      if (event.cancelable) event.preventDefault();
      const container = splitContainerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const nextWidth = ((event.clientX - rect.left) / rect.width) * 100;
      setLeftWidth(Math.min(MAX_LEFT_WIDTH, Math.max(MIN_LEFT_WIDTH, nextWidth)));
    };
    const stopDragging = () => {
      activeDividerPointerIdRef.current = null;
      setIsDragging(false);
    };
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopDragging);
    window.addEventListener("pointercancel", stopDragging);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopDragging);
      window.removeEventListener("pointercancel", stopDragging);
    };
  }, [isDragging]);

  const insertAnswer = (content: string) => {
    if (!content.trim()) return;
    editorRef.current?.insertMarkdown(content.trim());
  };

  const isStackedLayout = viewportWidth > 0 && viewportWidth < MOBILE_STACKED_BREAKPOINT;
  const showNotesPanel = panelMode === "split" || panelMode === "notes";
  const showChatPanel = panelMode === "split" || panelMode === "chat";
  const panelTransition: Transition = isStackedLayout
    ? { duration: 0.16, ease: "easeOut" }
    : { type: "spring", damping: 24, stiffness: 220 };
  const shellTransitionClass = isStackedLayout ? "duration-150" : "duration-300";


  useEffect(() => {
    if (isStackedLayout && panelMode === "split") setPanelMode("chat");
  }, [isStackedLayout, panelMode]);

  const collapseChat = () => {
    setPanelMode("notes");
  };

  if (isInitialLoading) {
    return (
      <div className="theme-panel-muted flex h-full w-full items-center justify-center rounded-2xl">
        <Loader2 className="text-primary h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="relative flex h-full w-full overflow-hidden rounded-2xl bg-transparent">


      {/* ── Floating Drawer Sidebar (File Explorer) ─────────────────────────────── */}
      <AnimatePresence>
        {isExplorerOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/35 backdrop-blur-[1.5px]"
              onClick={() => setIsExplorerOpen(false)}
            />
            <motion.aside
              initial={{ x: -320, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -320, opacity: 0 }}
              className="fixed top-4 left-4 bottom-4 z-50 flex w-[280px] sm:w-[320px] overflow-hidden rounded-[2rem] border border-white/10 bg-black/72 shadow-2xl backdrop-blur-2xl"
            >
              <FileExplorer
                variant="sidebar"
                onFileSelect={(path) => {
                  void handleFileSelect(path);
                  setIsExplorerOpen(false);
                }}
                onFolderSelect={handleFolderSelect}
                onClose={() => setIsExplorerOpen(false)}
                isOpen={isExplorerOpen}
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <div
        className={`relative flex h-full flex-1 flex-col overflow-hidden ${
          isDragging
            ? "cursor-col-resize transition-none select-none"
            : `transition-colors ${shellTransitionClass}`
        }`}
      >
        {(() => {
          const portalTarget =
            typeof document !== "undefined"
              ? document.getElementById("header-layout-controls")
              : null;
          const shouldRenderPortal = mounted && portalTarget;

          if (shouldRenderPortal) {
            return createPortal(
              <div className="border-glass-border bg-surface-0/90 pointer-events-auto flex items-center gap-0.5 sm:gap-1 rounded-full border p-0.5 sm:p-1 shadow-xl backdrop-blur-md">
                <IconTooltipButton
                  label="Chat"
                  active={panelMode === "chat"}
                  icon={<Bot size={18} />}
                  onClick={() => setPanelMode("chat")}
                />
                <IconTooltipButton
                  label="Memory"
                  active={panelMode === "memory"}
                  icon={<Database size={18} />}
                  onClick={() => setPanelMode("memory")}
                />
                <IconTooltipButton
                  label="Split view"
                  active={panelMode === "split"}
                  icon={<Columns2 size={15} />}
                  onClick={() => setPanelMode("split")}
                />
                <IconTooltipButton
                  label="Notes only"
                  active={panelMode === "notes"}
                  icon={<PanelRightClose size={15} />}
                  onClick={() => setPanelMode("notes")}
                />
                <IconTooltipButton
                  label="Explorer"
                  active={isExplorerOpen}
                  icon={<FolderSearch size={16} />}
                  onClick={() => setIsExplorerOpen(!isExplorerOpen)}
                />
                <IconTooltipButton
                  label="Insights"
                  active={isIntelligenceDrawerOpen}
                  icon={<Brain size={16} />}
                  onClick={() => setIsIntelligenceDrawerOpen(!isIntelligenceDrawerOpen)}
                />
                <IconTooltipButton
                  label="History"
                  active={isHistoryOpen}
                  icon={<History size={16} />}
                  onClick={() => setIsHistoryOpen(!isHistoryOpen)}
                />
              </div>,
              portalTarget,
            );
          }

          return null;
        })()}

        <div
          ref={splitContainerRef}
          className={`relative flex h-full max-h-full min-h-0 flex-1 overflow-hidden ${isStackedLayout ? "flex-col" : "flex-row"}`}
        >
          <AnimatePresence initial={false} mode="popLayout">
            {showNotesPanel ? (
              <motion.section
                key="notes-panel"
                initial={{ opacity: 0, x: isStackedLayout ? 0 : -24, y: isStackedLayout ? -24 : 0 }}
                animate={{ opacity: 1, x: 0, y: 0 }}
                exit={{ opacity: 0, x: isStackedLayout ? 0 : -24, y: isStackedLayout ? -24 : 0 }}
                transition={panelTransition}
                className={`relative flex min-h-0 min-w-0 flex-col overflow-hidden ${isStackedLayout ? "h-full w-full flex-[1_1_auto]" : showChatPanel ? "h-full flex-[0_0_auto]" : "h-full w-full"}`}
                style={
                  !isStackedLayout && showChatPanel ? { flexBasis: `${leftWidth}%` } : undefined
                }
              >
                <DeepSpaceEditor
                  ref={editorRef}
                  initialContent={activeNote?.content_html || ""}
                  onChange={handleEditorChange}
                  conversationId={activeNote?.id}
                  isSaving={isSaving}
                  showCollapseControls={false}
                  panelMode={panelMode}
                  onSetPanelMode={setPanelMode}
                  activeFilePath={activeFilePath}
                  activeFolderPath={activeFolderPath}
                  onSaveFile={handleSaveFile}
                />
              </motion.section>
            ) : null}
          </AnimatePresence>

          {showNotesPanel && showChatPanel && !isStackedLayout ? (
            <div
              role="separator"
              aria-label="Resize deepspace panels"
              onPointerDown={(e) => {
                e.preventDefault();
                e.currentTarget.setPointerCapture(e.pointerId);
                activeDividerPointerIdRef.current = e.pointerId;
                setIsDragging(true);
              }}
              onPointerUp={(e) => {
                if (isDragging) {
                  e.currentTarget.releasePointerCapture(e.pointerId);
                  activeDividerPointerIdRef.current = null;
                  setIsDragging(false);
                }
              }}
              className={`relative z-10 w-5 shrink-0 cursor-col-resize touch-none ${isDragging ? "bg-primary/10" : "hover:bg-primary/5"}`}
            >
              <div
                className={`bg-glass-border absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-colors ${isDragging ? "bg-primary/40" : ""}`}
              />
              <div className="pointer-events-none absolute inset-y-0 left-1/2 flex -translate-x-1/2 items-center justify-center">
                <div className="bg-surface-0 border-glass-border rounded-full border p-1 opacity-40 shadow-lg group-hover:opacity-100">
                  <GripVertical size={10} />
                </div>
              </div>
            </div>
          ) : null}

          <AnimatePresence initial={false} mode="popLayout">
            {showChatPanel ? (
              <motion.section
                key="chat-panel"
                initial={{ opacity: 0, x: isStackedLayout ? 0 : 24, y: isStackedLayout ? 24 : 0 }}
                animate={{ opacity: 1, x: 0, y: 0 }}
                exit={{ opacity: 0, x: isStackedLayout ? 0 : 24, y: isStackedLayout ? 24 : 0 }}
                transition={panelTransition}
                className="h-full min-h-0 min-w-0 flex-1 overflow-hidden"
              >
                <DeepSpaceChatClient
                  activeConversationId={activeNote?.id ?? null}
                  currentContent={activeNote?.content_html ?? ""}
                  onMetricsUpdate={setMetrics}
                  onConversationRenamed={(note) => {
                    setNotes((prev) => prev.map((item) => (item.id === note.id ? note : item)));
                    setActiveNote((prev) => (prev?.id === note.id ? note : prev));
                  }}
                  onSelectNote={(noteId) => {
                    const note = notes.find((n) => n.id === noteId);
                    if (note) {
                      setActiveNote(note);
                      setActiveFilePath(null);
                    }
                  }}
                  onNewNote={() => {
                    createNote();
                    setActiveFilePath(null);
                  }}
                  onInsertLatestAnswer={insertAnswer}
                  panelMode={panelMode}
                  onSetPanelMode={setPanelMode}
                  isHistoryOpen={isHistoryOpen}
                  onSetHistoryOpen={setIsHistoryOpen}
                />
              </motion.section>
            ) : null}
          </AnimatePresence>
        </div>

        <AnimatePresence>
          {isIntelligenceDrawerOpen && (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-40 bg-black/35 backdrop-blur-[1.5px]"
                onClick={() => setIsIntelligenceDrawerOpen(false)}
              />
              <motion.aside
                initial={{ x: 420, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: 420, opacity: 0 }}
                className="fixed top-4 right-4 bottom-4 z-50 flex w-[360px] overflow-hidden rounded-[2rem] border border-white/10 bg-black/72 shadow-2xl backdrop-blur-2xl"
              >
                <AgentIntelligencePanel
                  contextUsage={metrics.usage}
                  tokenCount={metrics.tokens}
                  activeTools={metrics.tools}
                  contextLimit={metrics.contextLimit}
                  contextLimitSource={metrics.contextLimitSource}
                  contextUsedTokens={metrics.contextUsedTokens}
                  contextRemainingTokens={metrics.contextRemainingTokens}
                  modelName={metrics.modelName}
                  providerType={metrics.providerType}
                  phase={metrics.phase}
                  compaction={metrics.compaction ?? null}
                  latencyTimeline={metrics.latencyTimeline ?? []}
                  agentSteps={metrics.agentSteps ?? []}
                  vitals={vitals}
                  onCompactNow={handleCompactNow}
                  variant="drawer"
                />
              </motion.aside>
            </>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
