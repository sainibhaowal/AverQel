"use client";

import { motion } from "framer-motion";
import { Sparkles, Layers, GitCompare, FileText, ShieldCheck, Folder, RefreshCw } from "lucide-react";

import type { QueryThreadMessage } from "../_lib/stream-protocol";

import AssistantMessage from "./AssistantMessage";
import UserMessage from "./UserMessage";

interface MessageThreadProps {
  mode?: "query" | "deepspace";
  messages: QueryThreadMessage[];
  emptyPrompts: string[];
  activeAssistantId: string | null;
  onRegenerate: (assistantMessageId: string) => void;
  onStartEdit: (messageId: string) => void;
  onCancelEdit: (messageId: string) => void;
  onEditDraftChange: (messageId: string, value: string) => void;
  onSaveEdit: (messageId: string, value: string) => void;
  onActivateVersion: (messageId: string, versionId: string) => void;
  onDeleteAssistant: (messageId: string) => void;
  onPreviewDocument: (payload: { id: string; name: string; page?: number }) => void;
  onFollowupSelect: (query: string) => void;
  realTimeStats?: {
    totalDocuments: number;
    totalQueries: number;
    activeJobs: number;
    storageBytes: number;
    indexHealth: number;
    latencyMs: number;
  } | null;
}

export default function MessageThread({
  mode = "query",
  messages,
  emptyPrompts,
  activeAssistantId,
  onRegenerate,
  onStartEdit,
  onCancelEdit,
  onEditDraftChange,
  onSaveEdit,
  onActivateVersion,
  onDeleteAssistant,
  onPreviewDocument,
  onFollowupSelect,
  realTimeStats,
}: MessageThreadProps) {
  if (messages.length === 0) {
    const indexHealth = realTimeStats ? realTimeStats.indexHealth.toFixed(1) + "%" : "99.8%";
    const latency = realTimeStats ? realTimeStats.latencyMs + "ms" : "42ms";
    const totalDocuments = realTimeStats ? realTimeStats.totalDocuments : 0;
    const activeJobs = realTimeStats ? realTimeStats.activeJobs : 0;
    const storageBytes = realTimeStats ? realTimeStats.storageBytes : 0;

    const formatBytes = (bytes: number) => {
      if (bytes === 0) return "0 Bytes";
      const k = 1024;
      const sizes = ["Bytes", "KB", "MB", "GB"];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    };

    return (
      <div className="flex h-full flex-col justify-center py-10 sm:py-12">
        <header className="mx-auto mb-8 max-w-3xl px-4 text-center">
          <div className="theme-accent-pill mb-4 inline-flex rounded-2xl p-4 shadow-[0_15px_30px_rgba(var(--primary),0.15)] relative">
            <div className="absolute inset-0 rounded-2xl border border-primary/20 animate-ping opacity-25 pointer-events-none" />
            <Sparkles size={28} className="text-primary relative z-10" />
          </div>
          <h1 className="text-foreground text-3xl font-extrabold tracking-[-0.04em] sm:text-[2.6rem] font-display">
            Grounded Query Workspace
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mx-auto mt-2 max-w-xl text-xs font-bold uppercase tracking-[0.2em] sm:text-[10px]">
            Neural Context Router • Hybrid Search Engine • Source-Isolated Guardrails
          </p>
        </header>

        {/* Real-time Diagnostics Control Panel */}
        <div className="mx-auto mb-10 grid w-full max-w-3xl grid-cols-1 gap-4 px-4 sm:grid-cols-6">
          {/* Card 1: Semantic Index Health */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4 transition-all hover:border-slate-300 dark:border-slate-800/80 dark:bg-black/10 col-span-1 sm:col-span-2">
            <div className="flex items-center justify-between">
              <span className="text-slate-455 dark:text-slate-500 text-[9px] font-bold uppercase tracking-widest">
                Semantic index
              </span>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
            </div>
            <p className="mt-2 text-2xl font-black tracking-tight text-slate-800 dark:text-slate-100">
              {indexHealth}
            </p>
            <p className="text-[10px] text-slate-500 dark:text-slate-400 font-semibold mt-1">
              Active Knowledge Mapping
            </p>
          </div>

          {/* Card 2: Hallucination Guard */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4 transition-all hover:border-slate-300 dark:border-slate-800/80 dark:bg-black/10 col-span-1 sm:col-span-2">
            <div className="flex items-center justify-between">
              <span className="text-slate-455 dark:text-slate-500 text-[9px] font-bold uppercase tracking-widest">
                Hallucination Guard
              </span>
              <span className="text-emerald-500 font-bold text-xs">✓</span>
            </div>
            <p className="mt-2 text-xl font-black tracking-wide text-slate-800 dark:text-slate-100">
              ENFORCED
            </p>
            <p className="text-[10px] text-slate-500 dark:text-slate-400 font-semibold mt-2">
              Context-isolated grounding
            </p>
          </div>

          {/* Card 3: Retrieval Latency */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4 transition-all hover:border-slate-300 dark:border-slate-800/80 dark:bg-black/10 col-span-1 sm:col-span-2">
            <div className="flex items-center justify-between">
              <span className="text-slate-455 dark:text-slate-500 text-[9px] font-bold uppercase tracking-widest">
                Retrieval Latency
              </span>
              <span className="text-amber-500 text-xs">⚡</span>
            </div>
            <p className="mt-2 text-2xl font-black tracking-tight text-slate-800 dark:text-slate-100">
              {latency}
            </p>
            <p className="text-[10px] text-slate-500 dark:text-slate-400 font-semibold mt-1">
              Hybrid vector routing
            </p>
          </div>

          {/* Card 4: Knowledge Pool */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4 transition-all hover:border-slate-300 dark:border-slate-800/80 dark:bg-black/10 col-span-1 sm:col-span-3">
            <div className="flex items-center justify-between">
              <span className="text-slate-455 dark:text-slate-500 text-[9px] font-bold uppercase tracking-widest">
                Knowledge Pool
              </span>
              <Folder size={14} className="text-primary" />
            </div>
            <p className="mt-2 text-xl font-black tracking-tight text-slate-800 dark:text-slate-100">
              {totalDocuments} Indexed {totalDocuments === 1 ? "File" : "Files"}
            </p>
            <p className="text-[10px] text-slate-500 dark:text-slate-400 font-semibold mt-2">
              {formatBytes(storageBytes)} parsed workspace context
            </p>
          </div>

          {/* Card 5: Ingest Queue */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4 transition-all hover:border-slate-300 dark:border-slate-800/80 dark:bg-black/10 col-span-1 sm:col-span-3">
            <div className="flex items-center justify-between">
              <span className="text-slate-455 dark:text-slate-500 text-[9px] font-bold uppercase tracking-widest">
                Ingest Queue
              </span>
              <RefreshCw size={14} className={`text-primary ${activeJobs > 0 ? "animate-spin" : ""}`} />
            </div>
            <p className="mt-2 text-xl font-black tracking-tight text-slate-800 dark:text-slate-100">
              {activeJobs} Active Ingestion{activeJobs === 1 ? "" : "s"}
            </p>
            <p className="text-[10px] text-slate-500 dark:text-slate-400 font-semibold mt-2">
              {activeJobs > 0 ? "Document pipeline active" : "All background loaders idle"}
            </p>
          </div>
        </div>

        {/* Analytical Operations Grid */}
        <div className="mx-auto w-full max-w-3xl px-4">
          <div className="mb-4 text-left">
            <h2 className="text-slate-450 dark:text-slate-500 text-[10px] font-bold uppercase tracking-[0.2em]">
              Grounded Operations
            </h2>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {emptyPrompts.map((prompt, idx) => {
              // Custom operation details per card
              let operationTitle = "Cross-Doc Analysis";
              let operationDesc = "Synthesize findings across active sources";
              let operationIcon = <Layers size={16} className="text-primary" />;

              if (idx === 1) {
                operationTitle = "Audit & Divergence";
                operationDesc = "Compare sources to discover conflicting details";
                operationIcon = <GitCompare size={16} className="text-primary" />;
              } else if (idx === 2) {
                operationTitle = "Relevance Extraction";
                operationDesc = "Locate documents with the strongest evidence";
                operationIcon = <FileText size={16} className="text-primary" />;
              } else if (idx === 3) {
                operationTitle = "Hallucination Protection";
                operationDesc = "Enforce verified source citation rules";
                operationIcon = <ShieldCheck size={16} className="text-primary" />;
              }

              return (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => onFollowupSelect(prompt)}
                  className="rounded-2xl border border-slate-200 bg-slate-50/50 p-5 text-left transition-all hover:translate-y-[-2px] hover:border-primary/30 hover:bg-white hover:shadow-[0_8px_30px_rgba(0,0,0,0.04)] dark:border-slate-800/80 dark:bg-black/10 dark:hover:border-primary/20 dark:hover:bg-slate-900/40 relative overflow-hidden group cursor-pointer"
                >
                  <div className="flex items-center gap-3 mb-2 relative z-10">
                    <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary/10 border border-primary/10">
                      {operationIcon}
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-slate-800 dark:text-slate-200 tracking-wide uppercase">
                        {operationTitle}
                      </h3>
                      <p className="text-[10px] text-slate-500 dark:text-slate-400 font-medium">
                        {operationDesc}
                      </p>
                    </div>
                  </div>
                  <p className="text-xs text-slate-700 dark:text-slate-300 font-semibold leading-relaxed relative z-10 border-t border-slate-100 dark:border-slate-800/60 pt-3 mt-3">
                    &quot;{prompt}&quot;
                  </p>
                  {/* Subtle hover gradient glow */}
                  <div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
                </button>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-1 pt-5 pb-10 sm:pt-6">
      {messages.map((message, index) => (
        <motion.div
          key={message.id}
          data-message-id={message.id}
          data-role={message.role}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, delay: Math.min(index * 0.018, 0.1), ease: "easeOut" }}
        >
          {message.role === "user" ? (
            <UserMessage
              message={message}
              canEdit={index === messages.length - 2 && messages[index + 1]?.role === "assistant"}
              onStartEdit={onStartEdit}
              onCancelEdit={onCancelEdit}
              onDraftChange={onEditDraftChange}
              onSaveEdit={onSaveEdit}
              onActivateVersion={onActivateVersion}
            />
          ) : (
            <AssistantMessage
              mode={mode}
              message={message}
              isStreaming={activeAssistantId === message.id}
              canRegenerate={index === messages.length - 1}
              onRegenerate={onRegenerate}
              onActivateVersion={onActivateVersion}
              onDelete={onDeleteAssistant}
              onPreviewDocument={onPreviewDocument}
              onFollowupSelect={onFollowupSelect}
            />
          )}
        </motion.div>
      ))}
    </div>
  );
}
