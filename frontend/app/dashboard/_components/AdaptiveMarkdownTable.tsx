"use client";

import { Children, isValidElement, type ReactElement, type ReactNode } from "react";

type ElementWithChildren = ReactElement<{ children?: ReactNode }>;

function elementChildren(node: ReactNode): ReactNode[] {
  return isValidElement(node) ? Children.toArray((node as ElementWithChildren).props.children) : [];
}

const MAX_TREE_DEPTH = 32;

function elementsNamed(node: ReactNode, names: ReadonlySet<string>): ElementWithChildren[] {
  // Markdown is untrusted model output. Keep tree walking entirely iterative:
  // a malformed response can have either extreme nesting or a huge number of
  // siblings, and recursive calls/spread arguments can overflow the browser
  // stack even if an individual depth limit exists.
  const matches: ElementWithChildren[] = [];
  const pending = Children.toArray(node)
    .reverse()
    .map((child) => ({ child, depth: 0 }));

  while (pending.length) {
    const current = pending.pop();
    if (!current || current.depth >= MAX_TREE_DEPTH) continue;
    const { child, depth } = current;
    if (!isValidElement(child)) continue;
    const element = child as ElementWithChildren;
    if (typeof element.type === "string" && names.has(element.type)) matches.push(element);
    const children = Children.toArray(element.props.children);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      pending.push({ child: children[index]!, depth: depth + 1 });
    }
  }
  return matches;
}

function visibleText(node: ReactNode): string {
  const fragments: string[] = [];
  const pending = [{ node, depth: 0 }];

  while (pending.length) {
    const current = pending.pop();
    if (!current || current.depth >= MAX_TREE_DEPTH) continue;
    if (typeof current.node === "string" || typeof current.node === "number") {
      fragments.push(String(current.node));
      continue;
    }
    const children = isValidElement(current.node)
      ? elementChildren(current.node)
      : Children.toArray(current.node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      pending.push({ node: children[index]!, depth: current.depth + 1 });
    }
  }

  return fragments.join(" ").replace(/\s+/g, " ").trim();
}

function rowCells(row: ElementWithChildren): ElementWithChildren[] {
  return elementsNamed(row.props.children, new Set(["th", "td"]));
}

/**
 * Keeps valid comparison data as a normal grid, but protects users from a
 * common provider failure: multi-line bullets emitted as sparse table rows.
 * Those rows no longer contain enough information to recover their intended
 * column. Presenting each numbered record as a card preserves every value
 * without pretending the displaced text belongs to an incorrect column.
 */
export default function AdaptiveMarkdownTable({ children }: { children?: ReactNode }) {
  const sections = elementsNamed(children, new Set(["thead", "tbody"]));
  const head = sections.find((section) => section.type === "thead");
  const body = sections.find((section) => section.type === "tbody");
  const headerRow = head ? elementsNamed(head.props.children, new Set(["tr"]))[0] : undefined;
  const headers = headerRow ? rowCells(headerRow) : [];
  const rows = body ? elementsNamed(body.props.children, new Set(["tr"])) : [];
  const parsedRows = rows.map((row) => ({
    cells: rowCells(row),
    text: rowCells(row).map((cell) => visibleText(cell.props.children)),
  }));
  const primaryIndexes = parsedRows.flatMap((row, index) =>
    /^\d{1,3}$/.test(row.text[0] ?? "") ? [index] : [],
  );
  const hasSparseContinuations = parsedRows.some((row, index) => {
    if (primaryIndexes.includes(index)) return false;
    const populated = row.text.filter(Boolean).length;
    return populated > 0 && populated <= Math.max(2, Math.ceil(headers.length / 2));
  });

  if (headers.length >= 3 && primaryIndexes.length > 0 && hasSparseContinuations) {
    const records = primaryIndexes.map((start, recordIndex) => {
      const end = primaryIndexes[recordIndex + 1] ?? parsedRows.length;
      return { primary: parsedRows[start]!, continuations: parsedRows.slice(start + 1, end) };
    });
    return (
      <div className="my-5 grid gap-4" data-adaptive-table="cards">
        {records.map(({ primary, continuations }, recordIndex) => {
          const title = primary.text[1] || `Result ${primary.text[0] || recordIndex + 1}`;
          const details = continuations.flatMap((row) =>
            row.cells.filter((cell) => visibleText(cell.props.children)),
          );
          return (
            <section
              key={`${primary.text[0] || recordIndex}-${title}`}
              className="rounded-xl border border-white/10 bg-white/[0.025] p-4 shadow-sm"
            >
              <div className="mb-3 flex items-start gap-3">
                <span className="mt-0.5 min-w-6 font-mono text-xs text-cyan-300">
                  {primary.text[0] || String(recordIndex + 1).padStart(2, "0")}
                </span>
                <h4 className="m-0 text-base font-semibold text-cyan-50">
                  {primary.cells[1]?.props.children ?? title}
                </h4>
              </div>
              <dl className="grid gap-3 sm:grid-cols-2">
                {primary.cells.slice(2).map((cell, cellIndex) => {
                  if (!visibleText(cell.props.children)) return null;
                  const label =
                    visibleText(headers[cellIndex + 2]?.props.children) ||
                    `Detail ${cellIndex + 1}`;
                  return (
                    <div key={`${label}-${cellIndex}`} className="min-w-0">
                      <dt className="mb-1 text-[10px] font-semibold tracking-wider text-cyan-300/70 uppercase">
                        {label}
                      </dt>
                      <dd className="text-foreground/85 m-0 text-sm leading-6 break-words">
                        {cell.props.children}
                      </dd>
                    </div>
                  );
                })}
              </dl>
              {details.length ? (
                <div className="mt-4 border-t border-white/8 pt-3">
                  <div className="mb-2 text-[10px] font-semibold tracking-wider text-cyan-300/70 uppercase">
                    Additional details
                  </div>
                  <ul className="m-0 grid gap-2 pl-5 text-sm leading-6 marker:text-cyan-300 sm:grid-cols-2">
                    {details.map((cell, index) => (
                      <li key={index}>{cell.props.children}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          );
        })}
      </div>
    );
  }

  return (
    <div
      className="my-5 overflow-x-auto rounded-xl border border-white/10"
      data-adaptive-table="grid"
    >
      <table className="w-full min-w-[36rem] border-collapse text-left">{children}</table>
    </div>
  );
}
