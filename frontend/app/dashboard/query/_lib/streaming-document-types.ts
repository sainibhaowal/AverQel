export type StreamingDocumentNode =
  | StreamingHeadingNode
  | StreamingParagraphNode
  | StreamingBlockquoteNode
  | StreamingImageNode
  | StreamingFootnoteNode
  | StreamingListNode
  | StreamingTableNode
  | StreamingCodeNode
  | StreamingChartNode
  | StreamingMathNode
  | StreamingRuleNode;

export interface StreamingHeadingNode {
  type: "heading";
  /** 1–6 only. Parser matches #{1,6}; deeper headings are treated as paragraphs. */
  depth: 1 | 2 | 3 | 4 | 5 | 6;
  content: string;
}

export interface StreamingParagraphNode {
  type: "paragraph";
  content: string;
}

export interface StreamingBlockquoteNode {
  type: "blockquote";
  content: string;
}

export interface StreamingImageNode {
  type: "image";
  src: string;
  alt?: string;
  title?: string;
}

export interface StreamingFootnoteNode {
  type: "footnote";
  identifier: string;
  content: string;
}

export interface StreamingListNode {
  type: "list";
  ordered: boolean;
  /**
   * Flat array of item objects. Indented sub-items are concatenated onto
   * their parent item with a space or nested list nodes are attached to the
   * parent item via `children`.
   */
  items: StreamingListItem[];
}

export interface StreamingListItem {
  content: string;
  task?: boolean;
  checked?: boolean;
  children?: StreamingListNode[];
}

export interface StreamingTableNode {
  type: "table";
  /** Optional title row detected above the header (e.g. "Table 1: …"). */
  title?: string;
  headers: string[];
  rows: string[][];
  /**
   * True while the table is still being streamed and the separator row
   * (| --- | --- |) has not yet arrived to lock the column count.
   * Renderers should show shimmer placeholder rows when this is true.
   */
  incomplete?: boolean;
}

export interface StreamingCodeNode {
  type: "code";
  /** Lowercased language identifier from the opening fence, e.g. "python". */
  language?: string;
  value: string;
  /**
   * True when the closing ``` has not yet arrived (fence is still open
   * during streaming). Renderers may show a blinking cursor or suppress
   * syntax highlighting until this is false.
   */
  incomplete?: boolean;
}

export interface StreamingRuleNode {
  type: "rule";
}

/**
 * A chart block detected inline in the token stream — the chart fence appeared
 * at this position in the document, so the HUD renders exactly here, matching
 * the same positional semantics as Mermaid's StreamingCodeNode.
 *
 * `incomplete: true` while the closing ``` has not yet arrived.  Renderers
 * should show a loading skeleton until this flips to false/undefined.
 */
export interface StreamingChartNode {
  type: "chart";
  title?: string;
  chart_type: "line" | "bar" | "pie" | "area" | "scatter";
  series: Array<{
    label: string;
    value: number;
    z?: number;
    [key: string]: string | number | null | undefined;
  }>;
  raw_payload?: string;
  parser_source?: "json" | "pattern" | "structured";
  confidence?: number;
  fields?: string[];
  x_key?: string;
  y_key?: string;
  z_key?: string;
  /** True while the closing ``` has not yet arrived (fence still streaming). */
  incomplete?: boolean;
}

/**
 * A math block detected in the stream ($$ ... $$).
 */
export interface StreamingMathNode {
  type: "math";
  value: string;
  /** True while the closing $$ has not yet arrived. */
  incomplete?: boolean;
}
