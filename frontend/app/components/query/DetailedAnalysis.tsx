"use client";

import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlignLeft } from "lucide-react";
import InlineCitation from "./InlineCitation";

interface Citation {
  document_id: string;
  filename?: string;
  page_number?: number;
}

interface DetailedAnalysisProps {
  content: string;
  citations?: Citation[];
  onCitationClick?: (citation: Citation) => void;
}

export default function DetailedAnalysis({
  content,
  citations,
  onCitationClick,
}: DetailedAnalysisProps) {
  if (!content || typeof content !== "string") return null;

  // Pre-process [N] into markdown links targeting citations
  const contentWithLinks = content.replace(/\[(\d+)\]/g, "[$1](#citation-$1)");

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="mb-6"
    >
      <div className="text-foreground/70 mb-3 flex items-center gap-2 text-xs font-semibold tracking-wide">
        <AlignLeft size={16} />
        <h3 className="uppercase">Detailed Analysis</h3>
      </div>
      <div className="prose dark:prose-invert selection:bg-primary/30 mx-auto max-w-4xl text-[15px] leading-[1.8]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            pre: ({ children, ...props }) => (
              <pre
                className="theme-code-surface my-4 overflow-x-auto rounded-2xl px-0 py-0"
                {...props}
              >
                {children}
              </pre>
            ),
            h1: ({ ...props }) => (
              <h1
                className="text-foreground mt-10 mb-6 text-3xl font-extrabold tracking-[-0.05em]"
                {...props}
              />
            ),
            h2: ({ ...props }) => (
              <h2
                className="text-foreground mt-9 mb-5 text-2xl font-bold tracking-[-0.04em]"
                {...props}
              />
            ),
            table: ({ ...props }) => (
              <div className="border-glass-border/30 bg-glass-bg/20 my-8 overflow-x-auto rounded-xl border shadow-sm">
                <table className="w-full border-collapse text-left" {...props} />
              </div>
            ),
            thead: ({ ...props }) => (
              <thead
                className="border-glass-border/30 bg-primary/5 text-primary border-b text-[11px] font-bold tracking-widest uppercase"
                {...props}
              />
            ),
            th: ({ ...props }) => <th className="px-5 py-3.5" {...props} />,
            td: ({ ...props }) => (
              <td
                className="border-glass-border/10 text-foreground/80 border-b px-5 py-3.5 text-sm font-light"
                {...props}
              />
            ),
            h3: ({ ...props }) => (
              <h3
                className="text-foreground border-glass-border/30 mt-12 mb-6 flex items-center gap-3 border-b pb-3 text-xl font-extrabold tracking-tight"
                {...props}
              >
                <span className="bg-primary/50 h-6 w-1.5 rounded-full" />
                {props.children}
              </h3>
            ),
            h4: ({ ...props }) => (
              <h4
                className="text-primary mt-8 mb-4 flex items-center gap-2 text-sm font-bold tracking-widest uppercase"
                {...props}
              >
                <span className="bg-primary h-1 w-1 rounded-full" />
                {props.children}
              </h4>
            ),
            h5: ({ ...props }) => (
              <h5
                className="text-foreground mt-6 mb-3 text-[0.95rem] font-semibold tracking-[0.03em] uppercase"
                {...props}
              />
            ),
            h6: ({ ...props }) => (
              <h6
                className="text-foreground/82 mt-5 mb-2 text-[0.9rem] font-semibold tracking-tight"
                {...props}
              />
            ),
            p: ({ ...props }) => (
              <p className="text-foreground/90 mb-6 leading-[1.9] font-light" {...props} />
            ),
            blockquote: ({ ...props }) => (
              <blockquote
                className="border-primary/45 bg-primary/5 my-6 rounded-r-2xl border-l-2 px-4 py-3"
                {...props}
              />
            ),
            ul: ({ ...props }) => <ul className="mb-4 space-y-2 pl-5" {...props} />,
            ol: ({ ...props }) => <ol className="mb-4 list-decimal space-y-2 pl-5" {...props} />,
            li: ({ className, ...props }) => (
              <li
                className={`marker:text-primary/50 mb-3 leading-relaxed ${
                  typeof className === "string" && className.includes("task-list-item")
                    ? "list-none pl-0"
                    : "ml-6 pl-2"
                }`}
                {...props}
              />
            ),
            input: ({ type, checked, ...props }) =>
              type === "checkbox" ? (
                <input
                  type="checkbox"
                  checked={Boolean(checked)}
                  readOnly
                  tabIndex={-1}
                  aria-hidden="true"
                  className="mr-2 h-4 w-4 translate-y-[1px] rounded border border-cyan-400/35 bg-slate-950/90 text-cyan-400 accent-cyan-400"
                  {...props}
                />
              ) : (
                <input type={type} {...props} />
              ),
            strong: ({ ...props }) => (
              <strong
                className="text-primary decoration-primary/20 font-bold underline underline-offset-4"
                {...props}
              />
            ),
            em: ({ ...props }) => <em className="text-foreground/90 italic" {...props} />,
            del: ({ ...props }) => (
              <del className="text-muted-foreground/80 line-through" {...props} />
            ),
            sup: ({ ...props }) => (
              <sup className="text-primary/80 text-[0.72em] font-semibold" {...props} />
            ),
            section: ({ ...props }) => (
              <section
                className="mt-6 rounded-2xl border border-white/8 bg-white/[0.03] p-4"
                {...props}
              />
            ),
            a: ({ href, children, ...props }) => {
              if (href?.startsWith("#citation-")) {
                const index = parseInt(href.replace("#citation-", ""));
                const citation = citations?.[index - 1];

                return (
                  <InlineCitation
                    index={index}
                    onClick={() => {
                      if (onCitationClick && citation) {
                        onCitationClick(citation);
                      }
                    }}
                  />
                );
              }
              const openInNewTab = typeof href === "string" && !href.startsWith("#");
              return (
                <a
                  href={href}
                  target={openInNewTab ? "_blank" : undefined}
                  rel={openInNewTab ? "noreferrer noopener" : undefined}
                  className="text-primary decoration-primary/30 underline underline-offset-4 transition-colors hover:brightness-110"
                  {...props}
                >
                  {children}
                </a>
              );
            },
            img: ({ src, alt, ...props }) => (
              <span className="my-6 block overflow-hidden rounded-2xl border border-white/10 bg-black/20">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={src ?? ""}
                  alt={alt ?? ""}
                  loading="lazy"
                  decoding="async"
                  className="block h-auto w-full max-w-full"
                  {...props}
                />
              </span>
            ),
            code: ({ children, className, ...props }) => {
              const codeText = String(children ?? "");
              const looksBlock =
                (typeof className === "string" && className.includes("language-")) ||
                codeText.includes("\n");

              if (looksBlock) {
                return (
                  <code
                    className={`block px-4 py-3 font-mono text-[13px] leading-7 whitespace-pre-wrap ${className ?? ""}`}
                    {...props}
                  >
                    {children}
                  </code>
                );
              }

              return (
                <code
                  className="rounded-md border border-white/10 bg-black/10 px-1.5 py-0.5 text-[12px]"
                  {...props}
                >
                  {children}
                </code>
              );
            },
          }}
        >
          {contentWithLinks}
        </ReactMarkdown>
      </div>
    </motion.div>
  );
}
