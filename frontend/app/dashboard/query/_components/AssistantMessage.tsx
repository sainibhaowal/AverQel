"use client";

import { AlertCircle, Bot, Check, Copy, Trash2 } from "lucide-react";
import { useState } from "react";

import type { QueryThreadMessage } from "../_lib/stream-protocol";

import RichMessageRenderer from "./RichMessageRenderer";
import RetryRegenerateBar from "./RetryRegenerateBar";
import StreamingTypingIndicator from "./StreamingTypingIndicator";
import ThinkingPanel from "./ThinkingPanel";

interface AssistantMessageProps {
  mode?: "query" | "deepspace";
  message: QueryThreadMessage;
  isStreaming: boolean;
  canRegenerate?: boolean;
  onRetry?: () => void;
  onRegenerate?: (assistantMessageId: string) => void;
  onActivateVersion?: (messageId: string, versionId: string) => void;
  onDelete?: (messageId: string) => void;
  onPreviewDocument: (payload: { id: string; name: string; page?: number }) => void;
  onFollowupSelect: (query: string) => void;
}

export default function AssistantMessage({
  mode = "query",
  message,
  isStreaming,
  canRegenerate = false,
  onRegenerate,
  onActivateVersion,
  onDelete,
  onPreviewDocument,
  onFollowupSelect,
}: AssistantMessageProps) {
  const [copied, setCopied] = useState(false);
  const showWorkflowMeta = mode !== "deepspace";
  const hasRenderablePayload =
    message.content.trim().length > 0 ||
    Boolean(message.thinkingContent?.trim()) ||
    message.blocks.length > 0 ||
    message.citations.length > 0 ||
    Boolean(message.trace) ||
    (showWorkflowMeta && message.followups.length > 0) ||
    Boolean(message.error);

  if (!isStreaming && !hasRenderablePayload) {
    return null;
  }

  const versions = message.versions ?? [];
  const versionCount = message.versionCount ?? versions.length;
  const activeVersionPosition = Math.max(
    0,
    versions.findIndex((version) => version.id === message.activeVersionId),
  );

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  return (
    <article className="mx-auto max-w-[74rem] px-2 py-5 sm:px-3 sm:py-6">
      <div className="flex items-start gap-3 sm:gap-4">
        <div className="theme-accent-pill mt-1.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-[1.35rem] shadow-[0_18px_42px_-28px_rgba(99,102,241,0.35)] sm:h-11 sm:w-11 sm:rounded-[1.5rem]">
          <Bot size={18} className="text-primary" />
        </div>

        <div className="w-full flex-1">
          <div className="text-muted-foreground mb-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[10px] tracking-[0.24em] uppercase sm:mb-4 sm:text-[11px]">
            <span className="text-foreground font-semibold">AverQel AI</span>
            {message.cached ? <span className="text-foreground/34">cached</span> : null}
            {message.traceId ? (
              <span className="text-foreground/28 font-mono text-[10px] tracking-normal normal-case sm:text-[11px]">
                {message.traceId}
              </span>
            ) : null}
          </div>

          <div className="theme-panel text-foreground/90 min-h-[3.2rem] rounded-[1.8rem] px-4 py-4 sm:rounded-[2rem] sm:px-6 sm:py-5">
            {isStreaming && !message.content.trim() && !message.error ? (
              <div className="mb-4">
                <StreamingTypingIndicator phase={message.streamPhase} />
              </div>
            ) : null}

            {message.thinkingContent?.trim() ? (
              <ThinkingPanel content={message.thinkingContent} isStreaming={isStreaming} />
            ) : null}

            {message.error ? (
              <div className="border-danger/20 bg-danger/5 text-danger mb-5 flex items-start gap-3 rounded-[1.4rem] border px-4 py-3.5 text-sm">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <div>
                  <p className="font-semibold">{message.error.message}</p>
                  <p className="text-danger/60 mt-1 text-xs">{message.error.code}</p>
                </div>
              </div>
            ) : null}

            <RichMessageRenderer
              mode={mode}
              message={message}
              isStreaming={isStreaming}
              onPreviewDocument={onPreviewDocument}
              onFollowupSelect={onFollowupSelect}
            />

            {message.metrics && (
              <div className="border-glass-border/30 text-foreground/30 mt-5 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t pt-3 text-[10px] font-medium tracking-tight">
                {message.metrics.modelName && (
                  <span className="border-glass-border/30 flex items-center gap-1.5 border-r pr-4 tracking-[0.1em] uppercase">
                    <Bot size={11} className="opacity-40" />
                    {message.metrics.modelName}
                  </span>
                )}
                {message.metrics.tokensPerSec !== undefined && message.metrics.tokensPerSec > 0 && (
                  <span className="flex items-center gap-1.5">
                    <span className="bg-primary/40 h-1 w-1 rounded-full" />
                    {message.metrics.tokensPerSec} Tok/s
                  </span>
                )}
                {message.metrics.totalTokens !== undefined && message.metrics.totalTokens > 0 && (
                  <span className="flex items-center gap-1.5">
                    <span className="bg-primary/40 h-1 w-1 rounded-full" />
                    {message.metrics.totalTokens} Tokens
                  </span>
                )}
                {message.metrics.ttftMs !== undefined && message.metrics.ttftMs > 0 && (
                  <span className="flex items-center gap-1.5">
                    <span className="bg-primary/40 h-1 w-1 rounded-full" />
                    TTFT: {message.metrics.ttftMs}ms
                  </span>
                )}
              </div>
            )}
          </div>

          {!isStreaming ? (
            <div className="text-muted-foreground mt-3 flex flex-wrap items-center gap-2 text-xs">
              {versionCount > 1 && onActivateVersion ? (
                <>
                  <button
                    type="button"
                    onClick={() =>
                      onActivateVersion(
                        message.id,
                        versions[Math.max(0, activeVersionPosition - 1)]!.id,
                      )
                    }
                    disabled={activeVersionPosition === 0}
                    className="border-glass-border hover:bg-surface-1 rounded-full border px-2 py-1 transition disabled:opacity-40"
                  >
                    ←
                  </button>
                  <span>
                    {activeVersionPosition + 1} / {versionCount}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      onActivateVersion(
                        message.id,
                        versions[Math.min(versionCount - 1, activeVersionPosition + 1)]!.id,
                      )
                    }
                    disabled={activeVersionPosition >= versionCount - 1}
                    className="border-glass-border hover:bg-surface-1 rounded-full border px-2 py-1 transition disabled:opacity-40"
                  >
                    →
                  </button>
                </>
              ) : null}
              <button
                type="button"
                onClick={handleCopy}
                className="border-glass-border hover:bg-surface-1 inline-flex items-center gap-1 rounded-full border px-3 py-1 transition"
              >
                {copied ? <Check size={12} /> : <Copy size={12} />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
              {onDelete ? (
                <button
                  type="button"
                  onClick={() => onDelete(message.id)}
                  className="border-glass-border hover:bg-surface-1 inline-flex items-center gap-1 rounded-full border px-3 py-1 transition"
                >
                  <Trash2 size={12} />
                  <span>Delete</span>
                </button>
              ) : null}
              {canRegenerate ? (
                <RetryRegenerateBar onRegenerate={() => onRegenerate?.(message.id)} />
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}
