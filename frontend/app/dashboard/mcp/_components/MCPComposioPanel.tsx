"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { AppWindow, ExternalLink, RefreshCw, X } from "lucide-react";
import AverQelLoading from "@/app/components/ui/AverQelLoading";
import {
  connectComposioToolkit,
  getComposioStatus,
  getComposioToolkit,
  getComposioToolkits,
  safeExternalUrl,
  type MCPComposioStatus,
  type MCPComposioToolkit,
  type MCPComposioToolkitDetail,
} from "@/lib/mcp-api";
import MCPLoadingIndicator from "./MCPLoadingIndicator";

const COMPOSIO_PAGE_SIZE = 24;

type Props = {
  connectedProviderSlugs: string[];
  connectingProviderSlugs: string[];
  onConnected: () => void;
};

function toolRiskLabel(risk: string): string {
  if (risk === "read") return "Read · may run automatically";
  if (risk === "delete") return "Delete · approval required";
  if (risk === "external_message") return "External action · approval required";
  return "Write · approval required";
}

function composioAssetUrl(slug: string): string | null {
  if (!/^(?:[a-z0-9][a-z0-9_-]{0,127}|_[a-z0-9][a-z0-9_-]{0,126})$/.test(slug)) return null;
  return `https://logos.composio.dev/api/${slug}`;
}

function ComposioLogo({ app, size = 48 }: { app: MCPComposioToolkit; size?: number }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  // Resolve by the Composio toolkit slug. The catalog's `meta.logo` may point
  // to an app-owned host with stale URLs, while this CDN is curated by Composio.
  const logoUrl = composioAssetUrl(app.slug);
  return (
    <span
      className="mcp-composio-logo flex shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-300 dark:bg-white"
      style={{ height: size, width: size }}
      aria-hidden="true"
      data-testid="composio-app-logo"
    >
      {logoUrl && failedUrl !== logoUrl ? (
        <Image
          src={logoUrl}
          alt=""
          width={size - 10}
          height={size - 10}
          unoptimized
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailedUrl(logoUrl)}
          className="h-[calc(100%-10px)] w-[calc(100%-10px)] object-contain"
        />
      ) : (
        <AppWindow
          className="h-5 w-5 text-teal-700"
          aria-hidden="true"
          data-testid="composio-logo-fallback"
        />
      )}
    </span>
  );
}

function secureLink(value?: string | null): string | null {
  const url = safeExternalUrl(value);
  return url && new URL(url).protocol === "https:" ? url : null;
}

function formatCatalogDate(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? null
    : date.toLocaleString("en-GB", { timeZone: "UTC", timeZoneName: "short" });
}

function ComposioToolInputDetails({ schema }: { schema: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const rawProperties = schema.properties;
  const properties =
    rawProperties && typeof rawProperties === "object" && !Array.isArray(rawProperties)
      ? (rawProperties as Record<string, unknown>)
      : {};
  const required = Array.isArray(schema.required)
    ? schema.required.filter((item): item is string => typeof item === "string")
    : [];

  return (
    <div className="mt-2 text-xs text-white/55">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
        className="text-left underline decoration-white/20 underline-offset-2 hover:text-white/80"
      >
        {expanded
          ? "Hide input schema"
          : Object.keys(properties).length
            ? `Input fields (${Object.keys(properties).length})`
            : "View input schema"}
      </button>
      {expanded && (
        <div className="mt-2">
          {Object.keys(properties).length > 0 && (
            <ul className="space-y-1 pl-4">
              {Object.entries(properties).map(([name, value]) => {
                const field =
                  value && typeof value === "object" && !Array.isArray(value)
                    ? (value as { type?: string; description?: string })
                    : {};
                return (
                  <li key={name} className="break-words">
                    <code className="text-cyan-100/75">{name}</code>
                    {field.type ? <span className="text-white/35"> · {field.type}</span> : null}
                    {required.includes(name) ? (
                      <span className="ml-1 text-amber-200/80">· required</span>
                    ) : null}
                    {field.description ? (
                      <span className="text-white/45"> — {field.description}</span>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
          <button
            type="button"
            aria-expanded={showJson}
            onClick={() => setShowJson((value) => !value)}
            className="mt-2 text-cyan-200/80 underline decoration-cyan-200/20 underline-offset-2 hover:text-cyan-100"
          >
            {showJson ? "Hide complete JSON schema" : "View complete JSON schema"}
          </button>
          {showJson && (
            <pre className="mt-2 max-h-72 overflow-auto rounded-lg border border-white/10 bg-black/20 p-3 text-[11px] leading-5 text-white/65">
              {JSON.stringify(schema, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export default function MCPComposioPanel({
  connectedProviderSlugs,
  connectingProviderSlugs,
  onConnected,
}: Props) {
  const [status, setStatus] = useState<MCPComposioStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusFailed, setStatusFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [apps, setApps] = useState<MCPComposioToolkit[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogFailed, setCatalogFailed] = useState(false);
  const [selected, setSelected] = useState<MCPComposioToolkitDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [busySlug, setBusySlug] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const detailsDialog = useRef<HTMLDialogElement | null>(null);
  const detailsTrigger = useRef<HTMLButtonElement | null>(null);
  const requestVersion = useRef(0);
  const statusAbort = useRef<AbortController | null>(null);
  const catalogAbort = useRef<AbortController | null>(null);
  const detailAbort = useRef<AbortController | null>(null);

  const closeDetails = () => {
    detailAbort.current?.abort();
    setDetailLoading(false);
    setDetailError(null);
    setSelected(null);
  };

  const refreshCatalog = () => {
    setCursor(null);
    setSelected(null);
    void loadApps(query);
  };

  const loadApps = useCallback(
    async (search: string, nextCursor?: string | null, append = false) => {
      if (!status?.configured) return;
      catalogAbort.current?.abort();
      const controller = new AbortController();
      catalogAbort.current = controller;
      const version = ++requestVersion.current;
      setCatalogLoading(true);
      setCatalogFailed(false);
      setError(null);
      try {
        const result = await getComposioToolkits(
          { q: search, cursor: nextCursor, limit: COMPOSIO_PAGE_SIZE },
          { signal: controller.signal },
        );
        if (version !== requestVersion.current) return;
        setApps((current) => (append ? [...current, ...result.items] : result.items));
        setCursor(result.next_cursor || null);
        setTotal(result.total_items || 0);
      } catch (reason) {
        if (version === requestVersion.current && !controller.signal.aborted) {
          setCatalogFailed(true);
          setError(
            reason instanceof Error ? reason.message : "The Composio catalog could not load.",
          );
        }
      } finally {
        if (version === requestVersion.current) setCatalogLoading(false);
      }
    },
    [status?.configured],
  );

  const loadStatus = useCallback(async () => {
    statusAbort.current?.abort();
    const controller = new AbortController();
    statusAbort.current = controller;
    setStatusLoading(true);
    setError(null);
    try {
      const next = await getComposioStatus({ signal: controller.signal });
      if (!controller.signal.aborted) {
        setStatus(next);
        setStatusFailed(false);
      }
    } catch (reason) {
      if (!controller.signal.aborted) {
        setStatusFailed(true);
        setError(reason instanceof Error ? reason.message : "Composio settings are unavailable.");
      }
    } finally {
      if (!controller.signal.aborted) setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadStatus(), 0);
    return () => {
      window.clearTimeout(timer);
      statusAbort.current?.abort();
    };
  }, [loadStatus]);

  useEffect(() => {
    if (!status?.configured) return;
    const timer = window.setTimeout(() => void loadApps(query), query ? 300 : 0);
    return () => {
      window.clearTimeout(timer);
      requestVersion.current += 1;
      catalogAbort.current?.abort();
    };
  }, [loadApps, query, status?.configured]);

  useEffect(() => {
    return () => detailAbort.current?.abort();
  }, []);

  const selectedSlug = selected?.slug;
  useEffect(() => {
    if (!selectedSlug) return;
    const dialog = detailsDialog.current;
    if (dialog && !dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    }
    return () => {
      if (dialog?.open) {
        if (typeof dialog.close === "function") dialog.close();
        else dialog.removeAttribute("open");
      }
      if (detailsTrigger.current?.isConnected) detailsTrigger.current.focus();
    };
  }, [selectedSlug]);

  /*
   * Keep the catalog request tied to the active search. A new search aborts
   * the previous network request instead of letting stale responses occupy
   * server/client resources or replace current results.
   */
  const showTools = async (
    app: MCPComposioToolkit,
    nextCursor: string | null = null,
    append = false,
    trigger?: HTMLButtonElement,
  ) => {
    detailAbort.current?.abort();
    const controller = new AbortController();
    detailAbort.current = controller;
    if (trigger) detailsTrigger.current = trigger;
    if (!append) {
      setSelected({ ...app, tools: [], tools_loaded: 0, tools_next_cursor: null });
    }
    setDetailError(null);
    setDetailLoading(true);
    try {
      const result = await getComposioToolkit(app.slug, nextCursor, {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setSelected((current) =>
        append && current?.slug === app.slug
          ? { ...result, tools: [...current.tools, ...result.tools] }
          : result,
      );
    } catch (reason) {
      if (!controller.signal.aborted)
        setDetailError(
          reason instanceof Error ? reason.message : `Unable to load ${app.name} details.`,
        );
    } finally {
      if (!controller.signal.aborted) setDetailLoading(false);
    }
  };

  const connect = async (app: MCPComposioToolkit) => {
    if (!app.no_auth && !status?.oauth_callback_ready) return;
    setBusySlug(app.slug);
    setError(null);
    try {
      const result = await connectComposioToolkit(app.slug);
      if (result.already_connected) {
        onConnected();
        return;
      }
      if (!result.authorization_required) {
        onConnected();
        return;
      }
      if (result.authorization_url) {
        window.location.assign(result.authorization_url);
        return;
      }
      setError("Composio did not return an authorization link. Try again.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Unable to connect ${app.name}.`);
    } finally {
      setBusySlug(null);
    }
  };

  const appWebsiteUrl = secureLink(selected?.app_url);
  const authGuideUrl = secureLink(selected?.auth_guide_url);
  const createdAt = formatCatalogDate(selected?.created_at);
  const updatedAt = formatCatalogDate(selected?.updated_at);

  return (
    <section className="mcp-composio-panel space-y-5" aria-label="Composio apps">
      <header className="mcp-composio-intro rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.04] p-5">
        <p className="text-xs font-semibold tracking-[0.18em] text-cyan-200 uppercase">
          Composio app catalog
        </p>
        <h2 className="mt-2 text-xl font-semibold text-white">Connect apps to DeepSpace</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-white/65">
          Browse Composio’s live toolkit catalog, inspect its available actions, and authorize an
          app account. Each connection belongs to your AverQel account and uses the existing MCP
          policy and approval controls.
        </p>
        <p className="mt-3 text-xs leading-5 text-white/50">
          Composio processes app authorization and tool execution. After sign-in, AverQel checks the
          callback against the connection request started by your account before enabling its tools.
          Review requested access and approve side-effecting actions in DeepSpace.
        </p>
      </header>

      {error && (
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200"
          role="alert"
        >
          <span>{error}</span>
          {statusFailed && (
            <button
              type="button"
              onClick={() => void loadStatus()}
              className="rounded-lg border border-red-200/20 px-3 py-1.5 text-xs font-medium hover:bg-red-200/10"
            >
              Retry setup check
            </button>
          )}
          {catalogFailed && apps.length > 0 && (
            <button
              type="button"
              onClick={() => void loadApps(query)}
              className="rounded-lg border border-red-200/20 px-3 py-1.5 text-xs font-medium hover:bg-red-200/10"
            >
              Retry catalog
            </button>
          )}
        </div>
      )}

      {statusLoading ? (
        <MCPLoadingIndicator
          label="Checking Composio setup…"
          size="compact"
          className="rounded-xl border border-white/10 bg-white/[0.02] p-4"
        />
      ) : status && !status.configured ? (
        <div
          className="rounded-2xl border border-amber-400/20 bg-amber-400/[0.05] p-5"
          role="status"
        >
          <h3 className="font-semibold text-amber-100">Add your Composio key to browse apps</h3>
          <p className="mt-2 text-sm leading-6 text-white/65">
            Each AverQel account uses its own Composio project key. Add yours in Providers, then
            return here to browse apps and connect your accounts.
          </p>
          <Link
            href="/dashboard/settings/providers?tab=mcp"
            className="mt-4 inline-flex rounded-lg border border-white/15 px-3 py-2 text-sm text-white/85 hover:bg-white/5"
          >
            Open Providers → MCP
          </Link>
        </div>
      ) : null}

      {status?.configured && !status.oauth_callback_ready && (
        <div className="rounded-2xl border border-amber-400/25 bg-amber-400/[0.06] p-5">
          <h3 className="font-semibold text-amber-100">OAuth apps need AverQel’s public URL</h3>
          <p className="mt-2 text-sm leading-6 text-white/65">
            The AverQel server needs its public HTTPS origin configured so Composio can return you
            here after sign-in. You do not need to configure a platform Composio key or a callback
            verifier in your Composio project. No-auth apps can still be added.
          </p>
        </div>
      )}

      {status?.configured && (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-white/55">
              {total.toLocaleString("en-US")} Composio apps available
            </p>
            <div className="flex w-full gap-2 sm:max-w-xl">
              <label className="min-w-0 flex-1">
                <span className="sr-only">Search Composio apps</span>
                <input
                  value={query}
                  onChange={(event) => {
                    requestVersion.current += 1;
                    catalogAbort.current?.abort();
                    setQuery(event.target.value);
                    setApps([]);
                    setCursor(null);
                    setTotal(0);
                    setCatalogLoading(true);
                    setCatalogFailed(false);
                    setError(null);
                  }}
                  placeholder="Search Composio apps"
                  className="mcp-composio-search w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50"
                />
              </label>
              <button
                type="button"
                disabled={catalogLoading}
                onClick={refreshCatalog}
                className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm text-white/75 hover:bg-white/5 disabled:opacity-50"
              >
                <RefreshCw
                  className={`h-4 w-4 ${catalogLoading ? "motion-safe:animate-spin" : ""}`}
                  aria-hidden="true"
                />
                Refresh catalog
              </button>
            </div>
          </div>
          {catalogLoading && apps.length > 0 && (
            <MCPLoadingIndicator
              label="Refreshing Composio apps…"
              size="compact"
              className="text-white/60"
            />
          )}
          {catalogLoading && apps.length === 0 ? (
            <MCPLoadingIndicator
              label="Loading Composio apps…"
              size="large"
              className="rounded-2xl border border-white/10 bg-white/[0.02] p-6"
            />
          ) : catalogFailed && apps.length === 0 ? (
            <div
              className="rounded-2xl border border-red-500/20 bg-red-500/[0.04] p-6 text-center"
              role="status"
            >
              <h3 className="font-semibold text-white">Composio apps could not be loaded</h3>
              <p className="mt-2 text-sm text-white/55">
                The rest of the page remains available. Check the connection and retry the catalog.
              </p>
              <button
                type="button"
                onClick={() => void loadApps(query)}
                className="mt-4 rounded-lg border border-white/15 px-4 py-2 text-sm text-white/80 hover:bg-white/5"
              >
                Retry catalog
              </button>
            </div>
          ) : apps.length === 0 ? (
            <p className="rounded-2xl border border-white/10 p-6 text-sm text-white/55">
              No Composio apps match this search.
            </p>
          ) : (
            <div className="grid items-stretch gap-4 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
              {apps.map((app) => {
                const providerSlug = `composio:${app.slug}`;
                const connected = connectedProviderSlugs.includes(providerSlug);
                const connecting = connectingProviderSlugs.includes(providerSlug);
                return (
                  <article
                    key={app.slug}
                    className="mcp-composio-app-card flex min-w-0 flex-col rounded-2xl border border-white/10 bg-[#111815] p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <ComposioLogo app={app} size={44} />
                        <div className="min-w-0">
                          <p className="text-[10px] tracking-wider text-cyan-200 uppercase">
                            Composio toolkit
                          </p>
                          <h3 className="mt-1 truncate text-lg font-semibold text-white">
                            {app.name}
                          </h3>
                          <p className="mt-1 truncate text-xs text-white/45">{app.slug}</p>
                        </div>
                      </div>
                      <span className="shrink-0 rounded-lg border border-white/10 px-2 py-1 text-xs text-white/55">
                        {app.tool_count.toLocaleString("en-US")} tools
                      </span>
                    </div>
                    <p className="mt-3 line-clamp-3 min-h-12 text-sm leading-5 text-white/60">
                      {app.description || "Connect this app and inspect its available actions."}
                    </p>
                    <div className="mt-3 flex min-h-6 flex-wrap gap-1.5">
                      {app.categories.slice(0, 3).map((category) => (
                        <span
                          key={category}
                          className="mcp-composio-category-tag rounded-lg bg-white/[0.06] px-2 py-1 text-[11px] text-white/55"
                        >
                          {category}
                        </span>
                      ))}
                      {app.auth_schemes.slice(0, 2).map((scheme) => (
                        <span
                          key={scheme}
                          className="mcp-composio-auth-tag rounded-lg bg-cyan-400/[0.08] px-2 py-1 text-[11px] text-cyan-100/65"
                        >
                          {scheme}
                        </span>
                      ))}
                      {app.no_auth && (
                        <span className="rounded-lg bg-white/[0.06] px-2 py-1 text-[11px] text-white/55">
                          No account login
                        </span>
                      )}
                    </div>
                    <div className="mt-auto flex gap-2 pt-4">
                      <button
                        type="button"
                        aria-haspopup="dialog"
                        onClick={(event) => void showTools(app, null, false, event.currentTarget)}
                        className="flex-1 rounded-lg border border-white/10 px-3 py-2.5 text-sm text-white/75 hover:bg-white/5 disabled:opacity-50"
                      >
                        View details
                      </button>
                      <button
                        type="button"
                        disabled={
                          (!status.oauth_callback_ready && !app.no_auth) ||
                          connected ||
                          connecting ||
                          busySlug === app.slug
                        }
                        onClick={() => void connect(app)}
                        className="mcp-composio-connect-button flex-1 rounded-lg bg-cyan-500/15 px-3 py-2.5 text-sm font-medium text-cyan-100 hover:bg-cyan-500/25 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {connected
                          ? "Connected"
                          : connecting
                            ? "Adding…"
                            : busySlug === app.slug
                              ? "Starting…"
                              : app.no_auth
                                ? "Add to DeepSpace"
                                : "Connect"}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
          {cursor && (
            <div className="text-center">
              <button
                type="button"
                disabled={catalogLoading}
                onClick={() => void loadApps(query, cursor, true)}
                className="rounded-xl border border-white/10 px-5 py-3 text-sm text-white/75 hover:bg-white/5 disabled:opacity-50"
              >
                {catalogLoading ? (
                  <AverQelLoading size="inline" label="Loading more apps" />
                ) : (
                  "Load more apps"
                )}
              </button>
            </div>
          )}
        </>
      )}

      {selected && (
        <dialog
          ref={detailsDialog}
          aria-labelledby="composio-details-title"
          aria-describedby="composio-details-description"
          className="mcp-composio-details-dialog mcp-theme-scope fixed inset-0 m-auto max-h-[min(92dvh,58rem)] w-[min(96vw,76rem)] max-w-none overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#111815] p-0 text-white shadow-2xl backdrop:bg-slate-950/80 backdrop:backdrop-blur-sm"
          onCancel={(event) => {
            event.preventDefault();
            closeDetails();
          }}
          onClick={(event) => {
            if (event.target === event.currentTarget) closeDetails();
          }}
        >
          <div className="max-h-[min(92dvh,58rem)] overflow-y-auto p-5 sm:p-7">
            <header className="flex items-start gap-4">
              <ComposioLogo app={selected} size={56} />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold tracking-[0.16em] text-cyan-200 uppercase">
                  Composio app details
                </p>
                <h2 id="composio-details-title" className="mt-1 text-2xl font-semibold text-white">
                  {selected.name}
                </h2>
                <p className="mt-1 font-mono text-xs break-all text-white/45">{selected.slug}</p>
              </div>
              <button
                type="button"
                onClick={closeDetails}
                aria-label="Close app details"
                className="rounded-lg border border-white/10 p-2 text-white/70 hover:bg-white/10"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </header>

            <p
              id="composio-details-description"
              className="mt-5 max-w-4xl text-sm leading-6 text-white/65"
            >
              {selected.description || "Composio does not provide a description for this app."}
            </p>

            <section className="mt-5 rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <h3 className="text-sm font-semibold text-white/85">App information</h3>
              <dl className="mt-3 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <dt className="text-xs text-white/45">Publisher / author</dt>
                  <dd className="mt-1 text-white/75">Not provided in Composio’s toolkit catalog</dd>
                </div>
                <div>
                  <dt className="text-xs text-white/45">Catalog source</dt>
                  <dd className="mt-1 text-white/75">Composio</dd>
                </div>
                <div>
                  <dt className="text-xs text-white/45">Connection</dt>
                  <dd className="mt-1 text-white/75">Composio-managed MCP tools</dd>
                </div>
                <div>
                  <dt className="text-xs text-white/45">Authentication</dt>
                  <dd className="mt-1 text-white/75">
                    {selected.no_auth
                      ? "No app sign-in required"
                      : selected.auth_schemes.join(", ") || "Authentication details not listed"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-white/45">Available tools</dt>
                  <dd className="mt-1 text-white/75">
                    {selected.tool_count.toLocaleString("en-US")} in the latest catalog
                  </dd>
                </div>
                {selected.version && (
                  <div>
                    <dt className="text-xs text-white/45">Catalog version</dt>
                    <dd className="mt-1 break-all text-white/75">{selected.version}</dd>
                  </div>
                )}
                {createdAt && (
                  <div>
                    <dt className="text-xs text-white/45">Catalog entry created (UTC)</dt>
                    <dd className="mt-1 text-white/75">{createdAt}</dd>
                  </div>
                )}
                {updatedAt && (
                  <div>
                    <dt className="text-xs text-white/45">Catalog entry updated (UTC)</dt>
                    <dd className="mt-1 text-white/75">{updatedAt}</dd>
                  </div>
                )}
                <div className="sm:col-span-2 lg:col-span-3">
                  <dt className="text-xs text-white/45">Categories</dt>
                  <dd className="mt-1 text-white/75">
                    {selected.categories.length ? selected.categories.join(", ") : "Not listed"}
                  </dd>
                </div>
              </dl>
              <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-white/10 pt-3">
                {appWebsiteUrl && (
                  <a
                    href={appWebsiteUrl}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex items-center gap-1.5 text-sm text-cyan-200 underline decoration-cyan-200/30 underline-offset-4 hover:text-cyan-100"
                  >
                    App website <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                )}
                {authGuideUrl && (
                  <a
                    href={authGuideUrl}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex items-center gap-1.5 text-sm text-cyan-200 underline decoration-cyan-200/30 underline-offset-4 hover:text-cyan-100"
                  >
                    Authentication guide <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                )}
                {!appWebsiteUrl && !authGuideUrl && (
                  <p className="text-xs text-white/45">
                    No external app or auth guide links provided.
                  </p>
                )}
                <p className="w-full text-xs text-white/45">
                  Composio manages the MCP connection. Its catalog does not publish a separate
                  per-app MCP endpoint URL.
                </p>
              </div>
            </section>

            <section className="mt-6" aria-live="polite">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-white">Available tools</h3>
                  <p className="mt-1 text-sm text-white/50">
                    Showing {selected.tools.length.toLocaleString("en-US")} of{" "}
                    {selected.tool_count.toLocaleString("en-US")} catalog tools.
                  </p>
                </div>
                <button
                  type="button"
                  disabled={detailLoading}
                  onClick={() => void showTools(selected)}
                  className="rounded-lg border border-white/10 px-3 py-2 text-sm text-white/75 hover:bg-white/5 disabled:opacity-50"
                >
                  Refresh details
                </button>
              </div>
              {detailError && (
                <div
                  className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200"
                  role="alert"
                >
                  <span>{detailError}</span>
                  <button
                    type="button"
                    onClick={() => void showTools(selected)}
                    className="rounded-md border border-red-200/20 px-3 py-1.5 text-xs hover:bg-red-200/10"
                  >
                    Retry details
                  </button>
                </div>
              )}
              {detailLoading && (
                <MCPLoadingIndicator
                  label={selected.tools.length ? "Loading more app tools…" : "Loading app tools…"}
                  size="compact"
                  className="mt-4"
                />
              )}
              {!detailLoading && !detailError && selected.tools.length === 0 ? (
                <p className="mt-4 rounded-xl border border-white/10 p-4 text-sm text-white/55">
                  Composio returned no tools for this app.
                </p>
              ) : (
                selected.tools.length > 0 && (
                  <ul className="mt-4 grid gap-2 md:grid-cols-2">
                    {selected.tools.map((tool) => (
                      <li
                        key={tool.name}
                        className="rounded-xl border border-white/10 bg-white/[0.03] p-3"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <code className="text-xs font-semibold break-all text-white/85">
                            {tool.name}
                          </code>
                          <span className="rounded-lg border border-amber-300/20 bg-amber-300/[0.06] px-2 py-0.5 text-[10px] text-amber-100/80 uppercase">
                            {toolRiskLabel(tool.risk_labels[0] || "write")}
                          </span>
                        </div>
                        <p className="mt-2 text-xs leading-5 text-white/50">
                          {tool.description || "No description provided by Composio."}
                        </p>
                        <ComposioToolInputDetails schema={tool.input_schema} />
                      </li>
                    ))}
                  </ul>
                )
              )}
              {selected.tools_next_cursor && (
                <div className="mt-4 text-center">
                  <button
                    type="button"
                    disabled={detailLoading}
                    onClick={() =>
                      void showTools(selected, selected.tools_next_cursor || null, true)
                    }
                    className="rounded-xl border border-white/10 px-5 py-3 text-sm text-white/75 hover:bg-white/5 disabled:opacity-50"
                  >
                    {detailLoading ? (
                      <AverQelLoading size="inline" label="Loading more tools" />
                    ) : (
                      "Load more tools"
                    )}
                  </button>
                </div>
              )}
            </section>
          </div>
        </dialog>
      )}
    </section>
  );
}
