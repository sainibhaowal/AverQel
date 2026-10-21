"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Columns2,
  GripVertical,
  Loader2,
  PanelRightClose,
  Bot,
  Database,
  History,
  RefreshCw,
  FolderOpen,
  CalendarClock,
} from "lucide-react";
import dynamic from "next/dynamic";
import {
  forwardRef,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ForwardedRef,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { fetchWithAuth } from "@/lib/api";
import type { Transition } from "framer-motion";
import type { StructuredBlock } from "../_lib/deepspace-stream";
import AverQelLoading from "@/app/components/ui/AverQelLoading";

import DeepSpaceChatClient from "./DeepSpaceChatClient";
import type {
  DeepSpaceAgentNotePreview,
  DeepSpaceEditorHandle,
  DeepSpaceEditorProps,
} from "./DeepSpaceEditor";
import MemoryPanel from "./MemoryPanel";
import DeepSpaceLibraryDrawer from "./DeepSpaceLibraryDrawer";
import DeepSpaceSchedulesPanel from "./DeepSpaceSchedulesPanel";

type DeferredEditorProps = DeepSpaceEditorProps & {
  forwardedRef?: ForwardedRef<DeepSpaceEditorHandle>;
};

// Keep the heavy BlockNote/Mantine styles out of ordinary dashboard routes.
// next/dynamic does not forward refs by itself, so this small adapter passes
// the imperative editor handle through to the real editor after it loads.
const DeferredDeepSpaceEditor = dynamic<DeferredEditorProps>(
  () =>
    import("./DeepSpaceEditor").then(
      ({ default: Editor }) =>
        function DeferredEditor({ forwardedRef, ...props }: DeferredEditorProps) {
          return <Editor {...props} ref={forwardedRef} />;
        },
    ),
  {
    ssr: false,
    loading: () => (
      <AverQelLoading label="Loading note editor…" size="section" className="h-full" />
    ),
  },
);

const DeepSpaceEditor = forwardRef<DeepSpaceEditorHandle, DeepSpaceEditorProps>(
  function DeepSpaceEditor(props, ref) {
    return <DeferredDeepSpaceEditor {...props} forwardedRef={ref} />;
  },
);

export interface DeepSpaceNote {
  id: string;
  title: string;
  updated_at: string;
  content_html?: string | null;
}

type WorkspacePanel = "notes" | "chat" | "memory" | "schedules" | "library";
type SplitWorkspacePanel = Exclude<WorkspacePanel, "chat">;

const STORAGE_KEY = "averqel_deepspace_draft";
const ACTIVE_NOTE_KEY = "averqel_deepspace_active_conversation";
const MIN_LEFT_WIDTH = 32;
const MAX_LEFT_WIDTH = 68;
const DEFAULT_NOTE_TITLE = "Untitled Note";
const MOBILE_STACKED_BREAKPOINT = 1024;
const DEEPSPACE_INITIAL_LOAD_GRACE_MS = 2_500;

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
      className={`group relative inline-flex h-8 w-8 items-center justify-center rounded-full transition-all sm:h-10 sm:w-10 ${
        active
          ? "bg-primary text-primary-foreground shadow-[0_0_15px_rgba(var(--primary),0.3)]"
          : "text-foreground/70 hover:bg-surface-2 hover:text-primary"
      }`}
    >
      {icon}
      <span
        role="tooltip"
        aria-hidden={!open}
        className={`workspace-icon-tooltip pointer-events-none absolute top-full left-1/2 z-40 mt-2 -translate-x-1/2 rounded-full border border-white/10 bg-black/85 px-3 py-1 text-[10px] font-semibold tracking-[0.22em] whitespace-nowrap text-white uppercase shadow-[0_12px_30px_rgba(0,0,0,0.35)] transition ${
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

function replaceVisualBlockInNoteHtml(html: string, block: StructuredBlock): string | null {
  if (typeof DOMParser === "undefined") return null;
  const documentNode = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  const candidates = Array.from(
    documentNode.body.querySelectorAll<HTMLElement>("[data-rich-content-source]"),
  );
  for (const candidate of candidates) {
    const source = candidate.dataset.richContentSource ?? "";
    let matches = false;
    try {
      const parsed = JSON.parse(source) as { id?: unknown; block_id?: unknown };
      matches =
        parsed.id === block.id ||
        parsed.block_id === block.id ||
        (typeof (block as { source_markdown?: unknown }).source_markdown === "string" &&
          source.trim() === String((block as { source_markdown?: string }).source_markdown).trim());
    } catch {
      matches = new RegExp(
        `(?:deepspace-block-id|block-id)\\s*:\\s*${escapeRegExp(block.id)}`,
      ).test(source);
    }
    if (!matches) continue;
    const nextSource =
      block.type === "diagram" && block.source === "mermaid"
        ? `%% deepspace-block-id: ${block.id}\n${block.syntax}`
        : JSON.stringify(block, null, 2);
    candidate.dataset.richContentSource = nextSource;
    return documentNode.body.innerHTML;
  }
  return null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function extractPersistedVisualBlocks(html: string): StructuredBlock[] {
  if (typeof DOMParser === "undefined") return [];
  const documentNode = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  const blocks: StructuredBlock[] = [];
  for (const candidate of Array.from(
    documentNode.body.querySelectorAll<HTMLElement>("[data-rich-content-source]"),
  )) {
    const source = candidate.dataset.richContentSource ?? "";
    try {
      const parsed = JSON.parse(source) as Record<string, unknown>;
      const kind = candidate.dataset.richContentKind;
      if (!parsed || typeof parsed !== "object") continue;
      const id =
        typeof parsed.id === "string"
          ? parsed.id
          : typeof parsed.block_id === "string"
            ? parsed.block_id
            : null;
      if (!id) continue;
      if (typeof parsed.type === "string") {
        blocks.push({ ...parsed, id } as StructuredBlock);
      } else if (kind === "chart" || kind === "card" || kind === "gallery") {
        blocks.push({ ...parsed, id, type: kind } as StructuredBlock);
      } else if (kind === "graph" && parsed.graph && typeof parsed.graph === "object") {
        blocks.push({
          ...parsed,
          id,
          type: "diagram",
          diagram_type: "graph_canvas",
          source: "graph_json",
          syntax: JSON.stringify(parsed),
          graph: parsed.graph,
        } as StructuredBlock);
      }
    } catch {
      // Mermaid source is intentionally left to the existing text editor path.
    }
  }
  return blocks;
}

function preserveLatestVisualBlockRevisions(
  html: string,
  latestSources: Map<string, string>,
): string {
  let synchronizedHtml = html;
  for (const incomingBlock of extractPersistedVisualBlocks(html)) {
    const latestSource = latestSources.get(incomingBlock.id);
    if (!latestSource) continue;
    try {
      const latestBlock = JSON.parse(latestSource) as StructuredBlock & { revision?: number };
      const incomingRevision = (incomingBlock as StructuredBlock & { revision?: number }).revision;
      if (
        typeof latestBlock.revision === "number" &&
        typeof incomingRevision === "number" &&
        latestBlock.revision > incomingRevision
      ) {
        synchronizedHtml =
          replaceVisualBlockInNoteHtml(synchronizedHtml, latestBlock) ?? synchronizedHtml;
      }
    } catch {
      // Ignore malformed cached sources; normal note validation handles them.
    }
  }
  return synchronizedHtml;
}

export default function DeepSpacePageClient() {
  const [notes, setNotes] = useState<DeepSpaceNote[]>([]);
  const [activeNote, setActiveNote] = useState<DeepSpaceNote | null>(null);
  const activeNoteRef = useRef<DeepSpaceNote | null>(null);
  useEffect(() => {
    activeNoteRef.current = activeNote;
  }, [activeNote]);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [agentNotePreview, setAgentNotePreview] = useState<DeepSpaceAgentNotePreview | null>(null);
  // Chat is the primary DeepSpace workspace. Notes remains available through
  // the workspace switcher and as the default left panel when split view is
  // explicitly enabled.
  const [panelMode, setPanelMode] = useState<WorkspacePanel>("chat");
  const editorRef = useRef<DeepSpaceEditorHandle>(null);
  const agentPreviewBaseContentRef = useRef<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isSplitView, setIsSplitView] = useState(false);
  const [splitWorkspacePanel, setSplitWorkspacePanel] = useState<SplitWorkspacePanel>("notes");
  const [serviceWarnings, setServiceWarnings] = useState<string[]>([]);
  const [serviceRetryKey, setServiceRetryKey] = useState(0);

  const [leftWidth, setLeftWidth] = useState(48);
  const [isDragging, setIsDragging] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(0);
  const splitContainerRef = useRef<HTMLDivElement | null>(null);
  const activeDividerPointerIdRef = useRef<number | null>(null);
  const [mounted, setMounted] = useState(false);

  const addServiceWarning = useCallback((message: string) => {
    setServiceWarnings((previous) =>
      previous.includes(message) ? previous : [...previous, message].slice(-3),
    );
  }, []);

  const syncExistingVisualArtifact = useCallback(
    async (conversationId: string, block: StructuredBlock) => {
      const entriesResponse = (await fetchWithAuth(`/deepspace/library/${conversationId}/entries`, {
        timeoutMs: 8_000,
      })) as Response;
      if (!entriesResponse.ok) {
        throw new Error("The saved visual artifact could not be checked for updates.");
      }
      const entries = (await entriesResponse.json()) as {
        files?: Array<{
          name?: string;
          version?: number;
          source?: string;
          metadata_json?: unknown;
        }>;
      };
      const artifact = (entries.files ?? []).find((file) => {
        const metadata =
          file.metadata_json && typeof file.metadata_json === "object"
            ? (file.metadata_json as { visual_document?: { block_id?: unknown } })
            : null;
        return (
          metadata?.visual_document?.block_id === block.id ||
          (file.source === "visual_editor" && file.name === `${block.id}.visual.json`)
        );
      });
      if (!artifact) return;
      if (typeof artifact.version !== "number" || !artifact.name) {
        throw new Error("The saved visual artifact is missing its revision information.");
      }
      const response = (await fetchWithAuth(
        `/deepspace/library/${conversationId}/visual-artifacts`,
        {
          method: "POST",
          body: JSON.stringify({
            block_id: block.id,
            block,
            filename: artifact.name,
            expected_version: artifact.version,
          }),
        },
      )) as Response;
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          String(
            payload?.detail?.message ??
              "The saved visual artifact could not be synchronized with this edit.",
          ),
        );
      }
    },
    [],
  );

  useEffect(() => {
    queueMicrotask(() => setMounted(true));
  }, []);

  // ── Data Fetching ────────────────────────────────────────────────────────

  const fetchNotes = useCallback(async () => {
    try {
      const res = (await fetchWithAuth("/deepspace/chats", { timeoutMs: 5_000 })) as Response;
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
        timeoutMs: 5_000,
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

  // ── Lifecycle & Migration ────────────────────────────────────────────────

  useEffect(() => {
    let mounted = true;
    const releaseTimer = window.setTimeout(() => {
      if (!mounted) return;
      setIsInitialLoading(false);
      addServiceWarning(
        "Conversation history is taking longer than expected; the workspace remains available.",
      );
    }, DEEPSPACE_INITIAL_LOAD_GRACE_MS);

    const init = async () => {
      const items = await fetchNotes();
      if (!mounted) return;
      window.clearTimeout(releaseTimer);
      if (items === null) {
        // Do not create a replacement conversation when the VPS is briefly
        // unavailable; that would make the real history appear lost.
        setIsInitialLoading(false);
        addServiceWarning("Conversation history is temporarily unavailable.");
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
        const requestedId = new URLSearchParams(window.location.search).get("conversation");
        setActiveNote(
          items.find((item) => item.id === requestedId) ||
            items.find((item) => item.id === savedId) ||
            items[0] ||
            null,
        );
      }
      setIsInitialLoading(false);
      setServiceWarnings((previous) =>
        previous.filter((warning) => !warning.toLowerCase().includes("conversation history")),
      );
    };
    void init();

    return () => {
      mounted = false;
      window.clearTimeout(releaseTimer);
    };
  }, [addServiceWarning, fetchNotes, serviceRetryKey]);

  // Keep the selected conversation stable across route changes, refreshes,
  // browser restarts, and returning from another dashboard page. The message
  // history itself remains server-owned; this key stores only the selection.
  useEffect(() => {
    const selectedNote = activeNoteRef.current;
    if (selectedNote?.id) {
      window.localStorage.setItem(ACTIVE_NOTE_KEY, selectedNote.id);
    }
    noteVisualSourceRef.current.clear();
    for (const block of extractPersistedVisualBlocks(selectedNote?.content_html ?? "")) {
      noteVisualSourceRef.current.set(block.id, JSON.stringify(block));
    }
    agentPreviewBaseContentRef.current = null;
    queueMicrotask(() => setAgentNotePreview(null));
  }, [activeNote?.id]);

  useEffect(() => {
    const openLibrary = () => {
      if (isSplitView) setSplitWorkspacePanel("library");
      else setPanelMode("library");
    };
    window.addEventListener("deepspace-library-open", openLibrary);
    return () => window.removeEventListener("deepspace-library-open", openLibrary);
  }, [isSplitView]);

  // ── Auto-save ────────────────────────────────────────────────────────────

  const saveTimerRef = useRef<NodeJS.Timeout | null>(null);
  const noteVisualSourceRef = useRef(new Map<string, string>());

  const handleEditorChange = (html: string) => {
    if (!activeNote) return;
    // replaceHTML can trigger a delayed BlockNote change event containing the
    // document that was current before a chat or artifact edit. Keep the
    // newest persisted visual revision when that stale callback arrives.
    const currentHtml = preserveLatestVisualBlockRevisions(html, noteVisualSourceRef.current);
    const nextAutoTitle =
      activeNote.title === DEFAULT_NOTE_TITLE ? deriveNoteTitleFromContent(currentHtml) : null;
    setActiveNote((prev) =>
      prev ? { ...prev, content_html: currentHtml, title: nextAutoTitle ?? prev.title } : null,
    );
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    setIsSaving(true);
    saveTimerRef.current = setTimeout(async () => {
      try {
        // A note edit can originate outside the chat renderer. Persist each
        // embedded visual block before saving its HTML. That way a revision
        // conflict cannot leave stale note markup behind. Recheck the latest
        // known revision when the debounce fires because a chat or artifact
        // edit may have completed since this callback was scheduled.
        let synchronizedHtml = preserveLatestVisualBlockRevisions(
          html,
          noteVisualSourceRef.current,
        );
        let hasVisualConflict = false;
        for (const block of extractPersistedVisualBlocks(synchronizedHtml)) {
          const serializedBlock = JSON.stringify(block);
          if (noteVisualSourceRef.current.get(block.id) === serializedBlock) continue;
          const revision =
            typeof (block as StructuredBlock & { revision?: number }).revision === "number"
              ? Number((block as StructuredBlock & { revision?: number }).revision)
              : undefined;
          const visualResponse = (await fetchWithAuth(
            `/deepspace/chats/${activeNote.id}/visual-block`,
            {
              method: "PATCH",
              body: JSON.stringify({
                block_id: block.id,
                block,
                ...(revision === undefined ? {} : { expected_revision: revision }),
              }),
            },
          )) as Response;
          // A block may be a note-only visual or a legacy block not yet
          // associated with a chat message. The note remains authoritative in
          // that case; a revision conflict must stop the note write.
          if (!visualResponse.ok && visualResponse.status !== 404) {
            addServiceWarning(
              "A visual block changed elsewhere; reload the note before editing it again.",
            );
            hasVisualConflict = visualResponse.status === 409;
            if (!hasVisualConflict) {
              throw new Error("The visual block could not be synchronized with the note.");
            }
            break;
          } else if (visualResponse.ok) {
            const updatedMessage = (await visualResponse.json()) as {
              metadata_json?: { visual_blocks?: Record<string, { block?: StructuredBlock }> };
            };
            const persisted = updatedMessage.metadata_json?.visual_blocks?.[block.id]?.block;
            if (persisted) {
              noteVisualSourceRef.current.set(block.id, JSON.stringify(persisted));
              synchronizedHtml =
                replaceVisualBlockInNoteHtml(synchronizedHtml, persisted) ?? synchronizedHtml;
              try {
                await syncExistingVisualArtifact(activeNote.id, persisted);
              } catch (error) {
                addServiceWarning(
                  error instanceof Error
                    ? error.message
                    : "The saved visual artifact could not be synchronized with this note edit.",
                );
              }
            } else {
              noteVisualSourceRef.current.set(block.id, serializedBlock);
            }
          }
        }
        if (hasVisualConflict) return;
        const noteResponse = (await fetchWithAuth(`/deepspace/chats/${activeNote.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            content_html: synchronizedHtml,
            ...(nextAutoTitle ? { title: nextAutoTitle } : {}),
          }),
        })) as Response;
        if (!noteResponse.ok) {
          throw new Error("The note could not be saved.");
        }
        if (synchronizedHtml !== html) {
          setActiveNote((current) =>
            current?.id === activeNote.id
              ? { ...current, content_html: synchronizedHtml }
              : current,
          );
          setNotes((current) =>
            current.map((item) =>
              item.id === activeNote.id ? { ...item, content_html: synchronizedHtml } : item,
            ),
          );
          await editorRef.current?.replaceHTML(synchronizedHtml);
        }
      } catch (error) {
        console.error("Failed to save DeepSpace note", error);
        addServiceWarning(
          "Your latest note edit could not be saved. Please retry after reconnecting.",
        );
      } finally {
        setIsSaving(false);
      }
    }, 1500);
  };

  const handleVisualBlockChange = useCallback(
    async (_messageId: string, block: StructuredBlock) => {
      const note = activeNote;
      if (!note) return;
      const nextHtml = replaceVisualBlockInNoteHtml(note.content_html ?? "", block);
      if (!nextHtml || nextHtml === (note.content_html ?? "")) return;
      setActiveNote((previous) =>
        previous?.id === note.id ? { ...previous, content_html: nextHtml } : previous,
      );
      setNotes((previous) =>
        previous.map((item) => (item.id === note.id ? { ...item, content_html: nextHtml } : item)),
      );
      noteVisualSourceRef.current.set(block.id, JSON.stringify(block));
      const response = (await fetchWithAuth(`/deepspace/chats/${note.id}`, {
        method: "PATCH",
        body: JSON.stringify({ content_html: nextHtml }),
      })) as Response;
      if (!response.ok) throw new Error("The edited visual could not be saved to this note.");
      await editorRef.current?.replaceHTML(nextHtml);
      try {
        await syncExistingVisualArtifact(note.id, block);
      } catch (error) {
        addServiceWarning(
          error instanceof Error
            ? error.message
            : "The saved visual artifact could not be synchronized with this chat edit.",
        );
      }
    },
    [activeNote, addServiceWarning, syncExistingVisualArtifact],
  );

  const handleSaveVisualArtifact = useCallback(
    async (block: StructuredBlock) => {
      if (!activeNote) {
        throw new Error("Open a conversation before saving this visual to Library.");
      }
      const response = (await fetchWithAuth(
        `/deepspace/library/${activeNote.id}/visual-artifacts`,
        {
          method: "POST",
          body: JSON.stringify({
            block_id: block.id,
            block,
            filename: `${block.id}.visual.json`,
          }),
        },
      )) as Response;
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          String(payload?.detail?.message ?? "The visual artifact could not be saved."),
        );
      }
    },
    [activeNote],
  );

  const handleArtifactVisualChange = useCallback(
    async (block: StructuredBlock) => {
      const note = activeNote;
      if (!note) return;
      const revision = (block as { revision?: number }).revision;
      const response = (await fetchWithAuth(`/deepspace/chats/${note.id}/visual-block`, {
        method: "PATCH",
        body: JSON.stringify({
          block_id: block.id,
          block,
          ...(typeof revision === "number" ? { expected_revision: Math.max(0, revision - 1) } : {}),
        }),
      })) as Response;
      if (!response.ok) {
        if (response.status === 409) {
          addServiceWarning("This artifact changed in another session. Reload it before editing.");
        }
        throw new Error("The artifact change could not be synchronized to chat.");
      }
      const updated = (await response.json()) as {
        metadata_json?: { visual_blocks?: Record<string, { block?: StructuredBlock }> };
      };
      const persisted = updated.metadata_json?.visual_blocks?.[block.id]?.block ?? {
        ...block,
        revision: (revision ?? 0) + 1,
      };
      const nextHtml = replaceVisualBlockInNoteHtml(note.content_html ?? "", persisted);
      if (!nextHtml || nextHtml === (note.content_html ?? "")) return;
      setActiveNote((current) =>
        current?.id === note.id ? { ...current, content_html: nextHtml } : current,
      );
      setNotes((current) =>
        current.map((item) => (item.id === note.id ? { ...item, content_html: nextHtml } : item)),
      );
      noteVisualSourceRef.current.set(block.id, JSON.stringify(persisted));
      const noteResponse = (await fetchWithAuth(`/deepspace/chats/${note.id}`, {
        method: "PATCH",
        body: JSON.stringify({ content_html: nextHtml }),
      })) as Response;
      if (!noteResponse.ok) throw new Error("The synchronized note could not be saved.");
      await editorRef.current?.replaceHTML(nextHtml);
    },
    [activeNote, addServiceWarning],
  );

  const handleAgentNotePreview = useCallback(
    (preview: DeepSpaceAgentNotePreview & { conversationId: string }) => {
      if (preview.conversationId !== activeNote?.id) return;
      if (agentPreviewBaseContentRef.current === null) {
        agentPreviewBaseContentRef.current = activeNote?.content_html ?? "";
      }
      setAgentNotePreview({
        markdown: preview.markdown,
        mode: preview.mode,
        status: preview.status,
      });
    },
    [activeNote?.content_html, activeNote?.id],
  );

  const handleAgentNoteCommitted = useCallback(
    async ({ conversationId, contentHtml }: { conversationId: string; contentHtml: string }) => {
      if (conversationId !== activeNote?.id) return;
      const currentContent = activeNote?.content_html ?? "";
      if (
        agentPreviewBaseContentRef.current !== null &&
        agentPreviewBaseContentRef.current !== currentContent
      ) {
        setAgentNotePreview((previous) =>
          previous ? { ...previous, status: "conflict" } : previous,
        );
        return;
      }
      agentPreviewBaseContentRef.current = null;
      setAgentNotePreview(null);
      setActiveNote((previous) =>
        previous ? { ...previous, content_html: contentHtml } : previous,
      );
      setNotes((previous) =>
        previous.map((note) =>
          note.id === conversationId
            ? { ...note, content_html: contentHtml, updated_at: new Date().toISOString() }
            : note,
        ),
      );
      await editorRef.current?.replaceHTML(contentHtml);
    },
    [activeNote?.content_html, activeNote?.id],
  );

  // ── Layout & Resizing ────────────────────────────────────────────────────

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
  const visibleWorkspacePanel = isSplitView
    ? splitWorkspacePanel
    : panelMode === "chat"
      ? null
      : panelMode;
  const showNotesPanel = visibleWorkspacePanel === "notes";
  const showLibraryPanel = visibleWorkspacePanel === "library";
  const showChatPanel = isSplitView || panelMode === "chat";
  const showMemoryPanel = visibleWorkspacePanel === "memory";
  const showSchedulesPanel = visibleWorkspacePanel === "schedules";
  const panelTransition: Transition = {
    duration: isStackedLayout ? 0.14 : 0.18,
    ease: [0.22, 1, 0.36, 1],
  };
  const shellTransitionClass = isStackedLayout ? "duration-150" : "duration-300";

  const selectWorkspacePanel = (nextPanel: SplitWorkspacePanel) => {
    if (isSplitView) setSplitWorkspacePanel(nextPanel);
    else setPanelMode(nextPanel);
  };

  const toggleSplitView = () => {
    if (isSplitView) {
      setIsSplitView(false);
      setPanelMode(splitWorkspacePanel);
      return;
    }
    if (panelMode !== "chat") setSplitWorkspacePanel(panelMode);
    setIsSplitView(true);
  };

  const legacyPanelMode: "split" | "notes" | "chat" | "memory" = isSplitView
    ? "split"
    : panelMode === "chat" || panelMode === "memory"
      ? panelMode
      : "notes";

  useEffect(() => {
    if (isStackedLayout && isSplitView) {
      queueMicrotask(() => {
        setIsSplitView(false);
        setPanelMode(splitWorkspacePanel);
      });
    }
  }, [isSplitView, isStackedLayout, splitWorkspacePanel]);

  if (isInitialLoading) {
    return (
      <div className="deepspace-theme-scope theme-panel-muted flex h-full w-full items-center justify-center rounded-2xl">
        <Loader2 className="text-primary h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="deepspace-theme-scope relative flex h-full w-full overflow-hidden rounded-2xl bg-transparent">
      {serviceWarnings.length > 0 && (
        <div className="pointer-events-none absolute top-2 right-2 left-2 z-30 flex justify-center">
          <div
            role="status"
            className="pointer-events-auto flex max-w-3xl items-center gap-3 rounded-xl border border-amber-400/25 bg-amber-950/80 px-4 py-3 text-xs text-amber-100 shadow-xl backdrop-blur-xl"
          >
            <span className="min-w-0 flex-1">{serviceWarnings.join(" ")}</span>
            <button
              type="button"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-amber-300/25 px-2.5 py-1.5 font-semibold hover:bg-amber-300/10"
              onClick={() => {
                setServiceWarnings([]);
                setIsInitialLoading(true);
                setServiceRetryKey((value) => value + 1);
              }}
            >
              <RefreshCw size={12} />
              Retry
            </button>
          </div>
        </div>
      )}

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
              <div className="border-glass-border bg-surface-0/90 pointer-events-auto flex items-center gap-0.5 rounded-full border p-0.5 shadow-xl backdrop-blur-md sm:gap-1 sm:p-1">
                <IconTooltipButton
                  label="Chat"
                  active={!isSplitView && panelMode === "chat"}
                  icon={<Bot size={18} />}
                  onClick={() => {
                    setIsSplitView(false);
                    setPanelMode("chat");
                  }}
                />
                <IconTooltipButton
                  label="Schedules"
                  active={visibleWorkspacePanel === "schedules"}
                  icon={<CalendarClock size={16} />}
                  onClick={() => selectWorkspacePanel("schedules")}
                />
                <IconTooltipButton
                  label="Memory"
                  active={visibleWorkspacePanel === "memory"}
                  icon={<Database size={18} />}
                  onClick={() => selectWorkspacePanel("memory")}
                />
                <IconTooltipButton
                  label="Split view"
                  active={isSplitView}
                  icon={<Columns2 size={15} />}
                  onClick={toggleSplitView}
                />
                <IconTooltipButton
                  label="Notes"
                  active={visibleWorkspacePanel === "notes"}
                  icon={<PanelRightClose size={15} />}
                  onClick={() => selectWorkspacePanel("notes")}
                />
                <IconTooltipButton
                  label="Library"
                  active={visibleWorkspacePanel === "library"}
                  icon={<FolderOpen size={16} />}
                  onClick={() => selectWorkspacePanel("library")}
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
          {visibleWorkspacePanel ? (
            <motion.section
              initial={{ opacity: 0, x: isStackedLayout ? 0 : -12, y: isStackedLayout ? -12 : 0 }}
              animate={{ opacity: 1, x: 0, y: 0 }}
              transition={panelTransition}
              className={`relative flex min-h-0 min-w-0 flex-col overflow-hidden ${isStackedLayout ? "h-full w-full flex-[1_1_auto]" : showChatPanel ? "h-full flex-[0_0_auto]" : "h-full w-full"}`}
              style={!isStackedLayout && showChatPanel ? { flexBasis: `${leftWidth}%` } : undefined}
            >
              <AnimatePresence initial={false} mode="sync">
                {showNotesPanel ? (
                  <motion.div
                    key="notes-panel"
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={panelTransition}
                    className="absolute inset-0 will-change-transform"
                  >
                    <DeepSpaceEditor
                      ref={editorRef}
                      initialContent={activeNote?.content_html || ""}
                      onChange={handleEditorChange}
                      conversationId={activeNote?.id}
                      isSaving={isSaving}
                      agentPreview={agentNotePreview}
                      showCollapseControls={false}
                      panelMode={legacyPanelMode}
                      onSetPanelMode={(mode) => {
                        if (mode === "split") toggleSplitView();
                        else {
                          setIsSplitView(false);
                          setPanelMode(mode);
                        }
                      }}
                    />
                  </motion.div>
                ) : null}
                {showLibraryPanel ? (
                  <motion.div
                    key="library-panel"
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={panelTransition}
                    className="absolute inset-0 will-change-transform"
                  >
                    <DeepSpaceLibraryDrawer
                      open
                      embedded
                      conversationId={activeNote?.id ?? null}
                      onClose={() => {
                        if (isSplitView) setSplitWorkspacePanel("notes");
                        else setPanelMode("chat");
                      }}
                      onVisualArtifactChange={handleArtifactVisualChange}
                    />
                  </motion.div>
                ) : null}
                {showMemoryPanel ? (
                  <motion.div
                    key="memory-panel"
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={panelTransition}
                    className="absolute inset-0 overflow-auto will-change-transform"
                  >
                    <MemoryPanel />
                  </motion.div>
                ) : null}
                {showSchedulesPanel ? (
                  <motion.div
                    key="schedules-panel"
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={panelTransition}
                    className="absolute inset-0 overflow-auto will-change-transform"
                  >
                    <DeepSpaceSchedulesPanel conversationId={activeNote?.id ?? null} />
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </motion.section>
          ) : null}

          {visibleWorkspacePanel && showChatPanel && !isStackedLayout ? (
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
                  onConversationRenamed={(note) => {
                    setNotes((prev) => prev.map((item) => (item.id === note.id ? note : item)));
                    setActiveNote((prev) => (prev?.id === note.id ? note : prev));
                  }}
                  onConversationUnavailable={(conversationId) => {
                    window.localStorage.removeItem(ACTIVE_NOTE_KEY);
                    setNotes((previous) => previous.filter((item) => item.id !== conversationId));
                    setActiveNote((active) => (active?.id === conversationId ? null : active));
                  }}
                  onSelectNote={(noteId) => {
                    const note = notes.find((n) => n.id === noteId);
                    if (note) {
                      setActiveNote(note);
                    }
                  }}
                  onNewNote={() => {
                    return createNote();
                  }}
                  onInsertLatestAnswer={insertAnswer}
                  onAgentNotePreview={handleAgentNotePreview}
                  onAgentNoteCommitted={handleAgentNoteCommitted}
                  onVisualBlockChange={handleVisualBlockChange}
                  onSaveVisualArtifact={handleSaveVisualArtifact}
                  panelMode={legacyPanelMode}
                  onSetPanelMode={(mode) => {
                    if (mode === "split") toggleSplitView();
                    else {
                      setIsSplitView(false);
                      setPanelMode(mode);
                    }
                  }}
                  isHistoryOpen={isHistoryOpen}
                  onSetHistoryOpen={setIsHistoryOpen}
                />
              </motion.section>
            ) : null}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
