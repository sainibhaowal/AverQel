"use client";

import { createReactBlockSpec } from "@blocknote/react";
import { BarChart3, CreditCard, GitBranch, Pencil, Save, Sparkles, X } from "lucide-react";
import { useState } from "react";

import DeepSpaceMarkdownRenderer from "./DeepSpaceMarkdownRenderer";

export type RichContentKind = "chart" | "card" | "mermaid" | "graph" | "gallery" | "infographic";

type RichContentBlockProps = {
  block: { id: string; props: { kind: RichContentKind; source: string } };
  editor: { updateBlock: (block: unknown, update: unknown) => void };
};

function RichContentBlockView({ block, editor }: RichContentBlockProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(block.props.source);
  const fence = `${String.fromCharCode(96).repeat(3)}${block.props.kind}\n${draft}\n${String.fromCharCode(96).repeat(3)}`;
  const save = () => {
    editor.updateBlock(block, { props: { ...block.props, source: draft } });
    setEditing(false);
  };
  return (
    <div className="group relative my-4 w-full" data-rich-content-kind={block.props.kind}>
      {editing ? (
        <div className="border-primary/30 bg-background/50 rounded-2xl border p-3">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="border-glass-border bg-background/70 text-foreground min-h-36 w-full rounded-xl border p-3 font-mono text-xs leading-6 outline-none"
            aria-label={`Edit ${block.props.kind} JSON or source`}
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setDraft(block.props.source);
                setEditing(false);
              }}
              className="theme-chip inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs"
            >
              <X size={13} /> Cancel
            </button>
            <button
              type="button"
              onClick={save}
              className="theme-chip bg-primary text-primary-foreground inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs"
            >
              <Save size={13} /> Save block
            </button>
          </div>
        </div>
      ) : (
        <DeepSpaceMarkdownRenderer content={fence} />
      )}
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="theme-chip absolute top-2 right-2 z-10 inline-flex items-center gap-1 rounded-full px-2.5 py-1.5 text-[11px] opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100"
        aria-label={`Edit ${block.props.kind} block`}
      >
        <Pencil size={13} /> Edit
      </button>
    </div>
  );
}

export const RichContentBlock = createReactBlockSpec(
  {
    type: "rich_content",
    propSchema: {
      kind: { default: "chart" as RichContentKind },
      source: { default: "{}" },
    },
    content: "none",
  },
  {
    render: (props) => <RichContentBlockView {...(props as RichContentBlockProps)} />,
    toExternalHTML: ({ block }) => {
      const fence = `${String.fromCharCode(96).repeat(3)}${block.props.kind}\n${block.props.source}\n${String.fromCharCode(96).repeat(3)}`;
      return (
        <pre
          data-rich-content-kind={block.props.kind}
          data-rich-content-source={block.props.source}
        >
          <code>{fence}</code>
        </pre>
      );
    },
    parse: (element) => {
      const kind = element.dataset.richContentKind;
      const source = element.dataset.richContentSource;
      if (
        (kind !== "chart" &&
          kind !== "card" &&
          kind !== "mermaid" &&
          kind !== "graph" &&
          kind !== "gallery" &&
          kind !== "infographic") ||
        !source
      )
        return undefined;
      return { kind, source };
    },
  },
);

export const RICH_CONTENT_SLASH_ITEMS = [
  {
    title: "Chart block",
    aliases: ["chart", "graph", "plot"],
    group: "Rich content",
    icon: <BarChart3 size={16} />,
    hint: "Insert an editable line, bar, area, scatter, or pie chart",
    kind: "chart" as const,
    source: JSON.stringify({
      title: "New chart",
      chart_type: "line",
      series: [
        { label: "A", value: 10 },
        { label: "B", value: 20 },
      ],
    }),
  },
  {
    title: "Information card",
    aliases: ["card", "info", "callout"],
    group: "Rich content",
    icon: <CreditCard size={16} />,
    hint: "Insert a rich information card with metrics and actions",
    kind: "card" as const,
    source: JSON.stringify({
      title: "New information card",
      content: "Add a finding or decision here.",
      tone: "info",
    }),
  },
  {
    title: "Diagram block",
    aliases: ["diagram", "mermaid", "flow"],
    group: "Rich content",
    icon: <GitBranch size={16} />,
    hint: "Insert a Mermaid flow, UML, architecture, or Gantt diagram",
    kind: "mermaid" as const,
    source: "flowchart LR\n  A[Start] --> B[Next step]",
  },
  {
    title: "Graph canvas",
    aliases: ["graph", "canvas", "nodes", "excalidraw"],
    group: "Rich content",
    icon: <GitBranch size={16} />,
    hint: "Insert a movable node and connector canvas",
    kind: "graph" as const,
    source: JSON.stringify({
      title: "New graph",
      layout: "horizontal",
      nodes: [
        { id: "start", label: "Start", category: "step", x: 160, y: 180 },
        { id: "next", label: "Next", category: "step", x: 520, y: 180 },
      ],
      edges: [{ source: "start", target: "next", label: "connect" }],
    }),
  },
  {
    title: "Infographic",
    aliases: ["infographic", "process", "timeline", "comparison", "features"],
    group: "Rich content",
    icon: <Sparkles size={16} />,
    hint: "Insert an editable process, timeline, comparison, feature grid, or stats visual",
    kind: "infographic" as const,
    source: JSON.stringify({
      title: "New infographic",
      layout: "steps",
      items: [{ title: "First step" }, { title: "Next step" }],
    }),
  },
  {
    title: "Photo gallery",
    aliases: ["gallery", "photos", "slides", "images"],
    group: "Rich content",
    icon: <CreditCard size={16} />,
    hint: "Insert a clickable, downloadable image sequence",
    kind: "gallery" as const,
    source: JSON.stringify({
      title: "New gallery",
      items: [
        {
          src: "https://images.unsplash.com/photo-1519608487953-e999c86e7455",
          alt: "Preview image",
          caption: "Add a caption",
        },
      ],
    }),
  },
];
