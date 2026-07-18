"use client";

import { useEffect, useRef, useState } from "react";
import { Download, FileCode, FileText, FileType, Flag, ThumbsDown, ThumbsUp } from "lucide-react";

import { fetchWithAuth } from "@/lib/api";
import { exportToDocx, exportToMarkdown, exportToPDF } from "@/lib/exportUtils";

interface FeedbackActionsProps {
  messageId: string;
  content: string;
}

export default function FeedbackActions({ messageId, content }: FeedbackActionsProps) {
  const [feedbackState, setFeedbackState] = useState<"helpful" | "unhelpful" | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowExportMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const submitFeedback = async (isHelpful: boolean) => {
    if (isSubmitting) return;
    setIsSubmitting(true);

    try {
      const response = await fetchWithAuth("/feedback", {
        method: "POST",
        body: JSON.stringify({ message_id: messageId, is_helpful: isHelpful }),
      });

      if (response && response.ok) {
        setFeedbackState(isHelpful ? "helpful" : "unhelpful");
      }
    } catch (error) {
      console.error("Failed to submit feedback", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="border-glass-border/40 flex flex-wrap items-center gap-2.5 border-t pt-4 text-xs"
      ref={menuRef}
    >
      <button
        onClick={() => submitFeedback(true)}
        disabled={isSubmitting || feedbackState !== null}
        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 transition ${
          feedbackState === "helpful"
            ? "border-emerald-500/28 bg-emerald-500/8 text-emerald-700 dark:text-emerald-300"
            : "theme-chip text-foreground/58 hover:text-foreground hover:border-white/20 dark:hover:text-white"
        }`}
      >
        <ThumbsUp size={13} />
        Helpful
      </button>

      <button
        onClick={() => submitFeedback(false)}
        disabled={isSubmitting || feedbackState !== null}
        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 transition ${
          feedbackState === "unhelpful"
            ? "border-red-500/28 bg-red-500/8 text-red-700 dark:text-red-300"
            : "theme-chip text-foreground/58 hover:text-foreground hover:border-white/20 dark:hover:text-white"
        }`}
      >
        <ThumbsDown size={13} />
        Needs work
      </button>

      <div className="relative">
        <button
          onClick={() => setShowExportMenu((value) => !value)}
          className="theme-chip text-foreground/58 hover:text-foreground inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 transition hover:border-white/20 dark:hover:text-white"
        >
          <Download size={13} />
          Export
        </button>

        {showExportMenu ? (
          <div className="theme-panel-strong absolute bottom-full left-0 z-50 mb-2 w-48 overflow-hidden rounded-[1.2rem] shadow-2xl backdrop-blur-xl">
            <button
              onClick={() => {
                exportToMarkdown(content);
                setShowExportMenu(false);
              }}
              className="text-foreground/84 hover:bg-foreground/[0.04] flex w-full items-center gap-2 px-3 py-3 text-left text-sm transition dark:hover:bg-white/[0.05]"
            >
              <FileCode size={15} className="text-cyan-700 dark:text-cyan-300" /> Markdown
            </button>
            <button
              onClick={() => {
                exportToPDF(content);
                setShowExportMenu(false);
              }}
              className="text-foreground/84 hover:bg-foreground/[0.04] flex w-full items-center gap-2 px-3 py-3 text-left text-sm transition dark:hover:bg-white/[0.05]"
            >
              <FileType size={15} className="text-rose-700 dark:text-rose-300" /> PDF
            </button>
            <button
              onClick={() => {
                exportToDocx(content);
                setShowExportMenu(false);
              }}
              className="text-foreground/84 hover:bg-foreground/[0.04] flex w-full items-center gap-2 px-3 py-3 text-left text-sm transition dark:hover:bg-white/[0.05]"
            >
              <FileText size={15} className="text-indigo-700 dark:text-indigo-300" /> DOCX
            </button>
          </div>
        ) : null}
      </div>

      <button
        onClick={() => submitFeedback(false)}
        disabled={isSubmitting || feedbackState !== null}
        className="theme-chip text-foreground/58 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 transition hover:border-red-400/22 hover:text-red-700 dark:hover:text-red-300"
      >
        <Flag size={13} />
        Report
      </button>
    </div>
  );
}
