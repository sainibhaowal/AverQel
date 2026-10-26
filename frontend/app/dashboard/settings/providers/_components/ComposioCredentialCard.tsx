"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { AlertCircle, CheckCircle2, ExternalLink, KeyRound, RefreshCw } from "lucide-react";
import toast from "react-hot-toast";

import { averqelConfirm } from "@/app/components/ui/AverQelDialogHost";
import {
  getComposioStatus,
  removeComposioApiKey,
  saveComposioApiKey,
  type MCPComposioStatus,
} from "@/lib/mcp-api";

export default function ComposioCredentialCard() {
  const [status, setStatus] = useState<MCPComposioStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setStatus(await getComposioStatus());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load Composio settings.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    queueMicrotask(() => void refresh());
  }, []);

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!apiKey.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const next = await saveComposioApiKey(apiKey);
      setStatus(next);
      setApiKey("");
      setEditing(false);
      toast.success("Your Composio key is connected");
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Unable to save the Composio key.";
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!status?.configured) return;
    const confirmed = await averqelConfirm(
      "Remove your Composio key? This disconnects only the Composio apps connected to your AverQel account.",
    );
    if (!confirmed) return;
    setRemoving(true);
    setError(null);
    try {
      await removeComposioApiKey();
      setStatus((current) => (current ? { ...current, configured: false } : current));
      toast.success("Your Composio key was removed");
    } catch (reason) {
      const message =
        reason instanceof Error ? reason.message : "Unable to remove the Composio key.";
      setError(message);
      toast.error(message);
    } finally {
      setRemoving(false);
    }
  };

  return (
    <section
      className="col-span-full space-y-5"
      aria-labelledby="composio-provider-heading"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-foreground flex items-center gap-2 text-xs font-semibold tracking-[0.18em] uppercase">
            <KeyRound className="text-primary" size={14} aria-hidden="true" /> MCP provider
          </p>
          <h2 id="composio-provider-heading" className="mt-2 text-xl font-semibold">
            Composio
          </h2>
          <p className="text-foreground/80 mt-2 text-sm leading-6">
            Add your own Composio project API key. AverQel encrypts it and scopes it to your
            account; the server uses it to load your app catalog and connect your app accounts.
            Other AverQel users cannot use your key.
          </p>
        </div>
        <Link
          href="/dashboard/mcp"
          className="border-primary/40 bg-surface-1 text-foreground hover:border-primary/70 inline-flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm transition-colors"
        >
          Browse Composio apps <ExternalLink size={14} aria-hidden="true" />
        </Link>
      </div>

      <div className="theme-inset rounded-xl p-4">
        {loading ? (
          <p className="text-foreground/80 text-sm">Checking your Composio connection…</p>
        ) : status?.configured && !editing ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-foreground flex items-center gap-2 text-sm font-medium">
              <CheckCircle2 className="text-success" size={16} aria-hidden="true" />
              Your Composio key is saved securely.
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="border-primary/40 bg-surface-1 text-foreground hover:border-primary/70 rounded-lg border px-3 py-2 text-sm transition-colors"
              >
                Replace key
              </button>
              <button
                type="button"
                disabled={removing}
                onClick={() => void remove()}
                className="border-danger/35 text-danger hover:bg-danger/10 rounded-lg border px-3 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              >
                {removing ? "Removing…" : "Remove key"}
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={(event) => void save(event)} className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label htmlFor="composio-project-key" className="text-sm font-medium">
                Your Composio project API key
              </label>
              <a
                href="https://dashboard.composio.dev"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Get an API key from the Composio dashboard (opens in a new tab)"
                className="text-foreground inline-flex items-center gap-1 text-sm underline decoration-primary/60 underline-offset-4 hover:decoration-primary"
              >
                Get an API key <ExternalLink size={13} aria-hidden="true" />
              </a>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                id="composio-project-key"
                type="password"
                autoComplete="new-password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="Paste your Composio project API key"
                className="border-glass-border bg-surface-0 text-foreground placeholder:text-foreground/65 focus:border-primary focus:ring-primary/40 min-w-0 flex-1 rounded-xl border px-4 py-3 text-sm outline-none transition focus:ring-2"
              />
              <button
                type="submit"
                disabled={saving || !apiKey.trim()}
                className="bg-primary text-primary-foreground focus-visible:ring-primary/50 inline-flex items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-foreground disabled:opacity-100"
              >
                {saving ? <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
                {saving
                  ? "Validating…"
                  : status?.configured
                    ? "Save replacement"
                    : "Validate and save"}
              </button>
              {status?.configured && editing ? (
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setApiKey("");
                  }}
                  className="border-primary/40 bg-surface-1 text-foreground hover:border-primary/70 rounded-xl border px-4 py-3 text-sm transition-colors"
                >
                  Cancel
                </button>
              ) : null}
            </div>
            <p className="text-foreground/75 text-xs leading-5">
              Find the key in your Composio project settings. AverQel validates it before saving and
              never sends the saved key back to your browser.
            </p>
          </form>
        )}
      </div>

      {!status?.oauth_callback_ready && status?.configured ? (
        <p className="border-warning/35 bg-warning/10 text-foreground mt-3 rounded-lg border p-3 text-sm">
          OAuth app sign-in needs the AverQel server’s public HTTPS origin. No-auth Composio apps
          can still be connected.
        </p>
      ) : null}

      {error ? (
        <p
          className="border-danger/35 bg-danger/10 text-foreground mt-3 flex items-start gap-2 rounded-lg border p-3 text-sm"
          role="alert"
        >
          <AlertCircle className="text-danger mt-0.5 shrink-0" size={16} aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : null}
    </section>
  );
}
