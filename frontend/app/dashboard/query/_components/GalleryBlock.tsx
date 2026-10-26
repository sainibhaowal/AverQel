"use client";

import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Download,
  ExternalLink,
  Pencil,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchWithAuth } from "@/lib/api";
import { downloadBlob } from "@/lib/client-export";

export interface GalleryItem {
  src: string;
  alt: string;
  caption?: string | null;
  href?: string | null;
}

export interface GalleryAssetRef {
  url: string;
  owned_url?: string | null;
  mime_type?: string | null;
  status?: string;
  file_id?: string | null;
  retention?: "temporary" | "library";
}

export type GalleryAssetRetention = "temporary" | "library";

export interface GalleryPayload {
  id?: string;
  block_id?: string;
  type?: "gallery";
  schema_version?: number;
  revision?: number;
  source_markdown?: string | null;
  assets?: Array<{
    url: string;
    owned_url?: string | null;
    mime_type?: string | null;
    status?: string;
    file_id?: string | null;
    retention?: "temporary" | "library";
  }>;
  history?: Array<{ revision: number; source: string; actor?: string | null; at?: string | null }>;
  undo?: Record<string, unknown>;
  title?: string | null;
  items: GalleryItem[];
}

export default function GalleryBlock({
  payload,
  onChange,
  onSaveArtifact,
  onImportAsset,
  onRetainAsset,
}: {
  payload: GalleryPayload;
  onChange?: (payload: GalleryPayload) => void | Promise<void>;
  onSaveArtifact?: (payload: GalleryPayload) => void | Promise<void>;
  onImportAsset?: (url: string, retention: GalleryAssetRetention) => Promise<GalleryAssetRef>;
  onRetainAsset?: (fileId: string) => Promise<GalleryAssetRef>;
}) {
  const items = useMemo(
    () => payload.items.filter((item) => Boolean(safeExternalHref(item.src))),
    [payload.items],
  );
  const [index, setIndex] = useState(0);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<GalleryPayload>(payload);
  const [failedImageSrc, setFailedImageSrc] = useState<string | null>(null);
  const [ownedPreview, setOwnedPreview] = useState<{ source: string; url: string } | null>(null);
  const [assetStatus, setAssetStatus] = useState<{ source: string; text: string } | null>(null);
  const [importing, setImporting] = useState(false);
  const attemptedImports = useRef(new Set<string>());
  const attemptedRecovery = useRef(new Set<string>());
  const payloadRef = useRef(payload);
  const onChangeRef = useRef(onChange);
  const onImportAssetRef = useRef(onImportAsset);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [artifactSaving, setArtifactSaving] = useState(false);
  const [artifactSaved, setArtifactSaved] = useState(false);
  const item = items[Math.min(index, items.length - 1)] ?? { src: "", alt: "Gallery image" };
  const src = safeExternalHref(item.src);
  const open = safeExternalHref(item.href ?? item.src);
  const activeAsset = payload.assets?.find((asset) => asset.url === item.src && asset.owned_url);
  const ownedPreviewUrl =
    ownedPreview && activeAsset && ownedPreview.source === activeAsset.owned_url
      ? ownedPreview.url
      : null;
  const displayImageSrc = ownedPreviewUrl ?? src;
  const imageFailed = failedImageSrc === displayImageSrc;
  const currentAssetStatus =
    assetStatus?.source === item.src
      ? assetStatus.text
      : items.length > 24
        ? "Large gallery: caching the current image first."
        : null;

  useEffect(() => {
    payloadRef.current = payload;
    onChangeRef.current = onChange;
    onImportAssetRef.current = onImportAsset;
  }, [onChange, onImportAsset, payload]);

  const appendAsset = useCallback(async (asset: GalleryAssetRef) => {
    const current = payloadRef.current;
    const existing = current.assets?.find((candidate) => candidate.url === asset.url);
    const next = {
      ...current,
      assets: [
        ...(current.assets ?? []).filter((candidate) => candidate.url !== asset.url),
        { ...existing, ...asset },
      ],
      revision: (current.revision ?? 0) + 1,
      history: [
        ...(current.history ?? []),
        {
          revision: (current.revision ?? 0) + 1,
          source: "gallery-asset",
          at: new Date().toISOString(),
        },
      ],
    };
    payloadRef.current = next;
    try {
      await onChangeRef.current?.(next);
    } catch (error) {
      if (payloadRef.current === next) payloadRef.current = current;
      throw error;
    }
  }, []);
  const importImage = useCallback(
    async (url: string, retention: GalleryAssetRetention = "temporary") => {
      const importAsset = onImportAssetRef.current;
      if (!importAsset) return;
      setImporting(true);
      setAssetStatus({
        source: url,
        text: retention === "temporary" ? "Making a reliable chat copy…" : "Saving to Library…",
      });
      setSaveError(null);
      try {
        const asset = await importAsset(url, retention);
        await appendAsset(asset);
        setAssetStatus({
          source: url,
          text:
            retention === "library"
              ? "Saved to Library."
              : "Cached for this chat. Save to Library to keep it longer.",
        });
      } catch (error) {
        setAssetStatus({ source: url, text: "" });
        setSaveError(error instanceof Error ? error.message : "This image could not be imported.");
      } finally {
        setImporting(false);
      }
    },
    [appendAsset],
  );

  useEffect(() => {
    if (!activeAsset?.owned_url) {
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    void (async () => {
      try {
        const response = (await fetchWithAuth(activeAsset.owned_url!, {
          timeoutMs: 20_000,
        })) as Response;
        if (!response.ok) throw new Error("The owned image is unavailable.");
        const blob = await response.blob();
        if (!blob.type.toLowerCase().startsWith("image/")) {
          throw new Error("The saved file is not an image.");
        }
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) setOwnedPreview({ source: activeAsset.owned_url!, url: objectUrl });
      } catch {
        if (!cancelled) {
          setOwnedPreview(null);
          setAssetStatus({
            source: item.src,
            text: "The cached image expired or could not be loaded. Retrying the source…",
          });
          const originalUrl = safeExternalHref(item.src);
          if (
            originalUrl?.startsWith("http") &&
            onImportAssetRef.current &&
            onChangeRef.current &&
            !attemptedRecovery.current.has(originalUrl)
          ) {
            attemptedRecovery.current.add(originalUrl);
            const current = payloadRef.current;
            const next = {
              ...current,
              assets: (current.assets ?? []).filter((asset) => asset.url !== originalUrl),
              revision: (current.revision ?? 0) + 1,
              history: [
                ...(current.history ?? []),
                {
                  revision: (current.revision ?? 0) + 1,
                  source: "gallery-asset-recovery",
                  at: new Date().toISOString(),
                },
              ],
            };
            payloadRef.current = next;
            try {
              await onChangeRef.current(next);
              attemptedImports.current.delete(originalUrl);
              await importImage(originalUrl);
            } catch {
              setSaveError("The cached image could not be refreshed. Retry the image import.");
            }
          }
        }
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl && typeof URL.revokeObjectURL === "function") {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [activeAsset?.owned_url, importImage, item.src]);

  useEffect(() => {
    if (!onImportAssetRef.current || !onChangeRef.current) return;
    const missingAssets = items
      .map((galleryItem) => safeExternalHref(galleryItem.src))
      .filter((url): url is string => Boolean(url?.startsWith("http")))
      .filter(
        (url) =>
          !payload.assets?.some((asset) => asset.url === url && asset.owned_url) &&
          !attemptedImports.current.has(url),
      );
    if (items.length > 24) {
      const currentUrl = safeExternalHref(item.src);
      missingAssets.sort(
        (left, right) => Number(right === currentUrl) - Number(left === currentUrl),
      );
      missingAssets.splice(1);
    }
    let cancelled = false;
    void (async () => {
      for (const url of missingAssets) {
        if (cancelled) return;
        attemptedImports.current.add(url);
        await importImage(url);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [importImage, item.src, items, payload.assets]);

  const downloadCurrentImage = async () => {
    if (activeAsset?.owned_url) {
      try {
        const response = (await fetchWithAuth(activeAsset.owned_url, {
          timeoutMs: 20_000,
        })) as Response;
        if (!response.ok) throw new Error("The image download failed.");
        const blob = await response.blob();
        const extensions: Record<string, string> = {
          "image/avif": "avif",
          "image/gif": "gif",
          "image/jpeg": "jpg",
          "image/png": "png",
          "image/webp": "webp",
        };
        downloadBlob(
          blob,
          `${safeFilename(item.alt) || "gallery-image"}.${extensions[blob.type] ?? "img"}`,
        );
      } catch (error) {
        setSaveError(error instanceof Error ? error.message : "The image could not be downloaded.");
      }
      return;
    }
    const anchor = document.createElement("a");
    if (!src) return;
    anchor.href = src;
    anchor.download = safeFilename(item.alt) || "gallery-image";
    anchor.target = "_blank";
    anchor.rel = "noreferrer noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  };

  const retainCurrentImage = async () => {
    const fileId = activeAsset?.file_id ?? getFileId(activeAsset?.owned_url);
    if (!fileId || !onRetainAsset || !activeAsset) return;
    setSaveError(null);
    try {
      const retained = await onRetainAsset(fileId);
      await appendAsset({
        ...activeAsset,
        ...retained,
        url: activeAsset.url,
        retention: "library",
      });
      setAssetStatus({ source: item.src, text: "Saved to Library." });
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "The image could not be saved.");
    }
  };
  const commit = async (): Promise<GalleryPayload | null> => {
    const next = {
      ...draft,
      id: draft.id ?? payload.id,
      block_id: draft.block_id ?? payload.block_id ?? payload.id,
      type: "gallery" as const,
      schema_version: draft.schema_version ?? payload.schema_version ?? 1,
      revision: (payload.revision ?? 0) + 1,
      history: [
        ...(payload.history ?? []),
        {
          revision: (payload.revision ?? 0) + 1,
          source: "gallery-editor",
          at: new Date().toISOString(),
        },
      ],
    };
    setSaveError(null);
    try {
      await onChange?.(next);
      setEditing(false);
      return next;
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "The gallery could not be saved.");
      return null;
    }
  };
  const saveArtifact = async () => {
    if (!onSaveArtifact || artifactSaving) return;
    setArtifactSaving(true);
    setArtifactSaved(false);
    setSaveError(null);
    try {
      const artifact = editing ? await commit() : payload;
      if (!artifact) return;
      await onSaveArtifact(artifact);
      setArtifactSaved(true);
    } catch (error) {
      setSaveError(
        error instanceof Error ? error.message : "The gallery could not be saved to Library.",
      );
    } finally {
      setArtifactSaving(false);
    }
  };
  const updateItem = (itemIndex: number, key: keyof GalleryItem, value: string) =>
    setDraft((current) => ({
      ...current,
      items: current.items.map((candidate, candidateIndex) =>
        candidateIndex === itemIndex ? { ...candidate, [key]: value } : candidate,
      ),
    }));
  const moveItem = (itemIndex: number, direction: -1 | 1) =>
    setDraft((current) => {
      const nextIndex = itemIndex + direction;
      if (nextIndex < 0 || nextIndex >= current.items.length) return current;
      const next = [...current.items];
      const item = next[itemIndex];
      next[itemIndex] = next[nextIndex]!;
      next[nextIndex] = item!;
      return { ...current, items: next };
    });
  if (!items.length && !editing) return null;
  return (
    <section
      className="theme-panel overflow-hidden rounded-[1.6rem] border border-black/5 p-4 shadow-sm dark:border-white/8"
      aria-label={payload.title ?? "Image gallery"}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-foreground text-sm font-semibold">{payload.title ?? "Gallery"}</h3>
          <p className="text-foreground/50 mt-0.5 text-[11px]">
            {index + 1} of {items.length}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {onChange ? (
            <button
              type="button"
              onClick={() => {
                if (editing) void commit();
                else {
                  setSaveError(null);
                  setArtifactSaved(false);
                  setDraft(payload);
                  setEditing(true);
                }
              }}
              disabled={artifactSaving}
              className="theme-chip inline-flex items-center gap-1 rounded-lg px-2.5 py-2 text-[11px]"
              aria-label={editing ? "Save gallery" : "Edit gallery"}
            >
              {editing ? <Save size={14} /> : <Pencil size={14} />}
            </button>
          ) : null}
          {onSaveArtifact ? (
            <button
              type="button"
              onClick={() => void saveArtifact()}
              disabled={artifactSaving}
              aria-busy={artifactSaving}
              aria-label="Save gallery to Library"
              className="theme-chip rounded-lg px-2.5 py-2 text-[11px] disabled:opacity-50"
            >
              {artifactSaving ? "Saving…" : artifactSaved ? "Saved" : "Save"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void downloadCurrentImage()}
            className="theme-chip rounded-lg p-2"
            aria-label="Download image"
            disabled={importing}
          >
            <Download size={14} />
          </button>
          {open ? (
            <a
              href={open}
              target="_blank"
              rel="noreferrer noopener"
              className="theme-chip rounded-lg p-2"
              aria-label="Open image"
            >
              <ExternalLink size={14} />
            </a>
          ) : null}
        </div>
      </div>
      {editing ? (
        <div className="mb-4 space-y-3 rounded-xl border border-white/10 bg-black/10 p-3">
          <input
            value={draft.title ?? ""}
            onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
            aria-label="Gallery title"
            placeholder="Gallery title"
            className="border-glass-border bg-background/60 w-full rounded-lg border px-2.5 py-2 text-xs"
          />
          {draft.items.map((draftItem, itemIndex) => (
            <div
              key={`${draftItem.src}-${itemIndex}`}
              className="space-y-2 rounded-lg border border-white/10 p-2"
            >
              {(["src", "alt", "caption", "href"] as const).map((key) => (
                <input
                  key={key}
                  value={draftItem[key] ?? ""}
                  onChange={(event) => updateItem(itemIndex, key, event.target.value)}
                  aria-label={`Gallery image ${itemIndex + 1} ${key}`}
                  placeholder={key}
                  className="border-glass-border bg-background/60 w-full rounded-lg border px-2 py-1.5 text-xs"
                />
              ))}
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => moveItem(itemIndex, -1)}
                  className="theme-chip rounded p-1"
                  aria-label="Move image earlier"
                >
                  <ChevronUp size={13} />
                </button>
                <button
                  type="button"
                  onClick={() => moveItem(itemIndex, 1)}
                  className="theme-chip rounded p-1"
                  aria-label="Move image later"
                >
                  <ChevronDown size={13} />
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      items: current.items.filter(
                        (_, candidateIndex) => candidateIndex !== itemIndex,
                      ),
                    }))
                  }
                  disabled={draft.items.length < 2}
                  className="theme-chip rounded p-1 text-rose-300 disabled:opacity-40"
                  aria-label="Remove image"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              setDraft((current) => ({
                ...current,
                items: [...current.items, { src: "https://", alt: "Gallery image" }],
              }))
            }
            className="theme-chip inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs"
          >
            <Plus size={13} /> Add image
          </button>
        </div>
      ) : null}
      {saveError ? (
        <p className="mb-2 text-xs text-rose-400" role="alert">
          {saveError}
        </p>
      ) : null}
      {artifactSaved ? (
        <p
          className="mb-2 text-xs text-emerald-700 dark:text-emerald-300"
          role="status"
          aria-live="polite"
        >
          Saved to Library.
        </p>
      ) : null}
      <div className="relative overflow-hidden rounded-2xl border border-black/5 bg-black/10 dark:border-white/8">
        {imageFailed ? (
          <div className="text-foreground/60 flex min-h-44 items-center justify-center px-4 text-center text-xs">
            This image is unavailable. Import it into the DeepSpace Library or update its URL.
          </div>
        ) : displayImageSrc ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={displayImageSrc}
            alt={item.alt}
            loading="lazy"
            decoding="async"
            className="max-h-[28rem] min-h-44 w-full object-contain"
            onError={() => setFailedImageSrc(displayImageSrc)}
            onLoad={() => setFailedImageSrc(null)}
          />
        ) : (
          <div className="text-foreground/60 flex min-h-44 items-center justify-center px-4 text-center text-xs">
            Add a valid HTTP(S) image URL or import an image into the Library.
          </div>
        )}
        {items.length > 1 ? (
          <>
            <button
              type="button"
              onClick={() => setIndex((current) => (current - 1 + items.length) % items.length)}
              className="absolute top-1/2 left-3 -translate-y-1/2 rounded-lg bg-black/55 p-2 text-white"
              aria-label="Previous image"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              onClick={() => setIndex((current) => (current + 1) % items.length)}
              className="absolute top-1/2 right-3 -translate-y-1/2 rounded-lg bg-black/55 p-2 text-white"
              aria-label="Next image"
            >
              <ChevronRight size={16} />
            </button>
          </>
        ) : null}
      </div>
      {currentAssetStatus ? (
        <p className="text-foreground/55 mt-2 text-[11px]" role="status" aria-live="polite">
          {currentAssetStatus}
        </p>
      ) : null}
      {activeAsset?.retention === "temporary" && activeAsset.file_id && onRetainAsset ? (
        <button
          type="button"
          onClick={() => void retainCurrentImage()}
          className="theme-chip mt-2 rounded-lg px-2.5 py-1.5 text-[11px]"
        >
          Save image to Library
        </button>
      ) : null}
      {saveError && onImportAsset && !activeAsset?.owned_url ? (
        <button
          type="button"
          disabled={importing}
          onClick={() => {
            attemptedImports.current.delete(item.src);
            void importImage(item.src);
          }}
          className="theme-chip mt-2 rounded-lg px-2.5 py-1.5 text-[11px]"
        >
          Retry image import
        </button>
      ) : null}
      {item.caption ? (
        <p className="text-foreground/65 mt-3 text-xs leading-5">{item.caption}</p>
      ) : null}
      {items.length > 1 ? (
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
          {items.map((thumb, thumbIndex) => (
            <button
              type="button"
              key={`${thumb.src}-${thumbIndex}`}
              onClick={() => setIndex(thumbIndex)}
              className={`h-12 w-16 shrink-0 overflow-hidden rounded-lg border ${thumbIndex === index ? "border-primary" : "border-black/10 dark:border-white/10"}`}
              aria-label={`Show image ${thumbIndex + 1}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={safeExternalHref(thumb.src)}
                alt=""
                className="h-full w-full object-cover"
                onError={(event) => {
                  event.currentTarget.style.display = "none";
                }}
              />
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function parseGalleryPayload(source: string): GalleryPayload | null {
  try {
    const payload = JSON.parse(source) as Record<string, unknown>;
    if (!payload || Array.isArray(payload) || !Array.isArray(payload.items)) return null;
    const items = payload.items.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const record = item as Record<string, unknown>;
      if (typeof record.src !== "string") return [];
      return [
        {
          src: record.src,
          alt: typeof record.alt === "string" ? record.alt : "Gallery image",
          caption: typeof record.caption === "string" ? record.caption : undefined,
          href: typeof record.href === "string" ? record.href : undefined,
        },
      ];
    });
    return items.length
      ? {
          id: typeof payload.id === "string" ? payload.id : undefined,
          block_id: typeof payload.block_id === "string" ? payload.block_id : undefined,
          type: payload.type === "gallery" ? "gallery" : undefined,
          revision: typeof payload.revision === "number" ? payload.revision : undefined,
          schema_version:
            typeof payload.schema_version === "number" ? payload.schema_version : undefined,
          source_markdown:
            typeof payload.source_markdown === "string" ? payload.source_markdown : undefined,
          assets: Array.isArray(payload.assets)
            ? payload.assets.filter(
                (
                  asset,
                ): asset is {
                  url: string;
                  owned_url?: string | null;
                  mime_type?: string | null;
                  status?: string;
                  file_id?: string | null;
                  retention?: "temporary" | "library";
                } =>
                  Boolean(
                    asset &&
                    typeof asset === "object" &&
                    typeof (asset as { url?: unknown }).url === "string",
                  ),
              )
            : undefined,
          history: Array.isArray(payload.history)
            ? payload.history.filter(
                (
                  entry,
                ): entry is {
                  revision: number;
                  source: string;
                  actor?: string | null;
                  at?: string | null;
                } =>
                  Boolean(
                    entry &&
                    typeof entry === "object" &&
                    typeof (entry as { revision?: unknown }).revision === "number" &&
                    typeof (entry as { source?: unknown }).source === "string",
                  ),
              )
            : undefined,
          undo:
            payload.undo && typeof payload.undo === "object" && !Array.isArray(payload.undo)
              ? (payload.undo as Record<string, unknown>)
              : undefined,
          title: typeof payload.title === "string" ? payload.title : "Gallery",
          items,
        }
      : null;
  } catch {
    return null;
  }
}

function safeExternalHref(value?: string | null): string | undefined {
  if (!value) return undefined;
  if (value.startsWith("/api/")) return value;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function getFileId(ownedUrl?: string | null): string | undefined {
  return ownedUrl?.match(/\/files\/([0-9a-f-]{36})\/content(?:\?|$)/i)?.[1];
}

function safeFilename(value: string): string {
  return value
    .trim()
    .replace(/[^\p{L}\p{N}_-]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}
