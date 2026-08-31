/* eslint-disable @next/next/no-img-element */
import Image from "next/image";
import Link from "next/link";
import { ArrowRight, ExternalLink } from "lucide-react";
import type { CSSProperties } from "react";

import type { MCPConnection, MCPMarketplaceEntry } from "@/lib/mcp-api";

import MCPHealthStatus from "./MCPHealthStatus";

const TRUSTED_LOGOS: Record<string, string> = {
  google: "/mcp/google.svg",
  github: "/mcp/github.svg",
  notion: "/mcp/notion.svg",
  slack: "/mcp/slack.svg",
};

const CARD_TINTS = [
  "rgba(34, 197, 94, 0.62)",
  "rgba(59, 130, 246, 0.62)",
  "rgba(239, 68, 68, 0.58)",
  "rgba(168, 85, 247, 0.58)",
  "rgba(20, 184, 166, 0.58)",
];

function cardTint(entry: MCPMarketplaceEntry): string {
  const key = `${entry.id}:${entry.provider_slug || entry.name}`;
  let hash = 0;
  for (const character of key) hash = (hash * 31 + character.charCodeAt(0)) | 0;
  return CARD_TINTS[Math.abs(hash) % CARD_TINTS.length];
}

export function resolveTrustedLogoPath(key?: string | null): string | null {
  const normalized = String(key || "")
    .trim()
    .toLowerCase();
  if (TRUSTED_LOGOS[normalized]) return TRUSTED_LOGOS[normalized];
  if (normalized.startsWith("google-")) return TRUSTED_LOGOS.google;
  if (normalized.startsWith("github-")) return TRUSTED_LOGOS.github;
  return null;
}

export function MCPLogo({ entry, size = 48 }: { entry: MCPMarketplaceEntry; size?: number }) {
  const logoPath = resolveTrustedLogoPath(entry.trusted_logo_key || entry.provider_slug);
  const communityLogo =
    entry.publisher_type === "community" && entry.logo_url && /^https:\/\//i.test(entry.logo_url)
      ? entry.logo_url
      : null;
  return (
    <div
      className="mcp-logo flex shrink-0 items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-slate-900"
      style={{ height: size, width: size }}
    >
      {logoPath ? (
        <Image src={logoPath} alt="" width={size - 12} height={size - 12} priority={size > 40} />
      ) : communityLogo ? (
        <img
          src={communityLogo}
          alt=""
          width={size - 12}
          height={size - 12}
          referrerPolicy="no-referrer"
        />
      ) : (
        <span className="text-sm font-semibold text-white/75">
          {entry.name.slice(0, 2).toUpperCase()}
        </span>
      )}
    </div>
  );
}

function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "green" | "blue" | "amber";
}) {
  const tones = {
    neutral: "border-white/10 bg-white/5 text-white/65",
    green: "border-emerald-400/25 bg-emerald-400/10 text-emerald-200",
    blue: "border-sky-400/25 bg-sky-400/10 text-sky-200",
    amber: "border-amber-400/25 bg-amber-400/10 text-amber-200",
  };
  return (
    <span className={`rounded-full border px-2 py-1 text-[11px] ${tones[tone]}`}>{children}</span>
  );
}

function formatTransport(value?: string | null): string {
  switch (value) {
    case "streamable_http":
      return "Remote HTTP";
    case "sse":
      return "Remote SSE";
    case "stdio":
      return "Local stdio";
    case "ssh":
      return "Remote SSH";
    default:
      return value ? value.replaceAll("_", " ") : "Remote";
  }
}

function authLabel(value?: string | null): string {
  return value === "oauth" ? "OAuth" : value === "anonymous" ? "Anonymous" : "Setup required";
}

export default function MCPMarketplaceCard({
  entry,
  connectedServer,
  onConnect,
  onReconnect,
}: {
  entry: MCPMarketplaceEntry;
  connectedServer?: MCPConnection | null;
  onConnect: (entry: MCPMarketplaceEntry) => void;
  onReconnect?: (server: MCPConnection) => void;
}) {
  const badges = entry.badges || {};
  const preview = entry.tool_preview || [];
  const connectable = entry.connectable;
  const tintStyle = { "--card-tint": cardTint(entry) } as CSSProperties;
  // Marketplace health is catalog-level and may remain ``not_checked`` even
  // after this user has connected the account. Prefer the tenant-owned live
  // connection status when one exists so the card reflects the account the
  // user can actually use.
  const displayHealth = connectedServer
    ? {
        status: connectedServer.status === "connected" ? "healthy" : connectedServer.status,
        last_checked_at: connectedServer.config?.mcp_catalog_last_sync_at || null,
      }
    : entry.health;
  return (
    <article
      style={tintStyle}
      className="mcp-marketplace-card group relative isolate flex h-full min-w-0 flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#111815] p-4 shadow-lg shadow-black/20 transition duration-300 hover:-translate-y-0.5 hover:border-white/25 hover:shadow-2xl hover:shadow-black/35"
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -inset-px z-0 [animation:spin_9s_linear_infinite] rounded-[inherit] bg-[conic-gradient(from_0deg,rgba(34,197,94,.72),rgba(59,130,246,.72),rgba(239,68,68,.68),var(--card-tint),rgba(34,197,94,.72))] opacity-0 blur-[0.5px] transition-opacity duration-500 group-focus-within:opacity-100 group-hover:opacity-100"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-px z-0 rounded-[calc(1rem-1px)] bg-[#111815]/95"
      />
      <div className="relative z-10 flex h-full flex-col">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <MCPLogo entry={entry} />
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold text-white">{entry.name}</h2>
              <p className="truncate text-xs text-white/55">
                {entry.publisher || entry.author_name || "Publisher unavailable"}
              </p>
            </div>
          </div>
          <div
            className="flex shrink-0 items-center gap-1 text-white/35"
            title="View provider details"
          >
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </div>
        </div>

        <div className="mt-3 flex min-h-7 flex-wrap gap-1.5">
          {entry.publisher_type === "community" || badges.community ? (
            <Badge tone="amber">Community</Badge>
          ) : entry.official || badges.official ? (
            <Badge tone="green">Official</Badge>
          ) : null}
          {entry.verified && <Badge tone="blue">Verified</Badge>}
          {badges.new && <Badge>New</Badge>}
          {badges.trending && <Badge>Trending</Badge>}
          {badges.interactive && <Badge>Interactive</Badge>}
        </div>

        <p className="mt-3 min-h-12 text-sm leading-5 text-white/65">
          {entry.description || "Approved remote MCP connector with cataloged tools."}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge>{formatTransport(entry.transport)}</Badge>
          <Badge>{authLabel(entry.auth_type)}</Badge>
          <Badge>{entry.tool_count ? `${entry.tool_count} tools` : "Tools pending"}</Badge>
        </div>
        {preview.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {preview.slice(0, 3).map((tool) => (
              <span
                key={tool.name}
                className="rounded-full border border-white/10 bg-black/10 px-2.5 py-1 text-xs text-white/65"
              >
                {tool.name}
              </span>
            ))}
          </div>
        )}
        <div className="mt-4 border-t border-white/5 pt-3">
          <MCPHealthStatus health={displayHealth} compact />
        </div>
        {!connectable && entry.connectability_reason && (
          <p className="mt-3 text-xs text-amber-200/80">{entry.connectability_reason}</p>
        )}
        <div className="mt-auto flex gap-2 pt-4">
          <Link
            href={`/dashboard/mcp/providers/${encodeURIComponent(entry.id)}`}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-white/80 hover:bg-white/10"
          >
            View details
          </Link>
          <button
            type="button"
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-sm font-medium text-sky-100 hover:bg-sky-400/15 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/5 disabled:text-white/35"
            disabled={!connectedServer && !connectable}
            onClick={() =>
              connectedServer && onReconnect ? onReconnect(connectedServer) : onConnect(entry)
            }
          >
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            {connectedServer ? "Reconnect" : connectable ? "Connect" : "Setup pending"}
          </button>
        </div>
      </div>
    </article>
  );
}
