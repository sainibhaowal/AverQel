"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

import InlineCitation from "@/app/components/query/InlineCitation";

export function InlineMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      // remarkGfm options: disable autoLinkLiterals so plain text containing
      // colons (e.g. "PG19: 1.057", "Note: value") is never converted into
      // <a> tags. Without this, remark-gfm treats "PG19:" as a URL-like
      // patterns and wraps the text in an <a> element, which inherits the
      // cyan link color — making table cell data appear blue.
      remarkPlugins={[[remarkGfm, { autoLinkLiterals: false }], remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        p: ({ children }) => <>{children}</>,
        pre: ({ children, ...props }) => (
          <pre className="theme-code-surface my-3 overflow-x-auto rounded-2xl px-0 py-0" {...props}>
            {children}
          </pre>
        ),
        h1: (props) => (
          <h1
            className="text-foreground mt-5 mb-3 text-[1.8rem] font-semibold tracking-[-0.04em]"
            {...props}
          />
        ),
        h2: (props) => (
          <h2
            className="text-foreground mt-4 mb-2 text-[1.35rem] font-semibold tracking-[-0.03em]"
            {...props}
          />
        ),
        h3: (props) => (
          <h3
            className="text-foreground mt-4 mb-2 text-[1.08rem] font-semibold tracking-[-0.025em]"
            {...props}
          />
        ),
        h4: (props) => (
          <h4
            className="text-foreground mt-4 mb-2 text-[1rem] font-semibold tracking-[-0.02em]"
            {...props}
          />
        ),
        a: ({ href, children, ...props }) => {
          if (href?.startsWith("#citation-")) {
            const index = Number.parseInt(href.replace("#citation-", ""), 10);
            if (!Number.isNaN(index)) {
              return <InlineCitation index={index} />;
            }
          }
          const openInNewTab = typeof href === "string" && !href.startsWith("#");
          return (
            <a
              href={href}
              target={openInNewTab ? "_blank" : undefined}
              rel={openInNewTab ? "noreferrer noopener" : undefined}
              className="text-primary decoration-primary/30 underline underline-offset-4"
              {...props}
            >
              {children}
            </a>
          );
        },
        img: ({ src, alt, ...props }) => (
          <span className="my-3 block overflow-hidden rounded-2xl border border-white/10 bg-black/20">
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
        blockquote: ({ children, ...props }) => (
          <blockquote
            className="border-primary/45 bg-primary/5 my-3 rounded-r-2xl border-l-2 px-4 py-3"
            {...props}
          >
            {children}
          </blockquote>
        ),
        h5: (props) => (
          <h5
            className="text-primary mt-4 mb-2 text-[0.95rem] font-semibold tracking-[0.04em] uppercase"
            {...props}
          />
        ),
        h6: (props) => (
          <h6
            className="text-foreground/82 mt-4 mb-2 text-[0.9rem] font-semibold tracking-tight"
            {...props}
          />
        ),
        ul: (props) => <ul className="my-2 list-disc space-y-2 pl-5" {...props} />,
        ol: (props) => <ol className="my-2 list-decimal space-y-2 pl-5" {...props} />,
        li: ({ className, children, ...props }) => {
          const isTaskItem = typeof className === "string" && className.includes("task-list-item");
          return (
            <li
              className={`${isTaskItem ? "list-none pl-0" : ""} marker:text-primary/50 leading-7`}
              {...props}
            >
              {children}
            </li>
          );
        },
        input: ({ type, checked, ...props }) => {
          if (type !== "checkbox") return <input type={type} {...props} />;
          return (
            <input
              type="checkbox"
              checked={Boolean(checked)}
              readOnly
              tabIndex={-1}
              aria-hidden="true"
              className="mr-2 h-4 w-4 translate-y-[1px] rounded border border-cyan-400/35 bg-slate-950/90 align-middle text-cyan-400 accent-cyan-400"
              {...props}
            />
          );
        },
        strong: (props) => <strong className="text-foreground font-semibold" {...props} />,
        em: (props) => <em className="italic" {...props} />,
        del: (props) => <del className="text-muted-foreground/80 line-through" {...props} />,
        sup: (props) => <sup className="text-primary/80 text-[0.72em] font-semibold" {...props} />,
        section: ({ children, ...props }) => (
          <section
            className="mt-5 rounded-2xl border border-white/8 bg-white/[0.03] p-4"
            {...props}
          >
            {children}
          </section>
        ),
        code: ({ children, className, ...props }) => {
          const codeText = String(children ?? "");
          const looksBlock =
            (typeof className === "string" && className.includes("language-")) ||
            codeText.includes("\n");
          if (looksBlock) {
            return (
              <code
                className={`block px-4 py-3 text-[13px] leading-7 font-[var(--font-mono)] whitespace-pre-wrap ${className ?? ""}`}
                {...props}
              >
                {children}
              </code>
            );
          }

          return (
            <code className="theme-code-inline rounded-md px-1.5 py-0.5 text-[13px]" {...props}>
              {children}
            </code>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
