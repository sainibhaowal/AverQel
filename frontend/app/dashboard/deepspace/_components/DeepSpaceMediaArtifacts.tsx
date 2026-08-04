"use client";

import { Download, Image as ImageIcon, Loader2, Music2, PlaySquare, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { fetchWithAuth } from "@/lib/api";

import type { DeepSpaceMediaArtifact } from "../_lib/deepspace-stream";

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "Private artifact";
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ArtifactSource({ artifact }: { artifact: DeepSpaceMediaArtifact }) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    let nextObjectUrl: string | null = null;
    setObjectUrl(null);
    setError(false);
    void (async () => {
      try {
        const response = (await fetchWithAuth(artifact.url, { timeoutMs: 30_000 })) as Response;
        if (!response.ok) throw new Error("Artifact delivery failed");
        const blob = await response.blob();
        nextObjectUrl = URL.createObjectURL(blob);
        if (active) setObjectUrl(nextObjectUrl);
      } catch {
        if (active) setError(true);
      }
    })();
    return () => {
      active = false;
      if (nextObjectUrl) URL.revokeObjectURL(nextObjectUrl);
    };
  }, [artifact.url]);

  if (!objectUrl && !error) {
    return (
      <div className="text-foreground/45 flex h-44 items-center justify-center text-xs">
        <Loader2 size={16} className="mr-2 animate-spin text-cyan-300" /> Preparing private media…
      </div>
    );
  }
  if (error || !objectUrl) {
    return (
      <div className="flex h-32 items-center justify-center px-4 text-center text-xs text-rose-200/80">
        This artifact could not be loaded. Your private media remains protected; retry the message
        or refresh the workspace.
      </div>
    );
  }
  if (artifact.kind === "image") {
    return (
      // Private authenticated blobs cannot use the Next image optimizer without
      // exposing a public loader URL; render the already-authorized object URL.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={objectUrl}
        alt={artifact.title}
        className="max-h-[36rem] w-full rounded-lg object-contain"
      />
    );
  }
  if (artifact.kind === "video") {
    return (
      <video
        src={objectUrl}
        controls
        preload="metadata"
        className="max-h-[34rem] w-full rounded-lg bg-black"
      />
    );
  }
  return <AudioPreview source={objectUrl} />;
}

function AudioPreview({ source }: { source: string }) {
  const waveform = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = waveform.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    let active = true;
    void (async () => {
      try {
        const response = await fetch(source);
        const bytes = await response.arrayBuffer();
        const AudioContextClass =
          window.AudioContext ||
          (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!AudioContextClass) return;
        const audioContext = new AudioContextClass();
        const decoded = await audioContext.decodeAudioData(bytes.slice(0));
        await audioContext.close();
        if (!active) return;
        const samples = decoded.getChannelData(0);
        const width = Math.max(1, canvas.clientWidth || 480);
        const height = 44;
        canvas.width = width * window.devicePixelRatio;
        canvas.height = height * window.devicePixelRatio;
        context.scale(window.devicePixelRatio, window.devicePixelRatio);
        context.clearRect(0, 0, width, height);
        context.fillStyle = "rgba(34, 211, 238, 0.72)";
        const block = Math.max(1, Math.floor(samples.length / width));
        for (let x = 0; x < width; x += 1) {
          let peak = 0;
          for (let offset = 0; offset < block; offset += 1) {
            peak = Math.max(peak, Math.abs(samples[x * block + offset] || 0));
          }
          const bar = Math.max(1, peak * height);
          context.fillRect(x, (height - bar) / 2, 1, bar);
        }
      } catch {
        // Browsers can decline to decode an unfamiliar audio codec. Playback
        // remains available through the native control in that case.
      }
    })();
    return () => {
      active = false;
    };
  }, [source]);

  return (
    <div className="space-y-3">
      <canvas
        ref={waveform}
        aria-label="Audio waveform"
        className="h-11 w-full rounded-md bg-cyan-300/[0.05]"
      />
      <audio src={source} controls preload="metadata" className="w-full" />
    </div>
  );
}

export default function DeepSpaceMediaArtifacts({
  artifacts,
}: {
  artifacts?: DeepSpaceMediaArtifact[];
}) {
  if (!artifacts?.length) return null;
  const download = async (artifact: DeepSpaceMediaArtifact) => {
    const response = (await fetchWithAuth(artifact.url, { timeoutMs: 30_000 })) as Response;
    if (!response.ok) return;
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `${artifact.title}.${artifact.content_type.split("/")[1] || "media"}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  };
  return (
    <div className="mt-4 grid gap-3">
      {artifacts.map((artifact) => {
        const Icon =
          artifact.kind === "image" ? ImageIcon : artifact.kind === "video" ? PlaySquare : Music2;
        return (
          <section
            key={artifact.id}
            className="overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#091510]/80 shadow-[0_18px_45px_-30px_rgba(34,211,238,0.65)]"
          >
            <header className="flex items-center justify-between gap-3 border-b border-white/10 px-3 py-2.5">
              <div className="flex min-w-0 items-center gap-2">
                <Icon size={15} className="shrink-0 text-cyan-300" />
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold text-cyan-50">
                    {artifact.title}
                  </div>
                  <div className="text-foreground/45 mt-0.5 text-[10px]">
                    {artifact.kind} · {formatBytes(artifact.size_bytes)} · private
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => void download(artifact)}
                className="text-foreground/70 inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 px-2 py-1.5 text-[10px] font-semibold hover:border-cyan-300/35 hover:text-cyan-100"
              >
                <Download size={12} /> Download
              </button>
            </header>
            <div className="p-3">
              <ArtifactSource artifact={artifact} />
            </div>
            <footer className="text-foreground/45 flex items-center gap-1.5 border-t border-white/10 px-3 py-2 text-[10px]">
              <RefreshCw size={11} /> Regenerate by asking DeepSpace to generate another variation.
            </footer>
          </section>
        );
      })}
    </div>
  );
}
