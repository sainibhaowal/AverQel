"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, Eye, Shapes } from "lucide-react";

import type { MessageArtifact } from "../_lib/stream-protocol";

import ArtifactViewer from "./ArtifactViewer";

interface ArtifactsPanelProps {
  artifacts: MessageArtifact[];
  files?: Array<{ name: string; url: string; type?: string }>;
}

export default function ArtifactsPanel({ artifacts, files = [] }: ArtifactsPanelProps) {
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null);
  const activeArtifact = artifacts.find((artifact) => artifact.id === activeArtifactId) ?? null;
  const canCreateObjectUrls = typeof URL.createObjectURL === "function";
  const artifactUrls = useMemo(() => {
    if (!canCreateObjectUrls) {
      return [];
    }

    return artifacts.map((artifact) => ({
      id: artifact.id,
      name: `${artifact.title}.${artifact.type === "svg" ? "svg" : "html"}`,
      type: artifact.type,
      url: URL.createObjectURL(
        new Blob([artifact.content], {
          type: artifact.type === "svg" ? "image/svg+xml" : "text/html",
        }),
      ),
    }));
  }, [artifacts, canCreateObjectUrls]);

  useEffect(
    () => () => {
      for (const artifact of artifactUrls) {
        URL.revokeObjectURL(artifact.url);
      }
    },
    [artifactUrls],
  );

  const generatedFiles = [
    ...files.map((file, index) => ({
      id: `file-${index}-${file.name}`,
      name: file.name,
      type: file.type ?? "file",
      url: file.url,
      previewable: false,
    })),
    ...artifactUrls.map((artifact) => ({
      id: `artifact-file-${artifact.id}`,
      name: artifact.name,
      type: artifact.type,
      url: artifact.url,
      previewable: true,
    })),
  ];

  if (artifacts.length === 0 && generatedFiles.length === 0) {
    return null;
  }

  return (
    <>
      <section className="theme-panel rounded-[1.7rem] px-4 py-4 sm:px-5">
        <div className="text-foreground/66 mb-3 flex items-center gap-2 text-[11px] font-semibold tracking-[0.18em] uppercase">
          <Shapes size={14} />
          Generated Files
        </div>
        <div className="grid gap-2.5 sm:grid-cols-2">
          {generatedFiles.map((file) => (
            <div
              key={file.id}
              className="theme-code-surface flex items-center justify-between rounded-[1.25rem] px-4 py-3"
            >
              <div className="min-w-0">
                <div className="text-foreground/42 text-[10px] tracking-[0.18em] uppercase">
                  {file.type}
                </div>
                <div className="text-foreground/84 mt-1 truncate text-sm font-medium">
                  {file.name}
                </div>
              </div>
              <div className="ml-3 flex shrink-0 items-center gap-2">
                <a
                  href={file.url}
                  download={file.name}
                  className="theme-chip text-foreground/70 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px]"
                >
                  <Download size={12} />
                  Save
                </a>
                <a
                  href={file.url}
                  target="_blank"
                  rel="noreferrer"
                  className="theme-chip text-foreground/70 hover:border-primary/40 hover:bg-primary/[0.04] hover:text-primary inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] transition-all"
                >
                  <ExternalLink size={12} />
                  Open
                </a>
              </div>
            </div>
          ))}
          {artifacts.map((artifact) => (
            <button
              key={artifact.id}
              type="button"
              onClick={() => setActiveArtifactId(artifact.id)}
              className="theme-code-surface hover:border-primary/40 hover:bg-primary/[0.04] hover:text-primary flex items-center justify-between rounded-[1.25rem] px-4 py-3 text-left transition"
            >
              <div>
                <div className="text-foreground/42 text-[10px] tracking-[0.18em] uppercase">
                  Preview
                </div>
                <div className="text-foreground/84 mt-1 text-sm font-medium">{artifact.title}</div>
              </div>
              <span className="theme-chip text-foreground/70 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px]">
                <Eye size={12} />
                Open
              </span>
            </button>
          ))}
        </div>
      </section>

      {activeArtifact ? (
        <ArtifactViewer artifact={activeArtifact} onClose={() => setActiveArtifactId(null)} />
      ) : null}
    </>
  );
}
