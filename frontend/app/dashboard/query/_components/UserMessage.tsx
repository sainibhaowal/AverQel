"use client";

import { Check, Copy, CornerDownLeft, Edit3, X } from "lucide-react";
import { useState } from "react";

import type { QueryThreadMessage } from "../_lib/stream-protocol";

interface UserMessageProps {
  message: QueryThreadMessage;
  canEdit: boolean;
  onStartEdit: (messageId: string) => void;
  onCancelEdit: (messageId: string) => void;
  onDraftChange: (messageId: string, value: string) => void;
  onSaveEdit: (messageId: string, value: string) => void;
  onActivateVersion: (messageId: string, versionId: string) => void;
}

export default function UserMessage({
  message,
  canEdit,
  onStartEdit,
  onCancelEdit,
  onDraftChange,
  onSaveEdit,
  onActivateVersion,
}: UserMessageProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  const activeVersionPosition = Math.max(
    0,
    message.versions.findIndex((version) => version.id === message.activeVersionId),
  );

  return (
    <article className="mx-auto max-w-[74rem] px-2 py-4 sm:px-3 sm:py-5">
      <div className="flex justify-end">
        <div className="max-w-[min(48rem,92%)] sm:max-w-[min(48rem,80%)]">
          <div className="text-primary/60 mb-2 pr-1 text-right text-[10px] font-bold tracking-[0.24em] uppercase">
            You
          </div>
          <div className="theme-panel-strong text-foreground/95 rounded-[1.75rem] px-4 py-3.5 text-[15px] leading-8 shadow-[0_28px_72px_-46px_rgba(99,102,241,0.22)] sm:rounded-[1.95rem] sm:px-5 sm:py-4">
            {message.isEditing ? (
              <textarea
                value={message.draftContent ?? message.content}
                onChange={(event) => onDraftChange(message.id, event.target.value.slice(0, 4000))}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    onSaveEdit(message.id, (message.draftContent ?? message.content).trim());
                  } else if (event.key === "Escape") {
                    event.preventDefault();
                    onCancelEdit(message.id);
                  }
                }}
                className="min-h-[88px] w-full resize-none bg-transparent outline-none"
                autoFocus
              />
            ) : (
              <div className="break-words whitespace-pre-wrap">{message.content}</div>
            )}
          </div>
          <div className="text-foreground/36 mt-2 flex items-center justify-end gap-2 pr-1 text-[11px]">
            {message.versionCount > 1 ? (
              <>
                <button
                  type="button"
                  onClick={() =>
                    onActivateVersion(
                      message.id,
                      message.versions[Math.max(0, activeVersionPosition - 1)]!.id,
                    )
                  }
                  disabled={activeVersionPosition === 0}
                  className="rounded-full border border-white/10 px-2 py-0.5 disabled:opacity-40"
                >
                  ←
                </button>
                <span>
                  {activeVersionPosition + 1} / {message.versionCount}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    onActivateVersion(
                      message.id,
                      message.versions[
                        Math.min(message.versionCount - 1, activeVersionPosition + 1)
                      ]!.id,
                    )
                  }
                  disabled={activeVersionPosition >= message.versionCount - 1}
                  className="rounded-full border border-white/10 px-2 py-0.5 disabled:opacity-40"
                >
                  →
                </button>
              </>
            ) : null}
            <button type="button" onClick={handleCopy} className="inline-flex items-center gap-1">
              {copied ? <Check size={12} /> : <Copy size={12} />}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
            {canEdit && !message.isEditing ? (
              <button
                type="button"
                onClick={() => onStartEdit(message.id)}
                className="inline-flex items-center gap-1"
              >
                <Edit3 size={12} />
                <span>Edit</span>
              </button>
            ) : null}
            {message.isEditing ? (
              <>
                <button
                  type="button"
                  onClick={() =>
                    onSaveEdit(message.id, (message.draftContent ?? message.content).trim())
                  }
                  className="inline-flex items-center gap-1"
                >
                  <Check size={12} />
                  <span>Save</span>
                </button>
                <button
                  type="button"
                  onClick={() => onCancelEdit(message.id)}
                  className="inline-flex items-center gap-1"
                >
                  <X size={12} />
                  <span>Cancel</span>
                </button>
              </>
            ) : (
              <>
                <CornerDownLeft size={12} />
                <span>Stored in this conversation</span>
              </>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
