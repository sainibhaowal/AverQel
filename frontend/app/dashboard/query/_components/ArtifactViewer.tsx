"use client";

import { X } from "lucide-react";

import type { MessageArtifact } from "../_lib/stream-protocol";

interface ArtifactViewerProps {
  artifact: MessageArtifact;
  onClose: () => void;
}

export default function ArtifactViewer({ artifact, onClose }: ArtifactViewerProps) {
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-md">
      <div className="theme-panel flex h-[85vh] w-full max-w-6xl flex-col overflow-hidden rounded-[2rem]">
        <div className="border-glass-border/40 flex items-center justify-between border-b px-5 py-4">
          <div>
            <div className="text-foreground/45 text-[11px] tracking-[0.2em] uppercase">
              {artifact.language}
            </div>
            <h3 className="text-foreground mt-1 text-lg font-semibold">{artifact.title}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="theme-chip text-foreground/72 inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm"
          >
            <X size={16} />
            Close
          </button>
        </div>

        <div className="min-h-0 flex-1 bg-white dark:bg-slate-950">
          {artifact.type === "svg" ? (
            <div
              className="h-full overflow-auto p-6 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
              dangerouslySetInnerHTML={{ __html: artifact.content }}
            />
          ) : (
            <iframe
              title={artifact.title}
              className="h-full w-full border-0 bg-white"
              sandbox="allow-scripts"
              srcDoc={artifact.content}
            />
          )}
        </div>
      </div>
    </div>
  );
}
