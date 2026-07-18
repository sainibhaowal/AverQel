"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { StreamCardBlock } from "../_lib/stream-protocol";

interface CalloutCardProps {
  block: StreamCardBlock;
  isStreaming?: boolean;
}

function toneClasses(tone: StreamCardBlock["tone"]) {
  switch (tone) {
    case "success":
      return "border-emerald-500/22 bg-emerald-500/[0.08] text-emerald-800 dark:text-emerald-50";
    case "warning":
      return "border-amber-500/22 bg-amber-500/[0.08] text-amber-800 dark:text-amber-50";
    case "error":
      return "border-red-500/22 bg-red-500/[0.08] text-red-800 dark:text-red-50";
    case "info":
      return "border-primary/22 bg-primary/8 text-primary dark:text-primary-foreground/90";
    default:
      return "theme-panel-muted text-foreground/90";
  }
}

export default function CalloutCard({ block, isStreaming = false }: CalloutCardProps) {
  const showStreamingHint = isStreaming && block.incomplete;

  return (
    <section
      className={`rounded-[1.75rem] border px-5 py-5 shadow-[0_24px_70px_-48px_rgba(15,23,42,0.94)] sm:px-6 ${toneClasses(block.tone)}`}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h4 className="text-[15px] font-semibold tracking-[-0.015em]">{block.title}</h4>
        <div className="flex items-center gap-2">
          {showStreamingHint ? (
            <span className="rounded-full border border-current/15 bg-white/35 px-2.5 py-1 text-[10px] font-semibold tracking-[0.16em] text-current/70 uppercase dark:bg-black/10">
              streaming
            </span>
          ) : null}
          <span className="rounded-full border border-current/15 bg-white/35 px-2.5 py-1 text-[10px] font-semibold tracking-[0.16em] text-current/70 uppercase dark:bg-black/10">
            {block.tone}
          </span>
        </div>
      </div>
      <div
        className={`text-[14px] leading-7 whitespace-pre-wrap text-current/86 ${
          showStreamingHint ? "animate-pulse" : ""
        }`}
      >
        <ReactMarkdown
          remarkPlugins={[[remarkGfm, { autoLinkLiterals: false }]]}
          components={{
            pre: ({ children, ...props }) => (
              <pre
                className="theme-code-surface my-3 overflow-x-auto rounded-2xl px-0 py-0"
                {...props}
              >
                {children}
              </pre>
            ),
            h1: (props) => (
              <h1 className="mt-5 mb-3 text-2xl font-bold tracking-[-0.04em]" {...props} />
            ),
            h2: (props) => (
              <h2 className="mt-4 mb-2 text-xl font-semibold tracking-[-0.03em]" {...props} />
            ),
            p: (props) => <p className="mb-3 last:mb-0" {...props} />,
            h5: (props) => (
              <h5 className="mt-4 mb-2 text-[0.95rem] font-semibold uppercase" {...props} />
            ),
            h6: (props) => (
              <h6 className="mt-4 mb-2 text-[0.9rem] font-semibold tracking-tight" {...props} />
            ),
            blockquote: (props) => (
              <blockquote
                className="border-primary/45 bg-primary/5 my-4 rounded-r-2xl border-l-2 px-4 py-3"
                {...props}
              />
            ),
            ul: (props) => <ul className="mb-3 list-disc space-y-2 pl-5 last:mb-0" {...props} />,
            ol: (props) => <ol className="mb-3 list-decimal space-y-2 pl-5 last:mb-0" {...props} />,
            li: ({ className, ...props }) => (
              <li
                className={`${typeof className === "string" && className.includes("task-list-item") ? "list-none pl-0" : ""} leading-7`}
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
            strong: (props) => <strong className="font-semibold text-current" {...props} />,
            em: (props) => <em className="text-current/90 italic" {...props} />,
            del: (props) => <del className="text-current/75 line-through" {...props} />,
            sup: (props) => (
              <sup className="text-[0.72em] font-semibold text-current/75" {...props} />
            ),
            section: (props) => (
              <section
                className="mt-5 rounded-2xl border border-white/8 bg-white/[0.03] p-4"
                {...props}
              />
            ),
            a: ({ href, children, ...props }) => {
              const openInNewTab = typeof href === "string" && !href.startsWith("#");
              return (
                <a
                  href={href}
                  target={openInNewTab ? "_blank" : undefined}
                  rel={openInNewTab ? "noreferrer noopener" : undefined}
                  className="underline decoration-current/30 underline-offset-4"
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
                  className="rounded bg-black/10 px-1.5 py-0.5 text-[12px] dark:bg-white/10"
                  {...props}
                >
                  {children}
                </code>
              );
            },
          }}
        >
          {block.content}
        </ReactMarkdown>
      </div>
    </section>
  );
}
