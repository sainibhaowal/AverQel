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
import {
  clearDeepSpaceNoteDraft,
  readDeepSpaceNoteDraft,
  writeDeepSpaceNoteDraft,
  type DeepSpaceLocalNoteDraft,
} from "../_lib/note-drafts";
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
const NOTE_AUTOSAVE_DEBOUNCE_MS = 1_500;

type NoteSaveState = "idle" | "saving" | "saved" | "local" | "failed";

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
      } else if (
        kind === "chart" ||
        kind === "card" ||
        kind === "gallery" ||
        kind === "infographic"
      ) {
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

function visualRevisionInMessage(
  message: {
    content?: unknown;
    metadata_json?: unknown;
  },
  blockId: string,
  sourceMarkdown?: string | null,
): number | null {
  const revisions: number[] = [];
  const addRevision = (value: unknown) => {
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
      revisions.push(value);
    }
  };
  const metadata =
    message.metadata_json && typeof message.metadata_json === "object"
      ? (message.metadata_json as Record<string, unknown>)
      : {};
  const visualBlocks = metadata.visual_blocks;
  if (visualBlocks && typeof visualBlocks === "object") {
    const record = (visualBlocks as Record<string, unknown>)[blockId];
    if (record && typeof record === "object") {
      addRevision((record as Record<string, unknown>).revision);
    }
  }

  const metadataBlocks = metadata.blocks;
  if (Array.isArray(metadataBlocks)) {
    const block = metadataBlocks.find(
      (candidate) =>
        candidate &&
        typeof candidate === "object" &&
        ((candidate as Record<string, unknown>).id === blockId ||
          (candidate as Record<string, unknown>).block_id === blockId),
    ) as Record<string, unknown> | undefined;
    if (block) {
      addRevision(block.revision);
    }
  }

  const content = typeof message.content === "string" ? message.content : "";
  if (sourceMarkdown?.trim() && content.includes(sourceMarkdown.trim())) revisions.push(0);

  const fences = /```(?:chart|card|graph|gallery|infographic)[^\r\n]*\r?\n([\s\S]*?)\r?\n```/gi;
  for (const match of content.matchAll(fences)) {
    try {
      const block = JSON.parse(match[1] ?? "") as Record<string, unknown>;
      if (block.id !== blockId && block.block_id !== blockId) continue;
      addRevision(block.revision ?? 0);
    } catch {
      // Malformed visual fences are not a revision source.
    }
  }
  return revisions.length ? Math.max(...revisions) : null;
}

function apiErrorMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const record = payload as Record<string, unknown>;
  const detail = record.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const message = (detail as Record<string, unknown>).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" ? (item as Record<string, unknown>).msg : null,
      )
      .filter((message): message is string => typeof message === "string" && Boolean(message.trim()));
    if (messages.length) return messages.join("; ");
  }
  const error = record.error;
  if (error && typeof error === "object") {
    const message = (error as Record<string, unknown>).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return null;
}

async function getResponseErrorMessage(response: Response, fallback: string): Promise<string> {
  const payload = await response.json().catch(() => null);
  return (
    apiErrorMessage(payload) ??
    `${fallback} (HTTP ${response.status}). Retry the edit; your saved Library copy is preserved.`
  );
}

async function getVisualBlockChatRevision(
  conversationId: string,
  blockId: string,
  sourceMarkdown?: string | null,
): Promise<number | null> {
  const response = (await fetchWithAuth(`/deepspace/chats/${conversationId}/messages`)) as Response;
  if (!response.ok) {
    throw new Error(
      await getResponseErrorMessage(response, "The chat visual revision could not be loaded"),
    );
  }
  const history = (await response.json()) as {
    messages?: Array<{ role?: string; content?: unknown; metadata_json?: unknown }>;
  };
  const messages = Array.isArray(history.messages) ? history.messages : [];
  for (const message of [...messages].reverse()) {
    if (message.role !== "assistant") continue;
    const revision = visualRevisionInMessage(message, blockId, sourceMarkdown);
    if (revision !== null) return revision;
  }
  return null;
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
  const [noteSaveStates, setNoteSaveStates] = useState<Record<string, NoteSaveState>>({});
  const [recoveryDraft, setRecoveryDraft] = useState<DeepSpaceLocalNoteDraft | null>(null);
  const [agentNotePreview, setAgentNotePreview] = useState<DeepSpaceAgentNotePreview | null>(null);
  // Chat is the primary DeepSpace workspace. Notes remains available through
  // the workspace switcher and as the default left panel when split view is
  // explicitly enabled.
  const [panelMode, setPanelMode] = useState<WorkspacePanel>("chat");
  const editorRef = useRef<DeepSpaceEditorHandle>(null);
  const agentPreviewBaseContentRef = useRef<string | null>(null);
  const noteVisualSourceRef = useRef(new Map<string, string>());
  const visualBlockSyncQueuesRef = useRef(new Map<string, Promise<StructuredBlock | null>>());
  const pendingNoteSavesRef = useRef(new Map<string, DeepSpaceLocalNoteDraft>());
  const localDraftStoredRef = useRef(new Map<string, boolean>());
  const noteSaveTimersRef = useRef(new Map<string, number>());
  const inFlightNoteSavesRef = useRef(new Map<string, Promise<void>>());
  const scheduleNoteSaveRef = useRef<(conversationId: string, delayMs?: number) => void>(() => {});
  const flushPendingNoteSavesRef = useRef<() => void>(() => {});
  const savePendingNoteRef = useRef<(conversationId: string) => Promise<void>>(async () => {});
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

  const updateNoteSaveState = useCallback((conversationId: string, state: NoteSaveState) => {
    setNoteSaveStates((previous) => ({ ...previous, [conversationId]: state }));
  }, []);

  const syncVisualBlockToChat = useCallback(
    async (conversationId: string, block: StructuredBlock): Promise<StructuredBlock | null> => {
      const queueKey = `${conversationId}:${block.id}`;
      const previous = visualBlockSyncQueuesRef.current.get(queueKey) ?? Promise.resolve(null);
      const operation = previous.catch(() => null).then(async () => {
        const sourceMarkdown =
          block.type === "diagram" && block.source === "mermaid" ? block.source_markdown : null;
        const expectedRevision = await getVisualBlockChatRevision(
          conversationId,
          block.id,
          sourceMarkdown,
        );
        if (expectedRevision === null) return null;

        const response = (await fetchWithAuth(`/deepspace/chats/${conversationId}/visual-block`, {
          method: "PATCH",
          body: JSON.stringify({
            block_id: block.id,
            block,
            expected_revision: expectedRevision,
          }),
        })) as Response;
        if (response.status === 404) return null;
        if (!response.ok) {
          const message = await getResponseErrorMessage(
            response,
            response.status === 422
              ? "The visual block was rejected by chat validation"
              : "The visual block could not be synchronized to chat",
          );
          if (response.status === 409) addServiceWarning(message);
          const error = new Error(message) as Error & { status?: number };
          error.status = response.status;
          throw error;
        }

        const updated = (await response.json()) as {
          metadata_json?: { visual_blocks?: Record<string, { block?: StructuredBlock }> };
        };
        return (
          updated.metadata_json?.visual_blocks?.[block.id]?.block ?? {
            ...block,
            revision: Math.max(
              expectedRevision + 1,
              (block as StructuredBlock & { revision?: number }).revision ?? 0,
            ),
          }
        );
      });

      visualBlockSyncQueuesRef.current.set(queueKey, operation);
      try {
        return await operation;
      } finally {
        if (visualBlockSyncQueuesRef.current.get(queueKey) === operation) {
          visualBlockSyncQueuesRef.current.delete(queueKey);
        }
      }
    },
    [addServiceWarning],
  );

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
        throw new Error(
          await getResponseErrorMessage(
            response,
            "The saved visual artifact could not be synchronized with this edit",
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
        activeNoteRef.current = newNote;
        setActiveNote(newNote);
        setRecoveryDraft(null);
        return newNote;
      }
    } catch (err) {
      console.error("Failed to create note", err);
    }
    return null;
  };

  const activateNote = useCallback(
    (serverNote: DeepSpaceNote | null) => {
      if (!serverNote) {
        activeNoteRef.current = null;
        setActiveNote(null);
        setRecoveryDraft(null);
        return;
      }

      let draft = pendingNoteSavesRef.current.get(serverNote.id) ?? null;
      if (!draft) {
        try {
          draft = readDeepSpaceNoteDraft(window.sessionStorage, serverNote.id);
        } catch {
          draft = null;
        }
      }

      let selectedNote = serverNote;
      let conflictingDraft: DeepSpaceLocalNoteDraft | null = null;
      if (draft) {
        const serverAlreadyHasDraft =
          (serverNote.content_html ?? "") === draft.contentHtml && serverNote.title === draft.title;
        if (serverAlreadyHasDraft) {
          pendingNoteSavesRef.current.delete(serverNote.id);
          localDraftStoredRef.current.delete(serverNote.id);
          try {
            clearDeepSpaceNoteDraft(window.sessionStorage, serverNote.id);
          } catch {
            // The server copy is authoritative even if browser storage is unavailable.
          }
          updateNoteSaveState(serverNote.id, "saved");
        } else if (
          pendingNoteSavesRef.current.has(serverNote.id) ||
          draft.baseUpdatedAt === serverNote.updated_at
        ) {
          selectedNote = {
            ...serverNote,
            content_html: draft.contentHtml,
            title: draft.title,
          };
          pendingNoteSavesRef.current.set(serverNote.id, draft);
          localDraftStoredRef.current.set(serverNote.id, true);
          updateNoteSaveState(serverNote.id, "saving");
        } else {
          conflictingDraft = draft;
        }
      }

      activeNoteRef.current = selectedNote;
      setActiveNote(selectedNote);
      setRecoveryDraft(conflictingDraft);
      if (selectedNote !== serverNote) {
        setNotes((previous) =>
          previous.map((item) => (item.id === selectedNote.id ? selectedNote : item)),
        );
      }
    },
    [updateNoteSaveState],
  );

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
        activateNote(
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
  }, [activateNote, addServiceWarning, fetchNotes, serviceRetryKey]);

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

  const savePendingNote = useCallback(
    async (conversationId: string) => {
      const inFlight = inFlightNoteSavesRef.current.get(conversationId);
      if (inFlight) {
        await inFlight;
        return;
      }
      const draft = pendingNoteSavesRef.current.get(conversationId);
      if (!draft) return;

      updateNoteSaveState(conversationId, "saving");
      const operation = (async () => {
        try {
          // Keep rich visual blocks revisioned before writing the note HTML.
          let synchronizedHtml = preserveLatestVisualBlockRevisions(
            draft.contentHtml,
            noteVisualSourceRef.current,
          );
          let hasVisualConflict = false;
          for (const block of extractPersistedVisualBlocks(synchronizedHtml)) {
            const serializedBlock = JSON.stringify(block);
            if (noteVisualSourceRef.current.get(block.id) === serializedBlock) continue;
            let persisted: StructuredBlock | null;
            try {
              // Re-read the chat revision instead of trusting a note's revision;
              // note and chat revisions can advance independently.
              persisted = await syncVisualBlockToChat(conversationId, block);
            } catch (error) {
              const status = (error as Error & { status?: number }).status;
              addServiceWarning(
                error instanceof Error
                  ? error.message
                  : "A visual block could not be synchronized. Your draft is kept on this tab.",
              );
              hasVisualConflict = status === 409;
              if (!hasVisualConflict) {
                throw error;
              }
              break;
            }
            if (persisted) {
              noteVisualSourceRef.current.set(block.id, JSON.stringify(persisted));
              synchronizedHtml =
                replaceVisualBlockInNoteHtml(synchronizedHtml, persisted) ?? synchronizedHtml;
              try {
                await syncExistingVisualArtifact(conversationId, persisted);
              } catch (error) {
                addServiceWarning(
                  error instanceof Error
                    ? error.message
                    : "The saved visual artifact could not be synchronized with this note edit.",
                );
              }
            } else {
              // A note-only visual has no assistant message revision to update.
              noteVisualSourceRef.current.set(block.id, serializedBlock);
            }
          }
          if (hasVisualConflict) {
            updateNoteSaveState(conversationId, "local");
            return;
          }

          const noteResponse = (await fetchWithAuth(`/deepspace/chats/${conversationId}`, {
            method: "PATCH",
            body: JSON.stringify({
              content_html: synchronizedHtml,
              title: draft.title,
            }),
          })) as Response;
          if (!noteResponse.ok) throw new Error("The note could not be saved.");
          const savedNote = (await noteResponse.json().catch(() => null)) as {
            title?: unknown;
            content_html?: unknown;
            updated_at?: unknown;
          } | null;
          if (
            !savedNote ||
            savedNote.content_html !== synchronizedHtml ||
            typeof savedNote.title !== "string" ||
            savedNote.title.trim() !== draft.title.trim()
          ) {
            throw new Error("The server did not confirm the saved note content.");
          }
          const savedUpdatedAt =
            typeof savedNote?.updated_at === "string" ? savedNote.updated_at : undefined;
          const latestDraft = pendingNoteSavesRef.current.get(conversationId);
          const latestMatchesSaved =
            !latestDraft ||
            (latestDraft.contentHtml === draft.contentHtml && latestDraft.title === draft.title);

          setNotes((current) =>
            current.map((item) =>
              item.id === conversationId
                ? {
                    ...item,
                    ...(latestMatchesSaved
                      ? { content_html: synchronizedHtml, title: draft.title }
                      : {}),
                    ...(savedUpdatedAt ? { updated_at: savedUpdatedAt } : {}),
                  }
                : item,
            ),
          );
          setActiveNote((current) => {
            if (current?.id !== conversationId) return current;
            return {
              ...current,
              ...(latestMatchesSaved ? { content_html: synchronizedHtml, title: draft.title } : {}),
              ...(savedUpdatedAt ? { updated_at: savedUpdatedAt } : {}),
            };
          });

          if (latestMatchesSaved) {
            pendingNoteSavesRef.current.delete(conversationId);
            localDraftStoredRef.current.delete(conversationId);
            try {
              const localDraft = readDeepSpaceNoteDraft(window.sessionStorage, conversationId);
              if (
                localDraft?.contentHtml === draft.contentHtml &&
                localDraft.title === draft.title
              ) {
                clearDeepSpaceNoteDraft(window.sessionStorage, conversationId);
              }
            } catch {
              // The server save is authoritative even when tab storage is blocked.
            }
            updateNoteSaveState(conversationId, "saved");
          } else if (latestDraft) {
            const advancedDraft = {
              ...latestDraft,
              baseUpdatedAt: savedUpdatedAt ?? latestDraft.baseUpdatedAt,
            };
            pendingNoteSavesRef.current.set(conversationId, advancedDraft);
            let stored = false;
            try {
              stored = writeDeepSpaceNoteDraft(window.sessionStorage, advancedDraft);
            } catch {
              stored = false;
            }
            localDraftStoredRef.current.set(conversationId, stored);
            updateNoteSaveState(conversationId, stored ? "saving" : "failed");
          }
        } catch (error) {
          console.error("Failed to save DeepSpace note", error);
          const hasLocalCopy = localDraftStoredRef.current.get(conversationId) === true;
          updateNoteSaveState(conversationId, hasLocalCopy ? "local" : "failed");
          addServiceWarning(
            hasLocalCopy
              ? "The server did not confirm this save. Your latest draft is kept in this tab; retry when the server is available."
              : "The server did not confirm this save, and a recovery copy could not be stored. Keep this page open and retry.",
          );
        } finally {
          inFlightNoteSavesRef.current.delete(conversationId);
          const latestDraft = pendingNoteSavesRef.current.get(conversationId);
          if (
            latestDraft &&
            (latestDraft.contentHtml !== draft.contentHtml || latestDraft.title !== draft.title)
          ) {
            scheduleNoteSaveRef.current(conversationId, 0);
          }
        }
      })();
      inFlightNoteSavesRef.current.set(conversationId, operation);
      await operation;
    },
    [
      addServiceWarning,
      syncExistingVisualArtifact,
      syncVisualBlockToChat,
      updateNoteSaveState,
    ],
  );

  const scheduleNoteSave = useCallback(
    (conversationId: string, delayMs = NOTE_AUTOSAVE_DEBOUNCE_MS) => {
      const previousTimer = noteSaveTimersRef.current.get(conversationId);
      if (previousTimer) window.clearTimeout(previousTimer);
      const timer = window.setTimeout(() => {
        noteSaveTimersRef.current.delete(conversationId);
        void savePendingNote(conversationId);
      }, delayMs);
      noteSaveTimersRef.current.set(conversationId, timer);
    },
    [savePendingNote],
  );
  const flushPendingNoteSaves = useCallback(() => {
    for (const conversationId of pendingNoteSavesRef.current.keys()) {
      const timer = noteSaveTimersRef.current.get(conversationId);
      if (timer) window.clearTimeout(timer);
      noteSaveTimersRef.current.delete(conversationId);
      void savePendingNoteRef.current(conversationId);
    }
  }, []);
  useEffect(() => {
    scheduleNoteSaveRef.current = scheduleNoteSave;
    savePendingNoteRef.current = savePendingNote;
    flushPendingNoteSavesRef.current = flushPendingNoteSaves;
  }, [flushPendingNoteSaves, savePendingNote, scheduleNoteSave]);

  useEffect(() => {
    if (activeNote?.id && pendingNoteSavesRef.current.has(activeNote.id)) {
      scheduleNoteSave(activeNote.id, 0);
    }
  }, [activeNote?.id, scheduleNoteSave]);

  const queueNoteContentSave = useCallback(
    (
      note: DeepSpaceNote,
      contentHtml: string,
      title: string,
      delayMs = NOTE_AUTOSAVE_DEBOUNCE_MS,
    ) => {
      const previousDraft = pendingNoteSavesRef.current.get(note.id);
      const draft: DeepSpaceLocalNoteDraft = {
        version: 1,
        conversationId: note.id,
        contentHtml,
        title,
        baseUpdatedAt: previousDraft?.baseUpdatedAt ?? note.updated_at,
        updatedAt: Date.now(),
      };
      pendingNoteSavesRef.current.set(note.id, draft);
      let stored = false;
      try {
        stored = writeDeepSpaceNoteDraft(window.sessionStorage, draft);
      } catch {
        stored = false;
      }
      localDraftStoredRef.current.set(note.id, stored);
      updateNoteSaveState(note.id, stored ? "saving" : "failed");

      const updatedNote = { ...note, content_html: contentHtml, title };
      if (activeNoteRef.current?.id === note.id) {
        activeNoteRef.current = updatedNote;
        setActiveNote(updatedNote);
      }
      setNotes((previous) =>
        previous.map((item) =>
          item.id === note.id ? { ...item, content_html: contentHtml, title } : item,
        ),
      );
      scheduleNoteSave(note.id, delayMs);
      return stored;
    },
    [scheduleNoteSave, updateNoteSaveState],
  );

  const handleEditorChange = (html: string) => {
    const note = activeNoteRef.current ?? activeNote;
    if (!note) return;
    // Keep the newest saved visual revision if a delayed editor event arrives.
    const currentHtml = preserveLatestVisualBlockRevisions(html, noteVisualSourceRef.current);
    const nextTitle =
      (note.title === DEFAULT_NOTE_TITLE ? deriveNoteTitleFromContent(currentHtml) : null) ??
      note.title;
    if (currentHtml === (note.content_html ?? "") && nextTitle === note.title) return;
    queueNoteContentSave(note, currentHtml, nextTitle);
  };

  const restoreConflictingDraft = useCallback(() => {
    const note = activeNoteRef.current;
    if (!note || !recoveryDraft || recoveryDraft.conversationId !== note.id) return;
    const restoredDraft = {
      ...recoveryDraft,
      baseUpdatedAt: note.updated_at,
      updatedAt: Date.now(),
    };
    let stored = false;
    try {
      stored = writeDeepSpaceNoteDraft(window.sessionStorage, restoredDraft);
    } catch {
      stored = false;
    }
    pendingNoteSavesRef.current.set(note.id, restoredDraft);
    localDraftStoredRef.current.set(note.id, stored);
    const restoredNote = {
      ...note,
      content_html: restoredDraft.contentHtml,
      title: restoredDraft.title,
    };
    activeNoteRef.current = restoredNote;
    setActiveNote(restoredNote);
    setNotes((previous) => previous.map((item) => (item.id === note.id ? restoredNote : item)));
    setRecoveryDraft(null);
    updateNoteSaveState(note.id, stored ? "saving" : "failed");
    void editorRef.current?.replaceHTML(restoredDraft.contentHtml);
    scheduleNoteSave(note.id, 0);
  }, [recoveryDraft, scheduleNoteSave, updateNoteSaveState]);

  const discardConflictingDraft = useCallback(() => {
    if (!recoveryDraft) return;
    try {
      clearDeepSpaceNoteDraft(window.sessionStorage, recoveryDraft.conversationId);
    } catch {
      // The server copy remains selected if storage is unavailable.
    }
    pendingNoteSavesRef.current.delete(recoveryDraft.conversationId);
    localDraftStoredRef.current.delete(recoveryDraft.conversationId);
    noteSaveTimersRef.current.delete(recoveryDraft.conversationId);
    updateNoteSaveState(recoveryDraft.conversationId, "saved");
    setRecoveryDraft(null);
  }, [recoveryDraft, updateNoteSaveState]);

  useEffect(() => {
    const flushOnExit = () => flushPendingNoteSavesRef.current();
    const flushWhenHidden = () => {
      if (document.visibilityState === "hidden") flushPendingNoteSavesRef.current();
    };
    window.addEventListener("pagehide", flushOnExit);
    window.addEventListener("online", flushOnExit);
    document.addEventListener("visibilitychange", flushWhenHidden);
    return () => {
      window.removeEventListener("pagehide", flushOnExit);
      window.removeEventListener("online", flushOnExit);
      document.removeEventListener("visibilitychange", flushWhenHidden);
    };
  }, []);

  useEffect(
    () => () => {
      for (const timer of noteSaveTimersRef.current.values()) window.clearTimeout(timer);
      noteSaveTimersRef.current.clear();
    },
    [],
  );

  const handleVisualBlockChange = useCallback(
    async (_messageId: string, block: StructuredBlock) => {
      const note = activeNoteRef.current ?? activeNote;
      if (!note) return;
      const nextHtml = replaceVisualBlockInNoteHtml(note.content_html ?? "", block);
      if (!nextHtml || nextHtml === (note.content_html ?? "")) return;
      noteVisualSourceRef.current.set(block.id, JSON.stringify(block));
      queueNoteContentSave(note, nextHtml, note.title, 0);
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
    [activeNote, addServiceWarning, queueNoteContentSave, syncExistingVisualArtifact],
  );

  const handleSaveVisualArtifact = useCallback(
    async (block: StructuredBlock) => {
      if (!activeNote) {
        throw new Error("Open a conversation before saving this visual to Library.");
      }
      const entriesResponse = (await fetchWithAuth(`/deepspace/library/${activeNote.id}/entries`, {
        timeoutMs: 8_000,
      })) as Response;
      if (!entriesResponse.ok) {
        throw new Error("The Library could not be checked for an existing visual artifact.");
      }
      const entries = (await entriesResponse.json()) as {
        files?: Array<{
          name?: string;
          version?: number;
          source?: string;
          metadata_json?: unknown;
        }>;
      };
      const existing = (entries.files ?? []).find((file) => {
        const metadata =
          file.metadata_json && typeof file.metadata_json === "object"
            ? (file.metadata_json as { visual_document?: { block_id?: unknown } })
            : null;
        return (
          metadata?.visual_document?.block_id === block.id ||
          (file.source === "visual_editor" && file.name === `${block.id}.visual.json`)
        );
      });
      if (existing && (typeof existing.version !== "number" || !existing.name)) {
        throw new Error("The existing visual artifact is missing its revision information.");
      }
      const response = (await fetchWithAuth(
        `/deepspace/library/${activeNote.id}/visual-artifacts`,
        {
          method: "POST",
          body: JSON.stringify({
            block_id: block.id,
            block,
            filename: existing?.name ?? `${block.id}.visual.json`,
            ...(existing ? { expected_version: existing.version } : {}),
          }),
        },
      )) as Response;
      if (!response.ok) {
        throw new Error(
          await getResponseErrorMessage(
            response,
            response.status === 409
              ? "The visual artifact changed in another session. Reload before saving"
              : "The visual artifact could not be saved",
          ),
        );
      }
    },
    [activeNote],
  );

  const handleArtifactVisualChange = useCallback(
    async (block: StructuredBlock) => {
      const note = activeNoteRef.current ?? activeNote;
      if (!note) return;
      const persisted = (await syncVisualBlockToChat(note.id, block)) ?? block;
      const nextHtml = replaceVisualBlockInNoteHtml(note.content_html ?? "", persisted);
      if (!nextHtml || nextHtml === (note.content_html ?? "")) return;
      noteVisualSourceRef.current.set(block.id, JSON.stringify(persisted));
      queueNoteContentSave(note, nextHtml, note.title, 0);
      await editorRef.current?.replaceHTML(nextHtml);
    },
    [activeNote, queueNoteContentSave, syncVisualBlockToChat],
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
                    className="absolute inset-0 flex flex-col will-change-transform"
                  >
                    {recoveryDraft?.conversationId === activeNote?.id ? (
                      <div
                        role="alert"
                        className="text-foreground flex shrink-0 flex-wrap items-center gap-3 border-b border-amber-400/30 bg-amber-400/[0.08] px-4 py-3 text-xs"
                      >
                        <span className="min-w-0 flex-1">
                          A local draft and the saved note differ. Restore the local draft only if
                          you want it to replace the newer saved note.
                        </span>
                        <button
                          type="button"
                          onClick={restoreConflictingDraft}
                          className="bg-surface-1 hover:bg-surface-2 rounded-lg border border-amber-300/40 px-3 py-1.5 font-semibold"
                        >
                          Restore local draft
                        </button>
                        <button
                          type="button"
                          onClick={discardConflictingDraft}
                          className="text-muted-foreground hover:text-foreground px-2 py-1.5"
                        >
                          Discard draft
                        </button>
                      </div>
                    ) : null}
                    <div
                      className="min-h-0 flex-1"
                      inert={recoveryDraft?.conversationId === activeNote?.id}
                    >
                      <DeepSpaceEditor
                        ref={editorRef}
                        initialContent={activeNote?.content_html || ""}
                        onChange={handleEditorChange}
                        conversationId={activeNote?.id}
                        saveStatus={activeNote ? (noteSaveStates[activeNote.id] ?? "idle") : "idle"}
                        onRetrySave={() => {
                          if (!activeNote) return;
                          updateNoteSaveState(activeNote.id, "saving");
                          scheduleNoteSave(activeNote.id, 0);
                        }}
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
                    </div>
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
                    pendingNoteSavesRef.current.delete(conversationId);
                    localDraftStoredRef.current.delete(conversationId);
                    const timer = noteSaveTimersRef.current.get(conversationId);
                    if (timer) window.clearTimeout(timer);
                    noteSaveTimersRef.current.delete(conversationId);
                    try {
                      clearDeepSpaceNoteDraft(window.sessionStorage, conversationId);
                    } catch {
                      // The unavailable conversation will not be restored from this tab.
                    }
                    setNotes((previous) => previous.filter((item) => item.id !== conversationId));
                    setActiveNote((active) => (active?.id === conversationId ? null : active));
                  }}
                  onSelectNote={(noteId) => {
                    const note = notes.find((n) => n.id === noteId);
                    if (note) {
                      activateNote(note);
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
