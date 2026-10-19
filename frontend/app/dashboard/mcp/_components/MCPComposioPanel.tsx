"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  connectComposioToolkit,
  getComposioAdminStatus,
  getComposioStatus,
  getComposioToolkit,
  getComposioToolkits,
  removeComposioApiKey,
  saveComposioApiKey,
  type MCPComposioStatus,
  type MCPComposioToolkit,
  type MCPComposioToolkitDetail,
} from "@/lib/mcp-api";
import { averqelConfirm } from "@/app/components/ui/AverQelDialogHost";

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

export default function MCPComposioPanel({
  connectedProviderSlugs,
  connectingProviderSlugs,
  onConnected,
}: Props) {
  const [status, setStatus] = useState<MCPComposioStatus | null>(null);
  const [canManageKey, setCanManageKey] = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);
  const [key, setKey] = useState("");
  const [keyFormOpen, setKeyFormOpen] = useState(false);
  const [keySaving, setKeySaving] = useState(false);
  const [query, setQuery] = useState("");
  const [apps, setApps] = useState<MCPComposioToolkit[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [selected, setSelected] = useState<MCPComposioToolkitDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busySlug, setBusySlug] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);

  const refreshCatalog = () => {
    setCursor(null);
    setSelected(null);
    void loadApps(query);
  };

  const loadApps = useCallback(
    async (search: string, nextCursor?: string | null, append = false) => {
      if (!status?.configured) return;
      const version = ++requestVersion.current;
      setCatalogLoading(true);
      setError(null);
      try {
        const result = await getComposioToolkits({ q: search, cursor: nextCursor });
        if (version !== requestVersion.current) return;
        setApps((current) => (append ? [...current, ...result.items] : result.items));
        setCursor(result.next_cursor || null);
        setTotal(result.total_items || 0);
      } catch (reason) {
        if (version === requestVersion.current)
          setError(
            reason instanceof Error ? reason.message : "The Composio catalog could not load.",
          );
      } finally {
        if (version === requestVersion.current) setCatalogLoading(false);
      }
    },
    [status?.configured],
  );

  useEffect(() => {
    let active = true;
    void getComposioStatus()
      .then(async (next) => {
        const adminStatus = await getComposioAdminStatus().catch(() => null);
        if (!active) return;
        setStatus(next);
        setCanManageKey(Boolean(adminStatus));
        if (!next.configured && adminStatus) setKeyFormOpen(true);
        if (next.configured) setKeyFormOpen(false);
      })
      .catch((reason: unknown) => {
        if (active)
          setError(reason instanceof Error ? reason.message : "Composio settings are unavailable.");
      })
      .finally(() => {
        if (active) setStatusLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!status?.configured) return;
    const timer = window.setTimeout(() => void loadApps(query), query ? 300 : 0);
    return () => window.clearTimeout(timer);
  }, [loadApps, query, status?.configured]);

  const saveKey = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!key.trim()) return;
    setKeySaving(true);
    setError(null);
    try {
      const next = await saveComposioApiKey(key);
      setStatus(next);
      setCanManageKey(true);
      setKey("");
      setKeyFormOpen(false);
      setApps([]);
      setCursor(null);
      setSelected(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The Composio key could not be saved.");
    } finally {
      setKeySaving(false);
    }
  };

  const showTools = async (
    app: MCPComposioToolkit,
    nextCursor: string | null = null,
    append = false,
  ) => {
    if (!append) setSelected(null);
    setDetailLoading(true);
    setError(null);
    try {
      const result = await getComposioToolkit(app.slug, nextCursor);
      setSelected((current) =>
        append && current?.slug === app.slug
          ? { ...result, tools: [...current.tools, ...result.tools] }
          : result,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Unable to load ${app.name} tools.`);
    } finally {
      setDetailLoading(false);
    }
  };

  const connect = async (app: MCPComposioToolkit) => {
    if (!app.no_auth && !status?.callback_verifier_enabled) return;
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

  const replaceKey = async () => {
    if (!canManageKey) return;
    if (!status?.configured) {
      setKeyFormOpen(true);
      return;
    }
    if (
      await averqelConfirm(
        "Replace the Composio key? Existing Composio app connections will be disabled and need to be connected again.",
      )
    ) {
      setKeyFormOpen(true);
    }
  };

  const removeKey = async () => {
    if (!canManageKey || !status?.configured) return;
    if (
      await averqelConfirm(
        "Remove AverQel's Composio project key? This disables all Composio app connections. Users will need to reconnect after a key is configured again.",
      )
    ) {
      setError(null);
      try {
        await removeComposioApiKey();
        setApps([]);
        setSelected(null);
        setStatus((current) =>
          current
            ? { ...current, configured: false }
            : { configured: false, callback_verifier_enabled: false, callback_verifier_url: null },
        );
        setKeyFormOpen(true);
      } catch (reason) {
        setError(
          reason instanceof Error ? reason.message : "The Composio key could not be removed.",
        );
      }
    }
  };

  return (
    <section className="space-y-5" aria-label="Composio apps">
      <header className="rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.04] p-5">
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
          Composio processes the app authorization and tool execution. Review the app’s requested
          access before approving it. OAuth connections require a verified callback; no-login apps
          can be added without OAuth.
        </p>
      </header>

      {error && (
        <p
          className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200"
          role="alert"
        >
          {error}
        </p>
      )}

      {statusLoading ? (
        <p className="text-sm text-white/60">Checking Composio setup…</p>
      ) : (
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="font-semibold text-white">Platform Composio project key</h3>
              <p className="mt-1 text-sm text-white/55">
                {status?.configured
                  ? "The key is encrypted on the server and never returned to browsers. App authorizations remain isolated to each signed-in AverQel user."
                  : "Configure one Composio project key for AverQel. Users only need to authorize their own app accounts."}
              </p>
            </div>
            {status?.configured && !keyFormOpen && canManageKey && (
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => void replaceKey()}
                  className="rounded-lg border border-white/15 px-3 py-2 text-sm text-white/80 hover:bg-white/5"
                >
                  Replace key
                </button>
                <button
                  type="button"
                  onClick={() => void removeKey()}
                  className="rounded-lg border border-red-400/25 px-3 py-2 text-sm text-red-200 hover:bg-red-400/10"
                >
                  Remove key
                </button>
              </div>
            )}
          </div>
          {canManageKey && (!status?.configured || keyFormOpen) && (
            <form
              onSubmit={(event) => void saveKey(event)}
              className="mt-4 flex flex-col gap-3 sm:flex-row"
            >
              <label className="sr-only" htmlFor="composio-api-key">
                Composio project API key
              </label>
              <input
                id="composio-api-key"
                type="password"
                autoComplete="new-password"
                value={key}
                onChange={(event) => setKey(event.target.value)}
                placeholder="Composio project API key"
                className="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50"
              />
              <button
                type="submit"
                disabled={keySaving || !key.trim()}
                className="rounded-xl bg-cyan-500 px-5 py-3 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
              >
                {keySaving
                  ? "Validating…"
                  : status?.configured
                    ? "Save replacement"
                    : "Validate and save"}
              </button>
              {status?.configured && (
                <button
                  type="button"
                  onClick={() => {
                    setKey("");
                    setKeyFormOpen(false);
                  }}
                  className="rounded-xl border border-white/10 px-4 py-3 text-sm text-white/65"
                >
                  Cancel
                </button>
              )}
            </form>
          )}
          {!status?.configured && !canManageKey && (
            <p className="mt-4 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/60">
              Composio has not been configured by the AverQel administrator yet.
            </p>
          )}
        </div>
      )}

      {status?.configured && !status.callback_verifier_enabled && (
        <div className="rounded-2xl border border-amber-400/25 bg-amber-400/[0.06] p-5">
          <h3 className="font-semibold text-amber-100">Finish OAuth identity verification</h3>
          <p className="mt-2 text-sm leading-6 text-white/65">
            The AverQel administrator must open the Composio project dashboard, go to Settings →
            General → Configuration, and set its callback verifier URL to this AverQel page. Then
            enable
            <code className="mx-1 rounded bg-black/30 px-1.5 py-0.5 text-amber-100">
              COMPOSIO_CALLBACK_VERIFIER_ENABLED=true
            </code>
            for this AverQel backend. OAuth app connections remain disabled until both are
            configured.
          </p>
          {status.callback_verifier_url ? (
            <code className="mt-3 block rounded-lg border border-white/10 bg-black/25 p-3 text-xs break-all text-white/80">
              {status.callback_verifier_url}
            </code>
          ) : (
            <p className="mt-3 text-sm text-amber-100/80">
              AverQel needs its public HTTPS origin configured before it can show the callback URL.
            </p>
          )}
          <a
            href="https://dashboard.composio.dev"
            target="_blank"
            rel="noreferrer"
            className="mt-4 inline-flex rounded-lg border border-amber-300/25 px-3 py-2 text-sm text-amber-100 hover:bg-amber-300/10"
          >
            Open Composio dashboard
          </a>
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
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search Composio apps"
                  className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50"
                />
              </label>
              <button
                type="button"
                disabled={catalogLoading}
                onClick={refreshCatalog}
                className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm text-white/75 hover:bg-white/5 disabled:opacity-50"
              >
                <RefreshCw
                  className={`h-4 w-4 ${catalogLoading ? "animate-spin" : ""}`}
                  aria-hidden="true"
                />
                Refresh catalog
              </button>
            </div>
          </div>
          {catalogLoading && apps.length === 0 ? (
            <p className="text-sm text-white/60">Loading Composio apps…</p>
          ) : apps.length === 0 ? (
            <p className="rounded-2xl border border-white/10 p-6 text-sm text-white/55">
              No Composio apps match this search.
            </p>
          ) : (
            <div className="grid items-stretch gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {apps.map((app) => {
                const providerSlug = `composio:${app.slug}`;
                const connected = connectedProviderSlugs.includes(providerSlug);
                const connecting = connectingProviderSlugs.includes(providerSlug);
                return (
                  <article
                    key={app.slug}
                    className="flex min-w-0 flex-col rounded-2xl border border-white/10 bg-[#111815] p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs tracking-wider text-cyan-200 uppercase">
                          Composio toolkit
                        </p>
                        <h3 className="mt-1 truncate text-lg font-semibold text-white">
                          {app.name}
                        </h3>
                        <p className="mt-1 text-xs text-white/45">{app.slug}</p>
                      </div>
                      <span className="shrink-0 rounded-full border border-white/10 px-2 py-1 text-xs text-white/55">
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
                          className="rounded-full bg-white/[0.06] px-2 py-1 text-[11px] text-white/55"
                        >
                          {category}
                        </span>
                      ))}
                      {app.auth_schemes.slice(0, 2).map((scheme) => (
                        <span
                          key={scheme}
                          className="rounded-full bg-cyan-400/[0.08] px-2 py-1 text-[11px] text-cyan-100/65"
                        >
                          {scheme}
                        </span>
                      ))}
                      {app.no_auth && (
                        <span className="rounded-full bg-white/[0.06] px-2 py-1 text-[11px] text-white/55">
                          No account login
                        </span>
                      )}
                    </div>
                    <div className="mt-auto flex gap-2 pt-4">
                      <button
                        type="button"
                        disabled={detailLoading}
                        onClick={() => void showTools(app)}
                        className="flex-1 rounded-lg border border-white/10 px-3 py-2.5 text-sm text-white/75 hover:bg-white/5 disabled:opacity-50"
                      >
                        View tools
                      </button>
                      <button
                        type="button"
                        disabled={
                          (!status.callback_verifier_enabled && !app.no_auth) ||
                          connected ||
                          connecting ||
                          busySlug === app.slug
                        }
                        onClick={() => void connect(app)}
                        className="flex-1 rounded-lg bg-cyan-500/15 px-3 py-2.5 text-sm font-medium text-cyan-100 hover:bg-cyan-500/25 disabled:cursor-not-allowed disabled:opacity-50"
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
                {catalogLoading ? "Loading…" : "Load more apps"}
              </button>
            </div>
          )}
        </>
      )}

      {selected && (
        <div className="rounded-2xl border border-cyan-300/20 bg-black/20 p-5" aria-live="polite">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs tracking-wider text-cyan-200 uppercase">{selected.slug}</p>
              <h3 className="mt-1 text-xl font-semibold text-white">{selected.name} tools</h3>
              <p className="mt-1 text-sm text-white/55">
                Loaded {selected.tools.length.toLocaleString("en-US")} of{" "}
                {selected.tool_count.toLocaleString("en-US")} listed tools.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void showTools(selected)}
              className="rounded-lg border border-white/10 px-3 py-2 text-sm text-white/75 hover:bg-white/5"
            >
              Refresh tools
            </button>
          </div>
          {selected.tools.length === 0 ? (
            <p className="mt-4 text-sm text-white/55">No tools were returned for this app.</p>
          ) : (
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
                    <span className="rounded-full border border-amber-300/20 bg-amber-300/[0.06] px-2 py-0.5 text-[10px] text-amber-100/80 uppercase">
                      {toolRiskLabel(tool.risk_labels[0] || "write")}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-white/50">
                    {tool.description || "No description provided by Composio."}
                  </p>
                  {Object.keys(
                    (tool.input_schema.properties as Record<string, unknown> | undefined) || {},
                  ).length > 0 && (
                    <details className="mt-2 text-xs text-white/55">
                      <summary className="cursor-pointer select-none">Input fields</summary>
                      <ul className="mt-2 space-y-1 pl-4">
                        {Object.entries(
                          tool.input_schema.properties as Record<
                            string,
                            { type?: string; description?: string }
                          >,
                        )
                          .slice(0, 30)
                          .map(([name, schema]) => (
                            <li key={name} className="break-words">
                              <code className="text-cyan-100/75">{name}</code>
                              {schema?.type ? (
                                <span className="text-white/35"> · {schema.type}</span>
                              ) : null}
                              {schema?.description ? (
                                <span className="text-white/45"> — {schema.description}</span>
                              ) : null}
                            </li>
                          ))}
                      </ul>
                      {Object.keys(tool.input_schema.properties || {}).length > 30 && (
                        <p className="mt-2 text-white/35">First 30 fields shown.</p>
                      )}
                    </details>
                  )}
                </li>
              ))}
            </ul>
          )}
          {selected.tools_next_cursor && (
            <div className="mt-4 text-center">
              <button
                type="button"
                disabled={detailLoading}
                onClick={() => void showTools(selected, selected.tools_next_cursor || null, true)}
                className="rounded-xl border border-white/10 px-5 py-3 text-sm text-white/75 hover:bg-white/5 disabled:opacity-50"
              >
                {detailLoading ? "Loading…" : "Load more tools"}
              </button>
            </div>
          )}
        </div>
      )}
      {detailLoading && !selected && <p className="text-sm text-white/60">Loading app tools…</p>}
    </section>
  );
}
