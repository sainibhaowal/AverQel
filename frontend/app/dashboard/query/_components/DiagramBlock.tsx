"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Eye, GitBranch, Minimize2, Pencil, Plus, Save, Sparkles, Trash2 } from "lucide-react";

import type { StreamDiagramBlock } from "../_lib/stream-protocol";
import { isMermaidErrorSvg } from "../_lib/mermaid";

import CodeBlock, { sanitizeMermaidSyntax } from "./CodeBlock";
import GraphBlock from "./GraphBlock";

interface DiagramBlockProps {
  block: StreamDiagramBlock;
  isStreaming?: boolean;
  fillHeight?: boolean;
  onChange?: (
    block: StreamDiagramBlock,
  ) => void | boolean | StreamDiagramBlock | Promise<void | boolean | StreamDiagramBlock>;
  onSaveArtifact?: (block: StreamDiagramBlock) => void | Promise<void>;
}

type GanttTask = {
  name: string;
  id: string;
  start: string;
  duration: string;
  milestone: boolean;
  section: string;
  dependency?: string;
};

type ClassDefinition = {
  name: string;
  members: string[];
};

type ClassRelationship = {
  left: string;
  operator: string;
  right: string;
  label: string;
};

type StructuredDraft =
  | { kind: "gantt"; title: string; dateFormat: string; axisFormat: string; tasks: GanttTask[] }
  | { kind: "class"; classes: ClassDefinition[]; relationships: ClassRelationship[] };

function parseStructuredDraft(
  diagramType: StreamDiagramBlock["diagram_type"],
  syntax: string,
): StructuredDraft | null {
  if (diagramType === "mermaid_gantt") {
    const lines = syntax.split(/\r?\n/);
    let section = "Plan";
    const tasks: GanttTask[] = [];
    let title = "";
    let dateFormat = "YYYY-MM-DD";
    let axisFormat = "%m/%d";
    for (const raw of lines.slice(1)) {
      const line = raw.trim();
      if (!line) continue;
      if (line.startsWith("title ")) {
        title = line.slice(6).trim();
        continue;
      }
      if (line.startsWith("dateFormat ")) {
        dateFormat = line.slice(11).trim() || dateFormat;
        continue;
      }
      if (line.startsWith("axisFormat ")) {
        axisFormat = line.slice(11).trim() || axisFormat;
        continue;
      }
      if (line.startsWith("section ")) {
        section = line.slice(8).trim() || section;
        continue;
      }
      const [namePart, fieldsPart] = line.split(/\s*:\s*/, 2);
      if (!fieldsPart) continue;
      const fields = fieldsPart
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      const milestoneIndex = fields.findIndex((value) => value === "milestone");
      const filtered = fields.filter((value) => value !== "milestone");
      const id = filtered[0] ?? `task-${tasks.length + 1}`;
      const start = filtered[1] ?? "";
      const duration = filtered[2] ?? "1d";
      tasks.push({
        name: namePart.trim(),
        id,
        start,
        duration,
        milestone: milestoneIndex >= 0,
        section,
        dependency: start.startsWith("after ") ? start.slice(6).trim() : undefined,
      });
    }
    return { kind: "gantt", title, dateFormat, axisFormat, tasks };
  }

  if (diagramType === "mermaid_class") {
    const classes: ClassDefinition[] = [];
    const classPattern = /class\s+([\w.-]+)\s*\{([\s\S]*?)\}/g;
    let match: RegExpExecArray | null;
    while ((match = classPattern.exec(syntax)) !== null) {
      classes.push({
        name: match[1] ?? `Class${classes.length + 1}`,
        members: (match[2] ?? "")
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean),
      });
    }
    if (classes.length === 0) {
      const names = Array.from(syntax.matchAll(/\bclass\s+([\w.-]+)/g)).map((item) => item[1]);
      for (const name of names) classes.push({ name: name ?? "Class", members: [] });
    }
    const relationships: ClassRelationship[] = [];
    for (const raw of syntax.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith("classDiagram") || line.startsWith("class ")) continue;
      const relationship = line.match(/^([\w.-]+)\s+([.\-o*<>|]+)\s+([\w.-]+)(?:\s*:\s*(.*))?$/);
      if (relationship) {
        relationships.push({
          left: relationship[1] ?? "",
          operator: relationship[2] ?? "--> ",
          right: relationship[3] ?? "",
          label: relationship[4] ?? "",
        });
      }
    }
    return { kind: "class", classes, relationships };
  }
  return null;
}

function generateStructuredSyntax(draft: StructuredDraft): string {
  if (draft.kind === "gantt") {
    const lines = ["gantt"];
    if (draft.title.trim()) lines.push(`  title ${draft.title.trim()}`);
    lines.push(`  dateFormat ${draft.dateFormat.trim() || "YYYY-MM-DD"}`);
    if (draft.axisFormat.trim()) lines.push(`  axisFormat ${draft.axisFormat.trim()}`);
    let currentSection = "";
    for (const task of draft.tasks) {
      const section = task.section.trim() || "Plan";
      if (section !== currentSection) {
        lines.push(`  section ${section}`);
        currentSection = section;
      }
      const fields = [task.id.trim() || `task-${draft.tasks.indexOf(task) + 1}`];
      if (task.milestone) fields.push("milestone");
      fields.push(
        task.dependency?.trim() ? `after ${task.dependency.trim()}` : task.start.trim(),
        task.duration.trim() || "1d",
      );
      lines.push(`  ${task.name.trim() || "Untitled task"} :${fields.join(", ")}`);
    }
    return lines.join("\n");
  }
  const lines = ["classDiagram"];
  for (const definition of draft.classes) {
    lines.push(`  class ${definition.name.trim() || "Class"} {`);
    for (const member of definition.members) {
      if (member.trim()) lines.push(`    ${member.trim()}`);
    }
    lines.push("  }");
  }
  for (const relationship of draft.relationships) {
    if (!relationship.left.trim() || !relationship.right.trim()) continue;
    const label = relationship.label.trim() ? ` : ${relationship.label.trim()}` : "";
    lines.push(
      `  ${relationship.left.trim()} ${relationship.operator.trim() || "-->"} ${relationship.right.trim()}${label}`,
    );
  }
  return lines.join("\n");
}

function useStableId(prefix: string): string {
  const id = useId();
  return `${prefix}-${id.replace(/:/g, "")}`;
}

// FIX: Properly watches for dark mode changes on documentElement instead of
// reading it once at render time (which breaks when user switches theme).
function useMermaidTheme(): "dark" | "default" {
  const [theme, setTheme] = useState<"dark" | "default">(() => {
    if (typeof document === "undefined") return "default";
    return document.documentElement.classList.contains("dark") ? "dark" : "default";
  });

  useEffect(() => {
    if (typeof document === "undefined") return;

    const observer = new MutationObserver(() => {
      const isDark = document.documentElement.classList.contains("dark");
      setTheme(isDark ? "dark" : "default");
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => observer.disconnect();
  }, []);

  return theme;
}

export default function DiagramBlock({
  block,
  isStreaming = false,
  fillHeight = false,
  onChange,
  onSaveArtifact,
}: DiagramBlockProps) {
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [savingArtifact, setSavingArtifact] = useState(false);
  const [editingSyntax, setEditingSyntax] = useState(false);
  const [editingStructured, setEditingStructured] = useState(false);
  const [canvasOpen, setCanvasOpen] = useState(false);
  const [structuredDraft, setStructuredDraft] = useState<StructuredDraft | null>(null);
  const [draftSyntax, setDraftSyntax] = useState(block.syntax);
  const elementId = useStableId("diagram");
  const mermaidTheme = useMermaidTheme();
  const isMermaid = block.source === "mermaid";
  const activeSyntax = editingSyntax ? draftSyntax : block.syntax;
  const sanitizedSyntax = useMemo(
    () => (isMermaid ? sanitizeMermaidSyntax(activeSyntax) : activeSyntax),
    [activeSyntax, isMermaid],
  );
  const mountedRef = useRef(true);

  const persistChange = async (next: StreamDiagramBlock): Promise<boolean> => {
    if (!onChange) return true;
    setActionError(null);
    setActionStatus(null);
    try {
      const saved = await onChange(next);
      if (saved === false) {
        throw new Error(
          "This diagram changed in another session. Your edits are still open; retry after reviewing the latest version.",
        );
      }
      return true;
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "The diagram changes could not be saved.",
      );
      return false;
    }
  };

  const saveArtifact = async (artifact: StreamDiagramBlock) => {
    if (!onSaveArtifact || savingArtifact) return;
    setSavingArtifact(true);
    setActionError(null);
    setActionStatus(null);
    try {
      await onSaveArtifact(artifact);
      setActionStatus("Saved to Library.");
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "The diagram could not be saved to Library.",
      );
    } finally {
      setSavingArtifact(false);
    }
  };

  useEffect(() => {
    queueMicrotask(() => {
      setDraftSyntax(block.syntax);
      setEditingSyntax(false);
    });
  }, [block.id, block.syntax]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!isMermaid) {
      queueMicrotask(() => {
        setSvg(null);
        setError(null);
        setIsRendering(false);
      });
      return;
    }
    if (!isExpanded || block.incomplete || !sanitizedSyntax.trim()) {
      queueMicrotask(() => setIsRendering(false));
      return;
    }

    let cancelled = false;

    async function renderDiagram() {
      if (!cancelled && mountedRef.current) {
        setIsRendering(true);
      }
      try {
        const mermaidModule = await import("mermaid");
        const mermaid = mermaidModule.default;
        const isDark = mermaidTheme === "dark";

        (mermaid.initialize as (config: Record<string, unknown>) => void)({
          startOnLoad: false,
          securityLevel: "strict",
          suppressErrorRendering: true,
          theme: mermaidTheme,
          fontFamily: "inherit",
          flowchart: { useMaxWidth: false, htmlLabels: true },
          sequence: { useMaxWidth: false },
          gantt: { useMaxWidth: false },
          themeVariables: {
            fontSize: "14px",
            primaryColor: isDark ? "#1e293b" : "#f1f5f9",
            primaryTextColor: isDark ? "#f8fafc" : "#0f172a",
            primaryBorderColor: isDark ? "#334155" : "#cbd5e1",
            lineColor: isDark ? "#64748b" : "#94a3b8",
            secondaryColor: isDark ? "#0f172a" : "#ffffff",
            nodeTextColor: isDark ? "#ffffff" : "#000000",
            mainBkg: isDark ? "#0f172a" : "#ffffff",
          },
        });

        try {
          const parsed = await mermaid.parse(sanitizedSyntax, { suppressErrors: true });
          if (!parsed) {
            if (!cancelled && mountedRef.current) {
              setError("Invalid Mermaid syntax.");
              setIsRendering(false);
            }
            return;
          }
        } catch (parseError) {
          if (!cancelled && mountedRef.current) {
            const message =
              parseError instanceof Error ? parseError.message : "Invalid Mermaid syntax.";
            setError(message);
            setIsRendering(false);
          }
          return;
        }

        const rendered = await mermaid.render(elementId, sanitizedSyntax);

        if (isMermaidErrorSvg(rendered.svg)) {
          if (!cancelled && mountedRef.current) {
            setSvg(null);
            setError("Mermaid could not render this diagram. Showing the source instead.");
            setIsRendering(false);
          }
          return;
        }

        if (!cancelled && mountedRef.current) {
          setSvg(rendered.svg);
          setError(null);
          setIsRendering(false);
        }
      } catch (renderError) {
        if (!cancelled && mountedRef.current) {
          const message =
            renderError instanceof Error ? renderError.message : "Failed to render diagram.";
          setError(message);
          setIsRendering(false);
        }
      }
    }

    queueMicrotask(() => setError(null));
    const renderTimer = window.setTimeout(() => void renderDiagram(), 0);
    return () => {
      cancelled = true;
      window.clearTimeout(renderTimer);
    };
  }, [block.incomplete, elementId, isExpanded, isMermaid, mermaidTheme, sanitizedSyntax]);

  // FIX: Fullscreen uses a portal into document.body so it can never be
  // clipped by a parent with overflow:hidden or CSS transform.
  const expandedOverlay =
    isExpanded && typeof document !== "undefined"
      ? createPortal(
          <div className="fixed inset-0 z-[9999] flex flex-col bg-slate-950/95 backdrop-blur-xl">
            <div className="flex shrink-0 items-center justify-end px-6 py-4">
              <button
                onClick={() => setIsExpanded(false)}
                className="visual-block-action--active flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold shadow-xl backdrop-blur transition-all hover:scale-105"
              >
                <Minimize2 size={16} />
                Exit Fullscreen
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-8">
              {!isMermaid && block.graph ? (
                <div className="mx-auto max-w-6xl">
                  <GraphBlock block={{ ...block, graph: block.graph }} onChange={onChange} />
                </div>
              ) : isRendering ? (
                <div className="mx-auto max-w-4xl rounded-[1.5rem] border border-white/10 bg-white/5 p-6 text-sm text-white/70">
                  Rendering diagram view...
                </div>
              ) : svg ? (
                <div
                  className="[&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-none"
                  dangerouslySetInnerHTML={{ __html: svg }}
                />
              ) : error ? (
                <div className="mx-auto max-w-4xl rounded-[1.5rem] border border-amber-300/20 bg-amber-500/10 p-6 text-sm text-amber-100/85">
                  {error}
                </div>
              ) : (
                <div className="mx-auto max-w-4xl rounded-[1.5rem] border border-white/10 bg-white/5 p-6 text-sm text-white/70">
                  Diagram render is not ready yet.
                </div>
              )}
            </div>
          </div>,
          document.body,
        )
      : null;

  const handleCopy = async () => {
    const source =
      block.source === "graph_json" && block.graph
        ? JSON.stringify(block.graph, null, 2)
        : sanitizedSyntax;
    if (!source.trim()) {
      return;
    }
    try {
      await navigator.clipboard.writeText(source);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
      setActionError(null);
    } catch (caught) {
      setCopied(false);
      setActionError(
        caught instanceof Error ? caught.message : "The diagram source could not be copied.",
      );
    }
  };

  const commitSyntax = async () => {
    if (editingSyntax) {
      const saved = await persistChange({
        ...block,
        syntax: draftSyntax,
        revision: (block.revision ?? 0) + 1,
      });
      if (!saved) return;
    } else {
      setActionError(null);
      setActionStatus(null);
    }
    setEditingSyntax(!editingSyntax);
  };

  const openStructuredEditor = () => {
    const parsed = parseStructuredDraft(block.diagram_type, draftSyntax || block.syntax);
    if (!parsed) return;
    setStructuredDraft(parsed);
    setActionError(null);
    setActionStatus(null);
    setEditingStructured(true);
    setEditingSyntax(false);
  };

  const commitStructured = async () => {
    if (!structuredDraft) return;
    const syntax = generateStructuredSyntax(structuredDraft);
    const saved = await persistChange({ ...block, syntax, revision: (block.revision ?? 0) + 1 });
    if (!saved) return;
    setDraftSyntax(syntax);
    setEditingStructured(false);
  };

  if (isMermaid) {
    return (
      <section
        className={`theme-panel rounded-[1.6rem] p-4 ${fillHeight ? "flex h-full min-h-0 flex-1 flex-col" : ""}`}
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <span className="text-foreground/65 text-xs font-semibold tracking-[0.14em] uppercase">
            {formatDiagramLabel(block.diagram_type)} editor
          </span>
          <div className="flex items-center gap-2">
            {(block.diagram_type === "mermaid_gantt" || block.diagram_type === "mermaid_class") && (
              <button
                type="button"
                onClick={() => {
                  setActionError(null);
                  setActionStatus(null);
                  if (!canvasOpen && !structuredDraft) {
                    setStructuredDraft(
                      parseStructuredDraft(block.diagram_type, draftSyntax || block.syntax),
                    );
                  }
                  setCanvasOpen((open) => !open);
                }}
                className={`visual-block-action inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] ${canvasOpen ? "visual-block-action--active" : ""}`}
              >
                <GitBranch size={13} /> {canvasOpen ? "Close canvas" : "Canvas"}
              </button>
            )}
            {onSaveArtifact ? (
              <button
                type="button"
                onClick={() => void saveArtifact({ ...block, syntax: draftSyntax })}
                disabled={savingArtifact}
                aria-busy={savingArtifact}
                className="visual-block-action inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] disabled:opacity-50"
              >
                {savingArtifact ? "Saving…" : actionStatus ? "Saved" : "Save artifact"}
              </button>
            ) : null}
            {(block.diagram_type === "mermaid_gantt" || block.diagram_type === "mermaid_class") && (
              <button
                type="button"
                onClick={editingStructured ? commitStructured : openStructuredEditor}
                className={`visual-block-action inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] ${editingStructured ? "visual-block-action--active" : ""}`}
              >
                {editingStructured ? <Save size={13} /> : <GitBranch size={13} />}{" "}
                {editingStructured ? "Save structured" : "Edit structured"}
              </button>
            )}
            <button
              type="button"
              onClick={commitSyntax}
              className={`visual-block-action inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] ${editingSyntax ? "visual-block-action--active" : ""}`}
            >
              {editingSyntax ? <Save size={13} /> : <Pencil size={13} />}{" "}
              {editingSyntax ? "Preview" : "Edit source"}
            </button>
          </div>
        </div>
        {actionError ? (
          <p className="mb-3 text-xs text-rose-600 dark:text-rose-300" role="alert">
            {actionError}
          </p>
        ) : null}
        {actionStatus ? (
          <p
            className="mb-3 text-xs text-emerald-700 dark:text-emerald-300"
            role="status"
            aria-live="polite"
          >
            {actionStatus}
          </p>
        ) : null}
        {canvasOpen && structuredDraft ? (
          <NativeDiagramCanvas
            draft={structuredDraft}
            visualModel={block.visual_model}
            onChange={(nextDraft, visualModel) => {
              const syntax = generateStructuredSyntax(nextDraft);
              setStructuredDraft(nextDraft);
              setDraftSyntax(syntax);
              void persistChange({
                ...block,
                syntax,
                visual_model: visualModel,
                revision: (block.revision ?? 0) + 1,
              });
            }}
          />
        ) : null}
        {editingStructured && structuredDraft ? (
          <StructuredDiagramEditor draft={structuredDraft} onChange={setStructuredDraft} />
        ) : editingSyntax ? (
          <textarea
            value={draftSyntax}
            onChange={(event) => setDraftSyntax(event.target.value)}
            aria-label="Edit diagram source"
            className="border-glass-border bg-background/60 text-foreground mb-3 min-h-32 w-full rounded-xl border p-3 font-mono text-xs leading-6 outline-none"
          />
        ) : null}
        <CodeBlock
          language="mermaid"
          value={sanitizedSyntax}
          incomplete={Boolean(block.incomplete || isStreaming)}
          enableRichPreview={true}
          answerStreaming={false}
          defaultPreviewOpen={true}
          title={block.title}
          description={block.description}
        />
      </section>
    );
  }

  return (
    <section className="theme-panel w-full min-w-0 rounded-[1.8rem] px-5 py-5 shadow-[0_24px_70px_-44px_rgba(8,47,73,0.18)] sm:px-6 dark:shadow-[0_24px_70px_-44px_rgba(8,47,73,0.95)]">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="theme-accent-pill inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-semibold tracking-[0.18em] uppercase">
          <GitBranch size={12} />
          {formatDiagramLabel(block.diagram_type)}
        </div>
        {block.title ? (
          <h4 className="text-foreground text-[15px] font-semibold tracking-[-0.015em]">
            {block.title}
          </h4>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          {onSaveArtifact ? (
            <button
              type="button"
              onClick={() => void saveArtifact(block)}
              disabled={savingArtifact}
              aria-busy={savingArtifact}
              className="visual-block-action rounded-lg px-3 py-1 text-[11px] font-semibold disabled:opacity-50"
            >
              {savingArtifact ? "Saving…" : actionStatus ? "Saved" : "Save artifact"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={handleCopy}
            className="visual-block-action rounded-lg px-3 py-1 text-[11px] font-semibold tracking-[0.14em] uppercase"
          >
            {copied ? "Copied" : "Copy"}
          </button>
          {actionError ? (
            <p className="basis-full text-xs text-rose-600 dark:text-rose-300" role="alert">
              {actionError}
            </p>
          ) : null}
          {actionStatus ? (
            <p
              className="basis-full text-xs text-emerald-700 dark:text-emerald-300"
              role="status"
              aria-live="polite"
            >
              {actionStatus}
            </p>
          ) : null}
          <button
            type="button"
            onClick={() => setIsExpanded(true)}
            disabled={Boolean(block.incomplete || (!block.syntax.trim() && !block.graph))}
            className="visual-block-action inline-flex items-center gap-2 rounded-lg px-3 py-1 text-[11px] font-semibold tracking-[0.14em] uppercase disabled:cursor-not-allowed disabled:opacity-40"
            title="View diagram"
          >
            <Eye size={12} />
            View
          </button>
        </div>
      </div>

      {block.description ? (
        <p className="text-foreground/72 mb-4 text-[14px] leading-7">{block.description}</p>
      ) : null}

      {expandedOverlay}
      <div className="theme-code-surface text-foreground/72 rounded-[1.45rem] p-4 text-sm">
        <div className="theme-chip text-primary mb-3 inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] tracking-[0.18em] uppercase">
          <Sparkles size={12} />
          {block.incomplete
            ? "Streaming diagram..."
            : block.syntax.trim() || block.graph
              ? "Diagram block ready"
              : "Preparing diagram..."}
        </div>
        {block.incomplete ? (
          <pre className="text-primary/80 overflow-x-auto text-xs leading-6 break-words whitespace-pre-wrap transition-opacity duration-500">
            {block.syntax}
          </pre>
        ) : block.source === "graph_json" && block.graph ? (
          <div className="space-y-3">
            <GraphBlock block={{ ...block, graph: block.graph }} onChange={onChange} />
            <div className="text-foreground/60 text-xs leading-6">
              Graph structure is ready. Use <span className="font-semibold text-current">View</span>{" "}
              to open the visual graph.
            </div>
          </div>
        ) : block.syntax.trim() ? (
          <>
            <pre className="text-primary/80 overflow-x-auto text-xs leading-6 break-words whitespace-pre-wrap">
              {block.syntax}
            </pre>
            <div className="text-foreground/60 mt-3 text-xs leading-6">
              Diagram syntax is complete. Use{" "}
              <span className="font-semibold text-current">View</span> to open the rendered visual.
            </div>
          </>
        ) : (
          <div className="text-foreground/60 text-xs leading-6">Preparing diagram block...</div>
        )}
        {error && !isExpanded ? (
          <p className="mt-3 text-xs text-amber-700 dark:text-amber-200/85">{error}</p>
        ) : null}
      </div>
    </section>
  );
}

function NativeDiagramCanvas({
  draft,
  visualModel,
  onChange,
}: {
  draft: StructuredDraft;
  visualModel?: Record<string, unknown>;
  onChange: (draft: StructuredDraft, model: Record<string, unknown>) => void;
}) {
  const storedNodes =
    visualModel && typeof visualModel.nodes === "object" && visualModel.nodes
      ? (visualModel.nodes as Record<
          string,
          { x?: number; y?: number; width?: number; height?: number; group_id?: string }
        >)
      : {};
  const [positions, setPositions] = useState<
    Record<string, { x: number; y: number; width: number; height: number; group_id?: string }>
  >(() => {
    const next: Record<
      string,
      { x: number; y: number; width: number; height: number; group_id?: string }
    > = {};
    if (draft.kind === "class") {
      draft.classes.forEach((item, index) => {
        const stored = storedNodes[item.name];
        next[item.name] = {
          x: stored?.x ?? 24 + (index % 3) * 180,
          y: stored?.y ?? 24 + Math.floor(index / 3) * 110,
          width: stored?.width ?? 124,
          height: stored?.height ?? 50,
          group_id: stored?.group_id,
        };
      });
    } else {
      draft.tasks.forEach((item, index) => {
        const stored = storedNodes[item.id];
        next[item.id] = {
          x: stored?.x ?? 24,
          y: stored?.y ?? 24 + index * 54,
          width: stored?.width ?? 160,
          height: stored?.height ?? 32,
          group_id: stored?.group_id,
        };
      });
    }
    return next;
  });
  const [dragging, setDragging] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const dragOrigin = useRef<{
    x: number;
    y: number;
    px: number;
    py: number;
    width?: number;
    height?: number;
  } | null>(null);
  const [resizingId, setResizingId] = useState<string | null>(null);
  const ganttResizeBase = useRef<{ width: number; duration: string } | null>(null);
  const nodes =
    draft.kind === "class"
      ? draft.classes.map((item) => ({ id: item.name, label: item.name }))
      : draft.tasks.map((item) => ({ id: item.id, label: item.name }));
  const persist = (
    nextPositions: Record<
      string,
      { x: number; y: number; width: number; height: number; group_id?: string }
    >,
    nextDraft = draft,
  ) => {
    onChange(nextDraft, {
      kind: nextDraft.kind,
      nodes: nextPositions,
      groups: Object.entries(nextPositions)
        .filter(([, point]) => point.group_id)
        .map(([id, point]) => ({ id, group_id: point.group_id })),
      updated_at: new Date().toISOString(),
    });
  };
  const alignSelected = (axis: "x" | "y") => {
    if (selectedIds.length < 2) return;
    const baseline = positions[selectedIds[0]!];
    if (!baseline) return;
    const next = Object.fromEntries(
      Object.entries(positions).map(([id, point]) => [
        id,
        selectedIds.includes(id) ? { ...point, [axis]: baseline[axis] } : point,
      ]),
    );
    setPositions(next);
    persist(next);
  };
  const updateGanttTask = (id: string, patch: Partial<GanttTask>) => {
    if (draft.kind !== "gantt") return;
    const nextDraft: StructuredDraft = {
      ...draft,
      tasks: draft.tasks.map((task) => (task.id === id ? { ...task, ...patch } : task)),
    };
    persist(positions, nextDraft);
  };
  return (
    <div
      className="relative mb-3 min-h-[260px] overflow-hidden rounded-2xl border border-white/10 bg-slate-950/30 p-3"
      onPointerMove={(event) => {
        if (!dragging || !dragOrigin.current) return;
        if (resizingId === dragging) {
          const next = {
            ...(positions[dragging] ?? { x: 24, y: 24, width: 124, height: 50 }),
            width: Math.max(
              70,
              Math.min(
                300,
                (dragOrigin.current.width ?? 124) + event.clientX - dragOrigin.current.px,
              ),
            ),
            height: Math.max(
              40,
              Math.min(
                180,
                (dragOrigin.current.height ?? 50) + event.clientY - dragOrigin.current.py,
              ),
            ),
          };
          setPositions((current) => ({ ...current, [dragging]: next }));
          return;
        }
        const next = {
          x: Math.max(8, dragOrigin.current.x + event.clientX - dragOrigin.current.px),
          y: Math.max(8, dragOrigin.current.y + event.clientY - dragOrigin.current.py),
          width: positions[dragging]?.width ?? (draft.kind === "class" ? 124 : 160),
          height: positions[dragging]?.height ?? (draft.kind === "class" ? 50 : 32),
          group_id: positions[dragging]?.group_id,
        };
        setPositions((current) => ({ ...current, [dragging]: next }));
      }}
      onPointerUp={() => {
        if (!dragging) return;
        persist(positions);
        if (resizingId === dragging && draft.kind === "gantt" && ganttResizeBase.current) {
          const nextWidth = positions[dragging]?.width ?? ganttResizeBase.current.width;
          const days = Math.max(1, Math.round(nextWidth / 24));
          updateGanttTask(dragging, { duration: `${days}d` });
        }
        setDragging(null);
        setResizingId(null);
        ganttResizeBase.current = null;
        dragOrigin.current = null;
      }}
      onPointerCancel={() => {
        setDragging(null);
        setResizingId(null);
        ganttResizeBase.current = null;
        dragOrigin.current = null;
      }}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-[10px] font-semibold tracking-[0.16em] text-white/55 uppercase">
        <span>Native {draft.kind === "class" ? "UML" : "Gantt"} canvas · drag to arrange</span>
        {draft.kind === "class" ? (
          <div className="flex items-center gap-1 normal-case">
            <button
              type="button"
              className="theme-chip rounded px-2 py-1 text-[10px]"
              onClick={() => alignSelected("x")}
            >
              Align X
            </button>
            <button
              type="button"
              className="theme-chip rounded px-2 py-1 text-[10px]"
              onClick={() => alignSelected("y")}
            >
              Align Y
            </button>
            <button
              type="button"
              className="theme-chip rounded px-2 py-1 text-[10px]"
              onClick={() => {
                if (!selectedIds.length) return;
                const groupId = `group-${Date.now()}`;
                const next = Object.fromEntries(
                  Object.entries(positions).map(([id, point]) => [
                    id,
                    selectedIds.includes(id) ? { ...point, group_id: groupId } : point,
                  ]),
                );
                setPositions(next);
                persist(next);
              }}
            >
              Group
            </button>
            <button
              type="button"
              className="theme-chip rounded px-2 py-1 text-[10px]"
              onClick={() => {
                const next = Object.fromEntries(
                  Object.entries(positions).map(([id, point]) => [
                    id,
                    selectedIds.includes(id) ? { ...point, group_id: undefined } : point,
                  ]),
                );
                setPositions(next);
                persist(next);
              }}
            >
              Ungroup
            </button>
          </div>
        ) : null}
      </div>
      {draft.kind === "class" ? (
        <svg viewBox="0 0 680 220" className="h-[220px] w-full">
          {draft.relationships.map((relationship) => {
            const left = positions[relationship.left] ?? { x: 24, y: 24 };
            const right = positions[relationship.right] ?? { x: 24, y: 24 };
            return (
              <line
                key={`${relationship.left}-${relationship.right}`}
                x1={left.x + 62}
                y1={left.y + 25}
                x2={right.x + 62}
                y2={right.y + 25}
                stroke="rgba(125,211,252,.55)"
                strokeWidth="2"
              />
            );
          })}
          {nodes.map((node) => {
            const point = positions[node.id] ?? { x: 24, y: 24, width: 124, height: 50 };
            const selected = selectedIds.includes(node.id);
            return (
              <g
                key={node.id}
                transform={`translate(${point.x},${point.y})`}
                onPointerDown={(event) => {
                  event.currentTarget.setPointerCapture(event.pointerId);
                  setSelectedIds((current) =>
                    event.shiftKey
                      ? current.includes(node.id)
                        ? current.filter((id) => id !== node.id)
                        : [...current, node.id]
                      : [node.id],
                  );
                  setDragging(node.id);
                  dragOrigin.current = { ...point, px: event.clientX, py: event.clientY };
                }}
                className="cursor-grab active:cursor-grabbing"
              >
                <rect
                  width={point.width ?? 124}
                  height={point.height ?? 50}
                  rx="10"
                  fill="rgba(14,116,144,.35)"
                  stroke={selected ? "rgba(253,224,71,.95)" : "rgba(103,232,249,.75)"}
                />
                <text
                  x={(point.width ?? 124) / 2}
                  y={(point.height ?? 50) / 2 + 4}
                  textAnchor="middle"
                  fill="white"
                  fontSize="12"
                >
                  {node.label}
                </text>
                <rect
                  x={(point.width ?? 124) - 10}
                  y={(point.height ?? 50) - 10}
                  width="10"
                  height="10"
                  rx="2"
                  fill="rgba(255,255,255,.75)"
                  className="cursor-nwse-resize"
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    event.currentTarget.ownerSVGElement?.setPointerCapture(event.pointerId);
                    setSelectedIds([node.id]);
                    setDragging(node.id);
                    setResizingId(node.id);
                    dragOrigin.current = {
                      ...point,
                      px: event.clientX,
                      py: event.clientY,
                      width: point.width,
                      height: point.height,
                    };
                  }}
                />
              </g>
            );
          })}
        </svg>
      ) : (
        <div className="space-y-2">
          {nodes.map((node) => {
            const point = positions[node.id] ?? { x: 24, y: 24, width: 160, height: 32 };
            const task = draft.tasks.find((item) => item.id === node.id);
            return (
              <div key={node.id} className="rounded-lg bg-white/5 p-1">
                <div
                  className={`relative h-8 rounded-lg border px-3 text-xs leading-8 text-white ${selectedIds.includes(node.id) ? "border-yellow-300/70 bg-yellow-300/15" : "border-cyan-300/45 bg-cyan-300/20"}`}
                  style={{
                    left: `${Math.min(80, point.x)}px`,
                    width: `${Math.max(80, point.width)}px`,
                  }}
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    setSelectedIds([node.id]);
                    setDragging(node.id);
                    dragOrigin.current = { ...point, px: event.clientX, py: event.clientY };
                  }}
                >
                  {node.label}
                  {task && selectedIds.includes(node.id) ? (
                    <span
                      role="separator"
                      aria-label={`Resize ${task.name} duration`}
                      className="absolute top-1 right-0 h-6 w-2 cursor-ew-resize rounded bg-cyan-100/70"
                      onPointerDown={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        setDragging(node.id);
                        setResizingId(node.id);
                        ganttResizeBase.current = { width: point.width, duration: task.duration };
                        dragOrigin.current = {
                          ...point,
                          px: event.clientX,
                          py: event.clientY,
                          width: point.width,
                          height: point.height,
                        };
                      }}
                    />
                  ) : null}
                </div>
                {task && selectedIds.includes(node.id) ? (
                  <div className="mt-1 grid gap-1 px-1 sm:grid-cols-3">
                    <input
                      type="date"
                      value={task.start.startsWith("after ") ? "" : task.start}
                      onChange={(event) =>
                        updateGanttTask(node.id, {
                          start: event.target.value,
                          dependency: undefined,
                        })
                      }
                      aria-label={`${task.name} start date`}
                      className="rounded border border-white/10 bg-black/20 px-1 py-1 text-[10px] text-white"
                    />
                    <input
                      value={task.duration}
                      onChange={(event) =>
                        updateGanttTask(node.id, { duration: event.target.value })
                      }
                      aria-label={`${task.name} duration`}
                      className="rounded border border-white/10 bg-black/20 px-1 py-1 text-[10px] text-white"
                    />
                    <select
                      value={task.dependency ?? ""}
                      onChange={(event) =>
                        updateGanttTask(node.id, { dependency: event.target.value || undefined })
                      }
                      aria-label={`${task.name} dependency`}
                      className="rounded border border-white/10 bg-black/20 px-1 py-1 text-[10px] text-white"
                    >
                      <option value="">No dependency</option>
                      {draft.tasks
                        .filter((candidate) => candidate.id !== task.id)
                        .map((candidate) => (
                          <option key={candidate.id} value={candidate.id}>
                            After {candidate.name}
                          </option>
                        ))}
                    </select>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function StructuredDiagramEditor({
  draft,
  onChange,
}: {
  draft: StructuredDraft;
  onChange: (draft: StructuredDraft) => void;
}) {
  if (draft.kind === "gantt") {
    return (
      <div className="border-glass-border bg-background/50 mb-3 space-y-3 rounded-xl border p-3">
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="text-foreground/65 text-[11px] font-semibold uppercase">
            Title
            <input
              value={draft.title}
              onChange={(event) => onChange({ ...draft, title: event.target.value })}
              className="border-glass-border bg-background/70 text-foreground mt-1 w-full rounded-lg border px-2 py-1.5 text-xs outline-none"
            />
          </label>
          <label className="text-foreground/65 text-[11px] font-semibold uppercase">
            Date format
            <input
              value={draft.dateFormat}
              onChange={(event) => onChange({ ...draft, dateFormat: event.target.value })}
              className="border-glass-border bg-background/70 text-foreground mt-1 w-full rounded-lg border px-2 py-1.5 text-xs outline-none"
            />
          </label>
          <label className="text-foreground/65 text-[11px] font-semibold uppercase">
            Axis format
            <input
              value={draft.axisFormat}
              onChange={(event) => onChange({ ...draft, axisFormat: event.target.value })}
              className="border-glass-border bg-background/70 text-foreground mt-1 w-full rounded-lg border px-2 py-1.5 text-xs outline-none"
            />
          </label>
        </div>
        <div className="space-y-2">
          {draft.tasks.map((task, index) => (
            <div
              key={`${task.id}-${index}`}
              className="grid gap-2 rounded-lg border border-white/10 p-2 sm:grid-cols-[1.5fr_0.8fr_1fr_0.8fr_0.8fr_auto]"
            >
              {(
                [
                  ["name", "Task"],
                  ["section", "Section"],
                  ["start", "Start"],
                  ["duration", "Duration"],
                  ["dependency", "After task"],
                ] as const
              ).map(([field, label]) => (
                <label
                  key={field}
                  className="text-foreground/60 text-[10px] font-semibold uppercase"
                >
                  {label}
                  <input
                    value={task[field] ?? ""}
                    onChange={(event) => {
                      const tasks = draft.tasks.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, [field]: event.target.value } : item,
                      );
                      onChange({ ...draft, tasks });
                    }}
                    className="border-glass-border bg-background/70 text-foreground mt-1 w-full rounded-lg border px-2 py-1.5 text-xs outline-none"
                  />
                </label>
              ))}
              <div className="flex items-end gap-1">
                <button
                  type="button"
                  onClick={() => {
                    const tasks = draft.tasks.map((item, itemIndex) =>
                      itemIndex === index ? { ...item, milestone: !item.milestone } : item,
                    );
                    onChange({ ...draft, tasks });
                  }}
                  className={`theme-chip h-8 rounded-lg px-2 text-[10px] ${task.milestone ? "bg-primary text-primary-foreground" : ""}`}
                  title="Toggle milestone"
                >
                  Milestone
                </button>
                <button
                  type="button"
                  onClick={() =>
                    onChange({
                      ...draft,
                      tasks: draft.tasks.filter((_, itemIndex) => itemIndex !== index),
                    })
                  }
                  className="theme-chip inline-flex h-8 w-8 items-center justify-center rounded-lg text-rose-500"
                  aria-label={`Remove ${task.name || "task"}`}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={() =>
            onChange({
              ...draft,
              tasks: [
                ...draft.tasks,
                {
                  name: "New task",
                  id: `task-${draft.tasks.length + 1}`,
                  start: "2026-01-01",
                  duration: "1d",
                  milestone: false,
                  section: draft.tasks.at(-1)?.section || "Plan",
                  dependency: undefined,
                },
              ],
            })
          }
          className="theme-chip inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs"
        >
          <Plus size={13} /> Add task
        </button>
      </div>
    );
  }

  return (
    <div className="border-glass-border bg-background/50 mb-3 space-y-3 rounded-xl border p-3">
      {draft.classes.map((definition, index) => (
        <div key={`${definition.name}-${index}`} className="rounded-lg border border-white/10 p-2">
          <div className="flex gap-2">
            <input
              value={definition.name}
              onChange={(event) => {
                const classes = draft.classes.map((item, itemIndex) =>
                  itemIndex === index ? { ...item, name: event.target.value } : item,
                );
                onChange({ ...draft, classes });
              }}
              aria-label={`Class ${index + 1} name`}
              className="border-glass-border bg-background/70 text-foreground flex-1 rounded-lg border px-2 py-1.5 text-xs outline-none"
            />
            <button
              type="button"
              onClick={() =>
                onChange({
                  ...draft,
                  classes: draft.classes.filter((_, itemIndex) => itemIndex !== index),
                })
              }
              className="theme-chip inline-flex h-8 w-8 items-center justify-center rounded-lg text-rose-500"
              aria-label={`Remove ${definition.name || "class"}`}
            >
              <Trash2 size={13} />
            </button>
          </div>
          <textarea
            value={definition.members.join("\n")}
            onChange={(event) => {
              const classes = draft.classes.map((item, itemIndex) =>
                itemIndex === index
                  ? { ...item, members: event.target.value.split(/\r?\n/).filter(Boolean) }
                  : item,
              );
              onChange({ ...draft, classes });
            }}
            aria-label={`${definition.name || "Class"} members`}
            placeholder="+id: string\n+save()"
            className="border-glass-border bg-background/70 text-foreground mt-2 min-h-16 w-full rounded-lg border px-2 py-1.5 font-mono text-xs outline-none"
          />
        </div>
      ))}
      <button
        type="button"
        onClick={() =>
          onChange({ ...draft, classes: [...draft.classes, { name: "NewClass", members: [] }] })
        }
        className="theme-chip inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs"
      >
        <Plus size={13} /> Add class
      </button>
      <div className="border-t border-white/10 pt-3">
        <div className="text-foreground/60 mb-2 text-[10px] font-semibold uppercase">
          Relationships
        </div>
        {draft.relationships.map((relationship, index) => (
          <div
            key={`${relationship.left}-${relationship.right}-${index}`}
            className="mb-2 grid gap-2 sm:grid-cols-[1fr_0.7fr_1fr_1fr_auto]"
          >
            {(["left", "operator", "right", "label"] as const).map((field) => (
              <input
                key={field}
                value={relationship[field]}
                onChange={(event) => {
                  const relationships = draft.relationships.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, [field]: event.target.value } : item,
                  );
                  onChange({ ...draft, relationships });
                }}
                aria-label={`Relationship ${field}`}
                placeholder={field}
                className="border-glass-border bg-background/70 text-foreground rounded-lg border px-2 py-1.5 text-xs outline-none"
              />
            ))}
            <button
              type="button"
              onClick={() =>
                onChange({
                  ...draft,
                  relationships: draft.relationships.filter((_, itemIndex) => itemIndex !== index),
                })
              }
              className="theme-chip inline-flex h-8 w-8 items-center justify-center rounded-lg text-rose-500"
              aria-label="Remove relationship"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() =>
            onChange({
              ...draft,
              relationships: [
                ...draft.relationships,
                { left: "ClassA", operator: "-->", right: "ClassB", label: "" },
              ],
            })
          }
          className="theme-chip inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs"
        >
          <Plus size={13} /> Add relationship
        </button>
      </div>
    </div>
  );
}

function formatDiagramLabel(value: DiagramBlockProps["block"]["diagram_type"]) {
  return value.replace("mermaid_", "").replace(/_/g, " ");
}
