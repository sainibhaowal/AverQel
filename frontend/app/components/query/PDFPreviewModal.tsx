"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  Maximize2,
  Minimize2,
  Shield,
  X,
} from "lucide-react";
import {
  lazy,
  Suspense,
  useEffect,
  useMemo,
  useState,
  type MouseEvent as ReactMouseEvent,
} from "react";

import { fetchWithAuth } from "@/lib/api";
import AverQelLoading from "@/app/components/ui/AverQelLoading";
import {
  libraryFileKind,
  libraryFileSupportsServerPagePreview,
} from "@/app/dashboard/deepspace/_components/DeepSpaceLibraryFormats";

const LibraryPreview = lazy(async () => {
  const libraryModule =
    await import("@/app/dashboard/deepspace/_components/DeepSpaceLibraryPreview");
  return { default: libraryModule.LibraryPreview };
});

type PreviewMode = "page" | "format";

async function responseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as {
      error?: { message?: string };
      detail?: string;
    };
    return payload.error?.message || payload.detail || fallback;
  } catch {
    return fallback;
  }
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function safePageNumber(value?: number): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.floor(value) : 1;
}

function LoadingPreview({ label }: { label: string }) {
  return <AverQelLoading label={label} size="section" className="h-full min-h-56" />;
}

interface PDFPreviewModalProps {
  isOpen: boolean;
  documentId: string | null;
  documentName: string;
  pageNumber?: number;
  onClose: () => void;
}

export default function PDFPreviewModal({
  isOpen,
  documentId,
  documentName,
  pageNumber,
  onClose,
}: PDFPreviewModalProps) {
  const initialKind = libraryFileKind(documentName, "");
  const initialTabularContentType = documentName.toLowerCase().endsWith(".tsv")
    ? "text/tab-separated-values"
    : "text/csv";
  const initiallySupportsPageView = libraryFileSupportsServerPagePreview(documentName, "");
  const [isMaximized, setIsMaximized] = useState(false);
  const [viewMode, setViewMode] = useState<PreviewMode>(
    initiallySupportsPageView ? "page" : "format",
  );
  const [currentPage, setCurrentPage] = useState(safePageNumber(pageNumber));
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [sourceContentType, setSourceContentType] = useState(
    initialKind === "csv" ? initialTabularContentType : "",
  );
  const [sourceSizeBytes, setSourceSizeBytes] = useState<number | undefined>();
  const [documentText, setDocumentText] = useState<string | null>(
    initialKind === "csv" ? "" : null,
  );
  const [pageImageUrl, setPageImageUrl] = useState<string | null>(null);
  const [pageText, setPageText] = useState<string | null>(null);
  const [sourceLoading, setSourceLoading] = useState(initialKind !== "csv");
  const [pageLoading, setPageLoading] = useState(initiallySupportsPageView);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const inferredKind = useMemo(
    () => libraryFileKind(documentName, sourceContentType),
    [documentName, sourceContentType],
  );
  const isCsv = inferredKind === "csv";
  const inferredTabularContentType = documentName.toLowerCase().endsWith(".tsv")
    ? "text/tab-separated-values"
    : "text/csv";
  const supportsPageView = libraryFileSupportsServerPagePreview(documentName, sourceContentType);
  const csvPageUrl = isCsv && documentId ? `/documents/${documentId}/csv-page` : null;
  const hasFormatContent =
    isCsv || Boolean(sourceUrl) || documentText !== null || pageText !== null;
  const showInitialLoader =
    !hasFormatContent && !pageImageUrl && (sourceLoading || pageLoading) && !pageError;

  useEffect(() => {
    if (!isOpen || !documentId) return;

    let active = true;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    const fileKind = libraryFileKind(documentName, "");

    if (fileKind === "csv") {
      return () => {
        active = false;
      };
    }

    const loadSource = async () => {
      const [downloadResult, textResult] = await Promise.allSettled([
        fetchWithAuth(`/documents/${documentId}/download`, {
          signal: controller.signal,
          timeoutMs: 45_000,
          silentTimeout: true,
        }),
        fetchWithAuth(`/documents/${documentId}/full-text`, {
          signal: controller.signal,
          timeoutMs: 45_000,
          silentTimeout: true,
        }),
      ]);
      if (!active) return;

      const errors: string[] = [];
      if (downloadResult.status === "fulfilled" && downloadResult.value.ok) {
        const response = downloadResult.value;
        const blob = await response.blob();
        if (active) {
          const contentType = response.headers.get("content-type") || "application/octet-stream";
          objectUrl = URL.createObjectURL(blob);
          setSourceUrl(objectUrl);
          setSourceContentType(contentType);
          setSourceSizeBytes(blob.size);
          if (libraryFileSupportsServerPagePreview(documentName, contentType)) {
            setPageLoading(true);
          }
        }
      } else if (downloadResult.status === "fulfilled") {
        errors.push(
          await responseErrorMessage(downloadResult.value, "Could not load the original file."),
        );
      } else {
        errors.push(errorMessage(downloadResult.reason, "Could not load the original file."));
      }

      if (textResult.status === "fulfilled" && textResult.value.ok) {
        try {
          const payload = (await textResult.value.json()) as { content?: unknown };
          if (active) setDocumentText(typeof payload.content === "string" ? payload.content : "");
        } catch {
          errors.push("The extracted document preview could not be read.");
        }
      } else if (textResult.status === "fulfilled") {
        errors.push(
          await responseErrorMessage(textResult.value, "Could not load extracted document text."),
        );
      } else {
        errors.push(errorMessage(textResult.reason, "Could not load extracted document text."));
      }

      if (active) {
        setSourceError(errors.length ? [...new Set(errors)].join(" ") : null);
        setSourceLoading(false);
      }
    };

    void loadSource().catch((error: unknown) => {
      if (!active) return;
      setSourceError(errorMessage(error, "Could not load the secure document preview."));
      setSourceLoading(false);
    });

    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId, documentName, isOpen, reloadKey]);

  useEffect(() => {
    if (!isOpen || !documentId || !supportsPageView) return;

    let active = true;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    const loadPage = async () => {
      try {
        const response = (await fetchWithAuth(
          `/documents/${documentId}/pages/${safePageNumber(currentPage)}`,
          { signal: controller.signal, timeoutMs: 45_000, silentTimeout: true },
        )) as Response;
        if (!response.ok) {
          throw new Error(await responseErrorMessage(response, "This page could not be rendered."));
        }

        const contentType = response.headers.get("content-type") || "";
        if (contentType.startsWith("image/")) {
          const blob = await response.blob();
          if (active) {
            objectUrl = URL.createObjectURL(blob);
            setPageImageUrl(objectUrl);
          }
        } else {
          const text = await response.text();
          if (active) setPageText(text);
        }
      } catch (error) {
        if (active) setPageError(errorMessage(error, "This page could not be rendered."));
      } finally {
        if (active) setPageLoading(false);
      }
    };

    void loadPage();
    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [currentPage, documentId, isOpen, reloadKey, supportsPageView]);

  if (!isOpen || !documentId) return null;

  const formatContent = documentText ?? pageText ?? "";
  const pdfUrl = sourceUrl
    ? `${sourceUrl}${inferredKind === "pdf" ? `#page=${currentPage}` : ""}`
    : null;

  const handleOpenInNewTab = () => {
    if (pdfUrl) window.open(pdfUrl, "_blank", "noopener,noreferrer");
  };

  const handlePageClick = (event: ReactMouseEvent<HTMLButtonElement>, page: number) => {
    event.preventDefault();
    if (page >= 1 && !pageLoading) {
      setPageImageUrl(null);
      setPageText(null);
      setPageError(null);
      setPageLoading(true);
      setCurrentPage(page);
    }
  };

  const retryPreview = () => {
    setSourceUrl(null);
    setSourceContentType(initialKind === "csv" ? initialTabularContentType : "");
    setSourceSizeBytes(undefined);
    setDocumentText(initialKind === "csv" ? "" : null);
    setPageImageUrl(null);
    setPageText(null);
    setSourceError(null);
    setPageError(null);
    setSourceLoading(initialKind !== "csv");
    setPageLoading(initiallySupportsPageView);
    setReloadKey((value) => value + 1);
  };

  const hasAnyContent = hasFormatContent || Boolean(pageImageUrl);
  const errorToShow = pageError || sourceError || "No preview data is available for this file.";

  return (
    <AnimatePresence>
      <div className="pointer-events-none fixed inset-0 z-[100] flex items-center justify-end">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="pointer-events-auto absolute inset-0 bg-slate-950/35 backdrop-blur-[2px] dark:bg-slate-950/40"
        />

        <motion.div
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 25, stiffness: 200 }}
          className={`theme-panel-strong relative ${isMaximized ? "w-full" : "w-[min(92vw,1100px)]"} pointer-events-auto flex h-full flex-col border-l shadow-2xl`}
          onClick={(event: ReactMouseEvent<HTMLDivElement>) => event.stopPropagation()}
          role="dialog"
          aria-modal="true"
          aria-label={`Preview ${documentName}`}
        >
          <div className="border-glass-border bg-foreground/[0.03] flex shrink-0 items-center justify-between gap-3 border-b p-4 backdrop-blur-md dark:bg-slate-900/50">
            <div className="flex min-w-0 items-center gap-3">
              <div className="bg-primary/10 text-primary flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
                <FileText size={16} />
              </div>
              <div className="min-w-0">
                <h3 className="text-foreground truncate text-sm font-bold">{documentName}</h3>
                {pageNumber ? (
                  <p className="text-primary text-[10px] font-bold tracking-wider uppercase">
                    Cited on page {pageNumber}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => setIsMaximized((value) => !value)}
                aria-label={isMaximized ? "Restore preview size" : "Maximize preview"}
                title={isMaximized ? "Restore preview size" : "Maximize preview"}
                className="text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg p-2 transition-all"
              >
                {isMaximized ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
              </button>
              <button
                type="button"
                onClick={handleOpenInNewTab}
                disabled={!pdfUrl}
                aria-label="Open original file in a new tab"
                title="Open Original File"
                className="text-muted-foreground hover:bg-muted hover:text-primary rounded-lg p-2 transition-all disabled:opacity-40"
              >
                <ExternalLink size={16} />
              </button>
              <div className="bg-foreground/10 dark:bg-glass-border mx-1 h-4 w-px" />
              <button
                type="button"
                onClick={onClose}
                aria-label="Close document preview"
                title="Close"
                className="text-muted-foreground hover:bg-muted rounded-lg p-2 transition-all hover:text-red-400"
              >
                <X size={20} />
              </button>
            </div>
          </div>

          {supportsPageView ? (
            <div className="border-glass-border flex shrink-0 items-center gap-2 border-b px-4 py-2">
              <button
                type="button"
                onClick={() => setViewMode("page")}
                aria-pressed={viewMode === "page"}
                className={`rounded-md px-3 py-1.5 text-[10px] font-bold tracking-wider uppercase transition ${viewMode === "page" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-muted"}`}
              >
                Page view
              </button>
              <button
                type="button"
                onClick={() => setViewMode("format")}
                aria-pressed={viewMode === "format"}
                className={`rounded-md px-3 py-1.5 text-[10px] font-bold tracking-wider uppercase transition ${viewMode === "format" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-muted"}`}
              >
                Full format preview
              </button>
            </div>
          ) : null}

          <div className="bg-foreground/[0.03] relative min-h-0 flex-1 overflow-hidden dark:bg-slate-800/50">
            {showInitialLoader ? (
              <div className="bg-background/95 absolute inset-0 z-10 dark:bg-slate-900/80">
                <LoadingPreview label="Loading secure document preview…" />
              </div>
            ) : null}

            {!hasAnyContent && !showInitialLoader ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
                <AlertCircle size={26} className="text-danger" />
                <p className="text-foreground/75 max-w-lg text-sm">{errorToShow}</p>
                <button
                  type="button"
                  onClick={retryPreview}
                  className="text-primary rounded-lg border border-current/20 px-3 py-2 text-xs font-semibold"
                >
                  Retry preview
                </button>
              </div>
            ) : null}

            {hasAnyContent && viewMode === "page" && supportsPageView ? (
              <div className="flex h-full min-h-0 flex-col">
                <div className="border-glass-border flex shrink-0 items-center justify-between border-b px-3 py-2 text-xs">
                  <button
                    type="button"
                    disabled={currentPage <= 1 || pageLoading}
                    onClick={(event) => handlePageClick(event, currentPage - 1)}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 disabled:opacity-40"
                  >
                    <ChevronLeft size={14} /> Previous
                  </button>
                  <span className="text-foreground/65 font-semibold">
                    Page {currentPage}
                    {pageLoading ? (
                      <AverQelLoading size="inline" label="Loading next preview page" />
                    ) : null}
                  </span>
                  <button
                    type="button"
                    disabled={pageLoading || Boolean(pageError)}
                    onClick={(event) => handlePageClick(event, currentPage + 1)}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 disabled:opacity-40"
                  >
                    Next <ChevronRight size={14} />
                  </button>
                </div>
                <div className="custom-scrollbar relative min-h-0 flex-1 overflow-auto p-4">
                  {pageLoading && !pageImageUrl && pageText === null ? (
                    <LoadingPreview label="Rendering page securely…" />
                  ) : pageImageUrl ? (
                    // The authenticated server returns a page image for PDFs and
                    // LibreOffice-supported Office formats; source blobs stay private.
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={pageImageUrl}
                      alt={`${documentName}, page ${currentPage}`}
                      className="mx-auto max-h-full max-w-full rounded-lg object-contain shadow-xl"
                    />
                  ) : pageText !== null ? (
                    <div className="flex h-full min-h-0 flex-col">
                      <p
                        role="status"
                        className="border-primary/20 bg-primary/5 text-muted-foreground mb-3 shrink-0 rounded-lg border px-3 py-2 text-xs"
                      >
                        A visual page preview is unavailable. Showing extracted document content.
                      </p>
                      <Suspense fallback={<LoadingPreview label="Preparing format preview…" />}>
                        <LibraryPreview
                          kind={inferredKind}
                          contentType={sourceContentType || "text/plain"}
                          value={pageText}
                          previewUrl={sourceUrl}
                          sizeBytes={sourceSizeBytes}
                        />
                      </Suspense>
                    </div>
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
                      <AlertCircle size={24} className="text-muted-foreground" />
                      <p className="text-muted-foreground max-w-lg text-sm">
                        {pageError || "This page is not available as a visual preview."}
                      </p>
                      <button
                        type="button"
                        onClick={retryPreview}
                        className="text-primary rounded-lg border border-current/20 px-3 py-2 text-xs font-semibold"
                      >
                        Retry page preview
                      </button>
                      <button
                        type="button"
                        onClick={() => setViewMode("format")}
                        className="text-muted-foreground rounded-lg border border-current/20 px-3 py-2 text-xs font-semibold"
                      >
                        Open full format preview
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            {hasAnyContent && (viewMode === "format" || !supportsPageView) ? (
              <div className="h-full min-h-0 overflow-auto p-3 sm:p-5">
                {pageError && supportsPageView ? (
                  <p className="border-primary/20 bg-primary/5 text-muted-foreground mb-3 rounded-lg border px-3 py-2 text-xs">
                    The visual page preview is unavailable. Showing the available format preview.
                  </p>
                ) : null}
                {sourceError && !sourceUrl && documentText !== null ? (
                  <p className="border-primary/20 bg-primary/5 text-muted-foreground mb-3 rounded-lg border px-3 py-2 text-xs">
                    The original file could not be loaded. Showing extracted content instead.
                  </p>
                ) : null}
                <Suspense fallback={<LoadingPreview label="Preparing format preview…" />}>
                  <LibraryPreview
                    kind={inferredKind}
                    contentType={
                      sourceContentType || (isCsv ? inferredTabularContentType : "text/plain")
                    }
                    value={formatContent}
                    previewUrl={sourceUrl}
                    sizeBytes={sourceSizeBytes}
                    csvPageUrl={csvPageUrl}
                  />
                </Suspense>
              </div>
            ) : null}
          </div>

          <div className="border-glass-border bg-foreground/[0.03] flex shrink-0 items-center justify-between border-t p-3 dark:bg-slate-900/80">
            <div className="text-muted-foreground flex items-center gap-2 text-[10px] italic">
              <Shield size={12} className="text-primary/50" />
              <span>Strictly confidential • Enterprise analysis workspace</span>
            </div>
            <span className="border-glass-border bg-muted text-muted-foreground rounded-full border px-2 py-0.5 font-mono text-[9px]">
              ID: {documentId.substring(0, 8)}
            </span>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
