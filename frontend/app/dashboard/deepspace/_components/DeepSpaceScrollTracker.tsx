"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowUp } from "lucide-react";

import type {
  DeepSpaceHistoryVersion,
  DeepSpaceMessage,
  StructuredBlock,
} from "../_lib/deepspace-stream";

interface DeepSpaceScrollTrackerProps {
  messages: DeepSpaceMessage[];
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  onInsertActiveAnswer?: (content: string) => void;
}

function getVersionContent(version: DeepSpaceHistoryVersion | null | undefined): string {
  return version?.content || "";
}

function resolveFocusedAssistantMessage(
  messages: DeepSpaceMessage[],
  activeMessageId: string | null,
): DeepSpaceMessage | null {
  if (!activeMessageId) return null;

  let message = messages.find((item) => item.id === activeMessageId) ?? null;
  if (message?.role === "user") {
    const index = messages.findIndex((item) => item.id === message?.id);
    message = index >= 0 && messages[index + 1]?.role === "assistant" ? messages[index + 1] : null;
  }

  return message?.role === "assistant" ? message : null;
}

function appendStructuredBlocks(content: string, blocks: StructuredBlock[] | undefined): string {
  const fence = String.fromCharCode(96).repeat(3);
  let result = content;

  for (const block of blocks ?? []) {
    if (block.type === "chart" && !result.includes(fence + "chart")) {
      result +=
        "\n\n" +
        fence +
        "chart\n" +
        JSON.stringify(
          {
            title: block.title || "Chart Data",
            chart_type: block.chart_type,
            series: block.series,
            x_key: block.x_key,
            y_key: block.y_key,
            z_key: block.z_key,
          },
          null,
          2,
        ) +
        "\n" +
        fence +
        "\n";
    }

    if (block.type === "diagram" && block.syntax && !result.includes(block.syntax.trim())) {
      result += "\n\n" + fence + "mermaid\n" + block.syntax + "\n" + fence + "\n";
    }

    if (block.type === "table" && block.headers?.length && !result.includes(block.headers[0])) {
      result += "\n\n### " + (block.title || "Table Data") + "\n\n";
      result += "| " + block.headers.join(" | ") + " |\n";
      result += "| " + block.headers.map(() => "---").join(" | ") + " |\n";
      result += block.rows.map((row) => "| " + row.join(" | ") + " |").join("\n");
      result += "\n";
    }
  }

  return result;
}

function buildActiveAnswerContent(message: DeepSpaceMessage): string {
  const activeVersion = message.versions?.find((version) => version.id === message.activeVersionId);
  return appendStructuredBlocks(
    getVersionContent(activeVersion) || message.rawContent || message.content || "",
    message.blocks,
  );
}

export default function DeepSpaceScrollTracker({
  messages,
  scrollContainerRef,
  onInsertActiveAnswer,
}: DeepSpaceScrollTrackerProps) {
  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const [tooltipMessageId, setTooltipMessageId] = useState<string | null>(null);
  const messageObservationKey = useMemo(
    () => messages.map((message) => message.id).join("\u0000"),
    [messages],
  );

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container || typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => {
        let largestRatio = 0;
        let bestId: string | null = null;

        entries.forEach((entry) => {
          if (!entry.isIntersecting || entry.intersectionRatio <= largestRatio) return;
          const id = entry.target.getAttribute("data-message-id");
          if (id) {
            largestRatio = entry.intersectionRatio;
            bestId = id;
          }
        });

        if (bestId) {
          setActiveMessageId((current) => (current === bestId ? current : bestId));
        }
      },
      {
        root: container,
        rootMargin: "-15% 0px -40% 0px",
        threshold: [0.5],
      },
    );

    container.querySelectorAll("[data-message-id]").forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [messageObservationKey, scrollContainerRef]);

  const effectiveActiveId =
    activeMessageId && messages.some((message) => message.id === activeMessageId)
      ? activeMessageId
      : (messages[messages.length - 1]?.id ?? null);
  const focusedAssistantMessage = useMemo(
    () => resolveFocusedAssistantMessage(messages, effectiveActiveId),
    [effectiveActiveId, messages],
  );

  useEffect(() => {
    if (!tooltipMessageId) return;
    const timeout = window.setTimeout(() => setTooltipMessageId(null), 1400);
    return () => window.clearTimeout(timeout);
  }, [tooltipMessageId]);

  if (messages.length === 0) return null;

  const jumpToMessage = (messageId: string) => {
    const container = scrollContainerRef.current;
    const target = container?.querySelector<HTMLElement>('[data-message-id="' + messageId + '"]');
    if (!target) return;

    target.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
    setActiveMessageId(messageId);
    setTooltipMessageId(messageId);
  };

  return (
    <div className="pointer-events-auto absolute top-20 right-0 bottom-48 z-20 flex min-h-0 flex-col items-center gap-3 p-0">
      <div
        aria-label="DeepSpace message navigation"
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1 pl-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        <div className="relative flex min-h-full flex-col items-center gap-1.5 py-1">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute top-3 bottom-3 left-1/2 w-px -translate-x-1/2 border-l border-dashed border-cyan-300/30"
          />
          {messages.map((message, index) => {
            const isActive = message.id === effectiveActiveId;
            const isUser = message.role === "user";
            const preview = message.content.trim().slice(0, 28);
            const label =
              (isUser ? "Prompt" : "Answer") + " " + (index + 1) + (preview ? ": " + preview : "");

            return (
              <div key={message.id} className="group relative z-10 flex items-center justify-end">
                <button
                  type="button"
                  onClick={() => jumpToMessage(message.id)}
                  onMouseEnter={() => setTooltipMessageId(message.id)}
                  onFocus={() => setTooltipMessageId(message.id)}
                  aria-label={label}
                  className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full focus:ring-2 focus:ring-cyan-300/55 focus:ring-offset-2 focus:ring-offset-black/30 focus:outline-none"
                >
                  <span
                    className={[
                      "block rounded-full transition-colors duration-150",
                      isUser
                        ? isActive
                          ? "h-3 w-2.5 bg-[#c8b6ff]"
                          : "h-2.5 w-2.5 bg-[#cbd5e1]/32"
                        : isActive
                          ? "h-7 w-3 bg-[#a37ce6] shadow-[0_0_18px_rgba(163,124,230,0.45)]"
                          : "h-5 w-2.5 bg-[#c8b6ff]/28",
                      "group-hover:scale-110",
                    ].join(" ")}
                  />
                </button>
                <div
                  className={[
                    "pointer-events-none absolute right-full mr-3 max-w-[12rem] truncate rounded-2xl border px-3 py-1.5 text-[11px] leading-4 font-medium text-white shadow-[0_14px_30px_rgba(0,0,0,0.32)] backdrop-blur-md transition-all duration-200",
                    tooltipMessageId === message.id
                      ? "border-cyan-300/20 bg-slate-950/90 opacity-100"
                      : "border-white/8 bg-slate-950/82 opacity-0",
                  ].join(" ")}
                >
                  {label}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <button
        type="button"
        aria-label="Insert focused output"
        title="Insert focused output"
        onClick={() => {
          if (focusedAssistantMessage) {
            onInsertActiveAnswer?.(buildActiveAnswerContent(focusedAssistantMessage));
          }
        }}
        disabled={!focusedAssistantMessage}
        className="disabled:text-foreground/35 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-cyan-300/14 bg-cyan-300/8 text-cyan-100 shadow-[0_8px_18px_rgba(34,211,238,0.12)] transition-colors hover:bg-cyan-300/14 hover:text-white disabled:cursor-not-allowed disabled:border-white/8 disabled:bg-white/5 disabled:shadow-none"
      >
        <ArrowUp size={16} strokeWidth={2.5} />
      </button>
    </div>
  );
}
