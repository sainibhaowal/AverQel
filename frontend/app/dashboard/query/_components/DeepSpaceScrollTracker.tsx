"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ArrowUp } from "lucide-react";
import type { QueryThreadMessage, QueryThreadMessageVersion } from "../_lib/stream-protocol";
import type {
  DeepSpaceHistoryVersion,
  DeepSpaceMessage,
} from "../../deepspace/_lib/deepspace-stream";

interface DeepSpaceScrollTrackerProps {
  messages: (QueryThreadMessage | DeepSpaceMessage)[];
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  onInsertActiveAnswer?: (content: string) => void;
}

type TrackerVersion = QueryThreadMessageVersion | DeepSpaceHistoryVersion;

function getVersionContent(version: TrackerVersion | null | undefined): string {
  if (!version) return "";
  if ("rawContent" in version && version.rawContent) return version.rawContent;
  return version.content || "";
}

function resolveFocusedAssistantMessage(
  messages: (QueryThreadMessage | DeepSpaceMessage)[],
  effectiveActiveId: string | null,
): QueryThreadMessage | DeepSpaceMessage | null {
  if (!effectiveActiveId) return null;

  let msg = messages.find((m) => m.id === effectiveActiveId) ?? null;

  if (msg && msg.role === "user") {
    const idx = messages.findIndex((m) => m.id === msg?.id);
    if (idx >= 0 && idx + 1 < messages.length && messages[idx + 1].role === "assistant") {
      msg = messages[idx + 1];
    } else {
      return null;
    }
  }

  return msg && msg.role === "assistant" ? msg : null;
}

function buildActiveAnswerContent(msg: QueryThreadMessage | DeepSpaceMessage): string {
  const activeVersion =
    "versions" in msg && Array.isArray(msg.versions)
      ? msg.versions.find((v) => v.id === (msg as QueryThreadMessage).activeVersionId)
      : null;

  // Prioritize rawContent since it retains `json fences for charts, then append structured blocks if missing.
  let baseContent = getVersionContent(activeVersion) || msg.rawContent || msg.content || "";

  if ("blocks" in msg && Array.isArray(msg.blocks)) {
    const chartBlocks = msg.blocks.filter((b) => b.type === "chart");
    for (const chart of chartBlocks) {
      if (
        !baseContent.includes("```chart") &&
        (!chart.raw_payload || !baseContent.includes(chart.raw_payload))
      ) {
        const payload = {
          title: chart.title || "Chart Data",
          chart_type: chart.chart_type,
          series: chart.series,
          x_key: chart.x_key,
          y_key: chart.y_key,
          z_key: chart.z_key,
        };
        baseContent += `\n\n\`\`\`json\n${JSON.stringify(payload, null, 2)}\n\`\`\`\n`;
      }
    }

    const diagramBlocks = msg.blocks.filter((b) => b.type === "diagram");
    for (const diag of diagramBlocks) {
      if (
        diag.syntax &&
        typeof diag.syntax === "string" &&
        !baseContent.includes(diag.syntax.trim())
      ) {
        baseContent += `\n\n\`\`\`mermaid\n${diag.syntax}\n\`\`\`\n`;
      }
    }

    const tableBlocks = msg.blocks.filter((b) => b.type === "table");
    for (const table of tableBlocks) {
      if (table.headers && table.rows && !baseContent.includes(table.headers[0] || "")) {
        let tableStr = `\n\n### ${table.title || "Table Data"}\n\n`;
        tableStr += `| ${table.headers.join(" | ")} |\n`;
        tableStr += `| ${table.headers.map(() => "---").join(" | ")} |\n`;
        table.rows.forEach((row: string[]) => {
          tableStr += `| ${row.join(" | ")} |\n`;
        });
        baseContent += tableStr + "\n";
      }
    }
  }

  return baseContent;
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
    if (!container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        let largestRatio = 0;
        let bestId: string | null = null;

        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const ratio = entry.intersectionRatio;
            const id = entry.target.getAttribute("data-message-id");
            if (id && ratio > largestRatio) {
              largestRatio = ratio;
              bestId = id;
            }
          }
        });

        if (bestId) {
          setActiveMessageId(bestId);
        }
      },
      {
        root: container,
        rootMargin: "-15% 0px -40% 0px",
        threshold: [0, 0.1, 0.3, 0.5, 0.8, 1.0],
      },
    );

    const messageElements = container.querySelectorAll("[data-message-id]");
    messageElements.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, [messageObservationKey, scrollContainerRef]);

  // Fallback to the latest message if nothing is explicitly active
  const effectiveActiveId =
    activeMessageId ?? (messages.length > 0 ? messages[messages.length - 1].id : null);

  const focusedAssistantMessage = useMemo(
    () => resolveFocusedAssistantMessage(messages, effectiveActiveId),
    [effectiveActiveId, messages],
  );

  useEffect(() => {
    if (!tooltipMessageId) return;

    const timeout = window.setTimeout(() => {
      setTooltipMessageId((current) => (current === tooltipMessageId ? null : current));
    }, 1400);

    return () => window.clearTimeout(timeout);
  }, [tooltipMessageId]);

  if (messages.length === 0) return null;

  const jumpToMessage = (messageId: string) => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const target = container.querySelector<HTMLElement>(`[data-message-id="${messageId}"]`);
    if (!target) return;

    target.scrollIntoView({
      behavior: "smooth",
      block: "center",
      inline: "nearest",
    });
    setActiveMessageId(messageId);
    setTooltipMessageId(messageId);
  };

  const getMessageLabel = (msg: QueryThreadMessage | DeepSpaceMessage, index: number) => {
    const order = index + 1;
    if (msg.role === "user") {
      const preview = msg.content.trim().slice(0, 28);
      return preview ? `Prompt ${order}: ${preview}` : `Prompt ${order}`;
    }

    const preview = msg.content.trim().slice(0, 28);
    return preview ? `Answer ${order}: ${preview}` : `Answer ${order}`;
  };

  return (
    <div className="pointer-events-auto absolute top-20 right-0 bottom-48 z-20 flex min-h-0 flex-col items-center gap-3 p-0">
      <div
        aria-label="DeepSpace message navigation"
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden pl-3 pr-1"
      >
        <div className="flex flex-col items-center gap-1.5">
          {messages.map((msg, index) => {
            const isActive = msg.id === effectiveActiveId;
            const isUser = msg.role === "user";
            const label = getMessageLabel(msg, index);
            const isTooltipVisible = tooltipMessageId === msg.id;
            return (
              <motion.div
                key={msg.id}
                className="group relative flex items-center justify-end"
                layout
              >
                <motion.button
                  type="button"
                  onClick={() => jumpToMessage(msg.id)}
                  onMouseEnter={() => setTooltipMessageId(msg.id)}
                  onFocus={() => setTooltipMessageId(msg.id)}
                  aria-label={label}
                  className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full focus:ring-2 focus:ring-cyan-300/55 focus:ring-offset-2 focus:ring-offset-black/30 focus:outline-none"
                  layout
                >
                  <span
                    className={`block rounded-full transition-all duration-300 ${
                      isUser
                        ? isActive
                          ? "h-3 w-2.5 bg-[#c8b6ff]"
                          : "h-2.5 w-2.5 bg-[#cbd5e1]/32"
                        : isActive
                          ? "h-7 w-3 bg-[#a37ce6] shadow-[0_0_18px_rgba(163,124,230,0.45)]"
                          : "h-5 w-2.5 bg-[#c8b6ff]/28"
                    } group-hover:scale-110`}
                  />
                </motion.button>
                <div
                  className={`pointer-events-none absolute right-full mr-3 max-w-[12rem] rounded-2xl border px-3 py-1.5 text-[11px] leading-4 font-medium truncate text-white shadow-[0_14px_30px_rgba(0,0,0,0.32)] backdrop-blur-md transition-all duration-200 ${
                    isTooltipVisible
                      ? "border-cyan-300/20 bg-slate-950/90 opacity-100"
                      : "border-white/8 bg-slate-950/82 opacity-0"
                  }`}
                >
                  {label}
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      <button
        type="button"
        aria-label="Insert focused output"
        title="Insert focused output"
        onClick={() => {
          if (!focusedAssistantMessage) return;
          onInsertActiveAnswer?.(buildActiveAnswerContent(focusedAssistantMessage));
        }}
        disabled={!focusedAssistantMessage}
        className="disabled:text-foreground/35 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-cyan-300/14 bg-cyan-300/8 text-cyan-100 shadow-[0_8px_18px_rgba(34,211,238,0.12)] transition-colors hover:bg-cyan-300/14 hover:text-white disabled:cursor-not-allowed disabled:border-white/8 disabled:bg-white/5 disabled:shadow-none"
      >
        <ArrowUp size={16} strokeWidth={2.5} />
      </button>
    </div>
  );
}
