"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Download, FileText, Loader2, ShieldCheck } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";

interface SharedDocument {
  document_id: string;
  filename: string;
  content_type: string;
  expires_at: string;
  content: string;
}

export default function SharedDocumentClient() {
  const params = useParams<{ link_id: string }>();
  const search = useSearchParams();
  const [sharedDocument, setSharedDocument] = useState<SharedDocument | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewPage, setPreviewPage] = useState(1);
  const [previewHasNext, setPreviewHasNext] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [showText, setShowText] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPreviewPage = async (page: number, linkId: string, shareToken: string) => {
    if (page < 1) return;
    setPreviewLoading(true);
    try {
      const response = await fetch(
        `${getApiBaseUrl()}/documents/share-links/${encodeURIComponent(linkId)}/pages/${page}?token=${encodeURIComponent(shareToken)}`,
      );
      if (!response.ok || !response.headers.get("content-type")?.startsWith("image/")) {
        if (page > 1) setPreviewHasNext(false);
        return;
      }
      const nextUrl = URL.createObjectURL(await response.blob());
      setPreviewUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return nextUrl;
      });
      setPreviewPage(page);
      setPreviewHasNext(true);
    } finally {
      setPreviewLoading(false);
    }
  };

  useEffect(() => {
    const token = search.get("token");
    if (!params?.link_id || !token) {
      queueMicrotask(() => setError("This share link is incomplete."));
      return;
    }
    fetch(
      `${getApiBaseUrl()}/documents/share-links/${encodeURIComponent(params.link_id)}/resolve?token=${encodeURIComponent(token)}`,
    )
      .then(async (response) => {
        if (!response.ok) throw new Error("This share link is invalid or expired.");
        return response.json() as Promise<SharedDocument>;
      })
      .then(async (document) => {
        setSharedDocument(document);
        await loadPreviewPage(1, params.link_id, token);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Unable to open shared document."),
      );
    return () => {
      setPreviewUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return null;
      });
    };
  }, [params?.link_id, search]);

  const token = search.get("token");
  const downloadUrl = token
    ? `${getApiBaseUrl()}/documents/share-links/${encodeURIComponent(params.link_id)}/download?token=${encodeURIComponent(token)}`
    : null;

  return (
    <main className="bg-background text-foreground min-h-screen p-6 sm:p-12">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="glass-card flex items-center gap-3 p-5">
          <FileText className="text-primary" />
          <div>
            <h1 className="font-black">Shared document</h1>
            <p className="text-foreground/50 text-xs">Read-only secure link</p>
          </div>
          <ShieldCheck className="ml-auto text-emerald-500" size={18} />
        </div>
        {error ? (
          <div className="glass-card text-danger p-8 text-center text-sm">{error}</div>
        ) : sharedDocument ? (
          <article className="glass-card space-y-5 p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-black">{sharedDocument.filename}</h2>
                <p className="text-foreground/45 mt-1 text-xs">
                  Link expires {new Date(sharedDocument.expires_at).toLocaleString()}
                </p>
              </div>
              {downloadUrl ? (
                <a
                  href={downloadUrl}
                  download={sharedDocument.filename}
                  className="bg-primary text-primary-foreground inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold"
                >
                  <Download size={14} /> Download source
                </a>
              ) : null}
            </div>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {previewUrl ? (
                  <button
                    type="button"
                    onClick={() => setShowText(false)}
                    className={`rounded-lg px-3 py-2 text-xs font-bold ${!showText ? "bg-primary text-white" : "bg-foreground/5"}`}
                  >
                    Visual preview
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => setShowText(true)}
                  className={`rounded-lg px-3 py-2 text-xs font-bold ${showText || !previewUrl ? "bg-primary text-white" : "bg-foreground/5"}`}
                >
                  Extracted text
                </button>
              </div>
              {previewUrl ? (
                <span className="text-foreground/50 text-xs">Page {previewPage}</span>
              ) : null}
            </div>
            {showText || !previewUrl ? (
              <div className="border-glass-border/60 max-h-[70vh] overflow-auto border-t pt-6">
                <pre className="text-sm leading-7 whitespace-pre-wrap">
                  {sharedDocument.content ||
                    "No text could be extracted. Use Download source to open the original file."}
                </pre>
              </div>
            ) : (
              <div className="border-glass-border/60 max-h-[70vh] overflow-auto border-t pt-6 text-center">
                <div className="flex items-center justify-between pb-3">
                  <button
                    type="button"
                    disabled={previewLoading || previewPage <= 1}
                    onClick={() => {
                      if (token) void loadPreviewPage(previewPage - 1, params.link_id, token);
                    }}
                    className="bg-foreground/5 rounded-lg px-3 py-2 text-xs font-bold disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={previewLoading || !previewHasNext}
                    onClick={() => {
                      if (token) void loadPreviewPage(previewPage + 1, params.link_id, token);
                    }}
                    className="bg-foreground/5 rounded-lg px-3 py-2 text-xs font-bold disabled:opacity-40"
                  >
                    {previewLoading ? "Loading…" : "Next"}
                  </button>
                </div>
                {/* Only rendered page bytes are exposed; the original stays private. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={previewUrl}
                  alt={`${sharedDocument.filename} page ${previewPage}`}
                  className="mx-auto max-w-full rounded-lg shadow-lg"
                />
              </div>
            )}
          </article>
        ) : (
          <div className="flex justify-center p-16">
            <Loader2 className="text-primary animate-spin" />
          </div>
        )}
      </div>
    </main>
  );
}
