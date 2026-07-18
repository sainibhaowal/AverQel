"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Cable,
  Globe,
  Cloud,
  Slack,
  Github,
  Plus,
  RefreshCw,
  Settings2,
  CheckCircle2,
  Clock,
  ArrowRight,
  Activity,
  ShieldCheck,
  Zap,
  Network,
  ChevronLeft,
  FileText,
  ExternalLink,
  Mail,
  Calendar,
  Wifi,
  Cpu,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { fetchWithAuth } from "@/lib/api";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import AverQelTooltip from "@/app/components/ui/AverQelTooltip";

interface Integration {
  id: string;
  name: string;
  slug: string;
  description: string;
  ui_metadata: {
    setup_fields?: IntegrationSetupField[];
    [key: string]: unknown;
  };
  oauth_status?: {
    configured: boolean;
    message: string;
    missing: string[];
    provider_key?: string | null;
  } | null;
}

interface IntegrationSetupField {
  name: string;
  label: string;
  type: "text" | "url" | "password" | "number" | "textarea";
  required?: boolean;
  section?: "primary" | "advanced";
  default_value?: string | number;
  placeholder?: string;
  help_text?: string;
}

interface Connector {
  id: string;
  name: string;
  status: "ACTIVE" | "PAUSED" | "ERROR" | "SYNCING";
  last_sync_at: string | null;
  sync_frequency: string;
  last_error: string | null;
  integration_id: string;
  config?: {
    mcp_tools_cache?: Array<{
      name: string;
      description?: string;
      [key: string]: unknown;
    }>;
    [key: string]: unknown;
  };
}

interface ActivityItem {
  id: string;
  source: string;
  description: string;
  created_at: string;
}

interface ConnectorDocument {
  id: string;
  filename: string;
}

interface IntegrationDetail {
  summary: string;
  access: string;
  auth: string;
  manage: string;
  sync: string;
  output: string;
  tools?: string[];
  author?: string;
  connectorUrl?: string;
  fullDescription?: string;
}

const OAUTH_INTEGRATIONS = new Set([
  "google-drive",
  "gmail",
  "google-calendar",
  "github",
  "slack",
  "notion",
]);

function normalizeStatus(status: string) {
  return status.toUpperCase();
}

function isPrimarySetupField(field: IntegrationSetupField) {
  return field.required !== false || field.section === "primary";
}

function getFieldPlaceholder(field: IntegrationSetupField) {
  if (field.placeholder) {
    return field.placeholder;
  }

  switch (field.name) {
    case "folder_id":
      return "Leave blank to sync your full Drive";
    case "branch":
      return "main";
    case "path":
      return "docs/";
    case "page_size":
    case "limit":
    case "max_results":
      return "50";
    case "query":
      return "is:unread newer_than:7d";
    case "time_min":
      return "Leave blank for upcoming events";
    default:
      return `Enter ${field.label.toLowerCase()}`;
  }
}

function getFieldDefaultValue(field: IntegrationSetupField) {
  if (field.default_value !== undefined && field.default_value !== null) {
    return String(field.default_value);
  }

  switch (field.name) {
    case "branch":
      return "main";
    case "page_size":
    case "limit":
    case "max_results":
      return "50";
    default:
      return "";
  }
}

function isOAuthIntegration(slug: string) {
  return OAUTH_INTEGRATIONS.has(slug);
}

function getOAuthButtonLabel(slug: string) {
  switch (slug) {
    case "google-drive":
    case "gmail":
    case "google-calendar":
      return "Connect with Google";
    case "github":
      return "Connect with GitHub";
    case "slack":
      return "Connect with Slack";
    case "notion":
      return "Connect with Notion";
    default:
      return "Connect Account";
  }
}

function getOAuthSetupCopy(slug: string) {
  switch (slug) {
    case "google-drive":
      return "Sign in with Google once. AverQel stores the OAuth connection securely and can read, upload, update, and delete Drive files with approval.";
    case "gmail":
      return "Sign in with Google once. AverQel stores the OAuth connection securely and can read, send, delete, and manage mail with approval.";
    case "google-calendar":
      return "Sign in with Google once. AverQel stores the OAuth connection securely and can view, create, and schedule events with approval.";
    case "github":
      return "Sign in with GitHub and approve repository access. AverQel stores the OAuth connection securely and can read, create, update, delete repo files, and manage issues.";
    case "slack":
      return "Sign in with Slack and approve workspace access. AverQel stores the OAuth connection securely and can post, update, and delete messages.";
    case "notion":
      return "Sign in with Notion and approve workspace access. AverQel stores the OAuth connection securely and can create pages and append content.";
    default:
      return "Connect your account to let AverQel store a secure OAuth connection automatically.";
  }
}

function getOAuthAvailabilityCopy(integration: Integration) {
  if (!isOAuthIntegration(integration.slug)) {
    return null;
  }

  if (integration.oauth_status?.configured) {
    return {
      label: "OAuth Ready",
      tone: "text-emerald-500",
      message: integration.oauth_status.message,
    };
  }

  return {
    label: "OAuth Missing",
    tone: "text-rose-500",
    message: integration.oauth_status?.message || "OAuth is not configured on this deployment.",
  };
}

function getQuickStartCopy(slug: string) {
  switch (slug) {
    case "web-crawler":
      return "Paste a source URL and your auth token. AverQel will crawl and index the site.";
    case "google-drive":
      return "Connect with Google once and AverQel will sync your Drive automatically. Folder ID is optional.";
    case "github":
      return "Connect with GitHub once and AverQel will index the repo directly. Branch and path are optional filters, and issues can be managed from AverQel.";
    case "slack":
      return "Connect with Slack once and AverQel will read the channel directly. Optional limits control how much history is pulled.";
    case "notion":
      return "Connect with Notion once and AverQel will fetch the page content. Page ID is the scope selector.";
    case "gmail":
      return "Connect with Google once and optionally add search filters. Leave filters blank for a broad mail sync, then manage mail from AverQel.";
    case "google-calendar":
      return "Connect with Google once and optionally add a time window. Leave it blank to start from upcoming events.";
    default:
      return "Use the minimum required scope and sign in. Optional filters are hidden below.";
  }
}

function getIntegrationDetail(slug: string): IntegrationDetail {
  switch (slug) {
    case "web-crawler":
      return {
        summary: "Crawls a website or docs hub and turns pages into indexed knowledge.",
        access: "Source URL: paste the public site or docs home you want AverQel to crawl.",
        auth: "Auth: optional unless the source is gated or rate-limited.",
        manage: "Manage: resync the source and keep the collected pages available to AverQel.",
        sync: "Sync: runs through the connector pipeline and proactive refresh cycles.",
        output: "Output: pages become connector documents the agent can reference later.",
      };
    case "google-drive":
      return {
        summary: "Connects your Google account once and syncs your Drive as a live source.",
        access:
          "Folder ID: optional. Leave it blank for full Drive access or add one folder scope in Advanced.",
        auth: "Auth: sign in with Google. AverQel stores the OAuth connection securely; no token paste is needed.",
        manage:
          "Manage: upload, update, and delete files from AverQel with the same connected account.",
        sync: "Sync: page size stays optional and controls how many files are pulled per sweep.",
        output: "Output: files land in the document pipeline and show up in the workspace.",
        author: "Google",
        connectorUrl: "https://drivemcp.googleapis.com/mcp/v1",
        tools: [
          "list_files",
          "get_file_metadata",
          "search_files",
          "download_file",
          "create_folder",
        ],
        fullDescription:
          "Connect Google Drive to AverQel to access and manage your files directly. Search across documents, folders, and shared drives, and let the AI help you organize or extract insights from your cloud storage.",
      };
    case "github":
      return {
        summary: "Indexes repo code, docs, and README content for agentic work.",
        access: "Repository URL: paste the GitHub repo link you want AverQel to follow.",
        auth: "Auth: sign in with GitHub. AverQel stores the OAuth connection securely and can use repo-scoped access.",
        manage:
          "Manage: create, update, and delete files, plus open, update, or comment on issues from AverQel.",
        sync: "Sync: branch and folder path stay optional unless you need a narrower scan.",
        output: "Output: repo content becomes connector documents and source material.",
        author: "GitHub",
        connectorUrl: "https://githubmcp.com/mcp/v1",
        tools: ["search", "get_repo", "get_contents", "create_file", "create_issue", "add_comment"],
        fullDescription:
          "Connect GitHub to AverQel to index your repositories. The AI can search through code, read documentation, help manage issues, and even assist with pull request reviews directly from the chat.",
      };
    case "slack":
      return {
        summary: "Pulls Slack channel history into the knowledge pipeline for context.",
        access: "Channel ID: paste the channel ID, not the human-readable name.",
        auth: "Auth: sign in with Slack. AverQel stores the OAuth connection securely and can use the workspace directly.",
        manage: "Manage: post, update, and delete messages from the connected channel.",
        sync: "Sync: message limit controls how much history is pulled per run.",
        output: "Output: messages become searchable pipeline items and activity signals.",
        author: "Slack",
        connectorUrl: "https://slackmcp.com/mcp/v1",
        tools: [
          "slack_read_channel",
          "slack_post_message",
          "slack_update_message",
          "slack_list_channels",
        ],
        fullDescription:
          "Connect Slack to bring your team's conversations into AverQel. Triaging channels and staying updated on project discussions becomes seamless with AI-powered summaries and direct message management.",
      };
    case "notion":
      return {
        summary: "Fetches Notion pages or databases as structured knowledge.",
        access: "Page ID: paste the page or database ID you want indexed.",
        auth: "Auth: sign in with Notion. AverQel stores the OAuth connection securely and can reuse it safely.",
        manage: "Manage: create pages and append content from AverQel when the user approves.",
        sync: "Sync: keeps the page content fresh whenever the connector runs.",
        output: "Output: Notion content feeds documents, summaries, and agent context.",
        author: "Notion",
        connectorUrl: "https://notionmcp.com/mcp/v1",
        tools: ["fetch", "create_page", "update_page", "append_content", "search_notion"],
        fullDescription:
          "Connect Notion to turn your pages and databases into structured knowledge. AverQel can fetch page content, update notes, and help you organize your workspace more effectively.",
      };
    case "gmail":
      return {
        summary: "Turns email into proactive work so the agent can triage and draft.",
        access: "Search query: optional; leave it blank for a broader mailbox sync.",
        auth: "Auth: sign in with Google. AverQel stores the OAuth connection securely and can keep working later.",
        manage: "Manage: send, delete, archive, trash, or star messages from AverQel.",
        sync: "Sync: max results stays optional and controls how many emails are pulled.",
        output: "Output: email items feed the proactive workspace and agent workflow.",
        author: "Google",
        connectorUrl: "https://gmailmcp.googleapis.com/mcp/v1",
        tools: ["create_draft", "get_thread", "list_drafts", "list_labels", "search_threads"],
        fullDescription:
          "Connect Gmail to AverQel to quickly find important emails and understand long conversations. It can search through your messages, read entire email threads to give you context, and help you stay on top of your inbox. Perfect for finding that message you remember sending, catching up on email chains you missed, or preparing for meetings.",
      };
    case "google-calendar":
      return {
        summary: "Surfaces upcoming events so AverQel can brief, remind, and schedule.",
        access: "Start time: optional ISO time to narrow the calendar pull.",
        auth: "Auth: sign in with Google. AverQel stores the OAuth connection securely and can schedule later.",
        manage: "Manage: create events and inspect free/busy directly from AverQel.",
        sync: "Sync: max results stays optional and keeps the event pull focused.",
        output: "Output: events land in the proactive timeline and morning brief flow.",
        author: "Google",
        connectorUrl: "https://calendarmcp.googleapis.com/mcp/v1",
        tools: ["list_events", "get_event", "create_event", "update_event", "list_calendars"],
        fullDescription:
          "Connect Google Calendar to AverQel to view and manage your schedule. The AI can help you plan your day, schedule meetings, and stay on top of your commitments by surfacing upcoming events and identifying potential conflicts.",
      };
    default:
      return {
        summary: "Connector details are available here so the setup stays plug-and-play.",
        access: "Use the smallest required scope field for this source.",
        auth: "Sign in with the provider account and let AverQel store the OAuth connection securely.",
        manage: "Manage: the connector can be used directly inside AverQel once linked.",
        sync: "Optional fields stay in Advanced unless the source really needs them.",
        output: "Output: the connector becomes part of AverQel' knowledge pipeline.",
      };
  }
}

function formatUtcTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date);
}

function formatUtcDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

function extractApiErrorMessage(raw: string, fallback: string): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    return fallback;
  }

  try {
    const parsed = JSON.parse(trimmed) as {
      error?: { message?: string };
      message?: string;
    };
    return parsed.error?.message || parsed.message || fallback;
  } catch {
    return trimmed || fallback;
  }
}

function renderIntegrationDetailContent(details: IntegrationDetail) {
  return (
    <div className="flex max-w-xs flex-col gap-6">
      {details.fullDescription && (
        <p className="text-foreground/75 text-sm leading-6 italic">{details.fullDescription}</p>
      )}

      {!details.fullDescription && (
        <p className="text-foreground/65 text-sm leading-6">{details.summary}</p>
      )}

      {details.tools && (
        <div className="space-y-2">
          <p className="text-foreground/40 text-[10px] font-black tracking-[0.18em] uppercase">
            Tools ({details.tools.length})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {details.tools.map((tool) => (
              <span
                key={tool}
                className="bg-primary/5 text-primary border-primary/10 rounded-md border px-2 py-0.5 text-[10px] font-bold"
              >
                {tool}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {details.author && (
          <div>
            <p className="text-foreground/40 text-[10px] font-black tracking-[0.18em] uppercase">
              Author
            </p>
            <p className="text-foreground/70 mt-1 text-sm leading-5 font-bold">{details.author}</p>
          </div>
        )}
        {details.connectorUrl && (
          <div>
            <p className="text-foreground/40 text-[10px] font-black tracking-[0.18em] uppercase">
              Connector URL
            </p>
            <p className="text-foreground/70 mt-1 font-mono text-[10px] leading-5 break-all">
              {details.connectorUrl}
            </p>
          </div>
        )}
      </div>

      <div className="space-y-3">
        <div>
          <p className="text-foreground/40 text-[10px] font-black tracking-[0.18em] uppercase">
            Deployment Details
          </p>
          <ul className="mt-2 space-y-2">
            <li className="flex gap-2">
              <span className="text-primary font-black">•</span>
              <p className="text-foreground/70 text-[11px] leading-4">{details.auth}</p>
            </li>
            <li className="flex gap-2">
              <span className="text-primary font-black">•</span>
              <p className="text-foreground/70 text-[11px] leading-4">{details.manage}</p>
            </li>
            <li className="flex gap-2">
              <span className="text-primary font-black">•</span>
              <p className="text-foreground/70 text-[11px] leading-4">{details.output}</p>
            </li>
          </ul>
        </div>
      </div>

      <div className="border-t border-white/5 pt-4">
        <p className="text-foreground/30 text-[9px] leading-4 italic">
          Only use connectors from developers you trust. AverQel does not control which tools
          developers make available and cannot verify that they will work as intended or that they
          won&apos;t change.
        </p>
      </div>
    </div>
  );
}

export default function ConnectorsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [selectedIntegration, setSelectedIntegration] = useState<Integration | null>(null);
  const [editingConnector, setEditingConnector] = useState<Connector | null>(null);
  const [connectionName, setConnectionName] = useState("");
  const [connectionFields, setConnectionFields] = useState<Record<string, string>>({});
  const [connectionCredentials, setConnectionCredentials] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [connectorDocs, setConnectorDocs] = useState<Record<string, ConnectorDocument[]>>({});
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [vitals, setVitals] = useState({
    internet: "disconnected",
    llm: "disconnected",
    web_search: "unavailable",
    sources: 0,
  });
  const selectedIntegrationOAuth = selectedIntegration
    ? isOAuthIntegration(selectedIntegration.slug)
    : false;

  const fetchData = useCallback(async () => {
    try {
      const [intRes, connRes, actRes, vitRes] = await Promise.all([
        fetchWithAuth("/integrations"),
        fetchWithAuth("/integrations/connectors"),
        fetchWithAuth("/deepspace/chats/activity"),
        fetchWithAuth("/deepspace/chats/vitals"),
      ]);

      if (intRes.ok) setIntegrations(await intRes.json());
      if (actRes.ok) setActivities((await actRes.json()) as ActivityItem[]);
      if (vitRes.ok) setVitals(await vitRes.json());
      if (connRes.ok) {
        const connectorsData = await connRes.json();
        setConnectors(connectorsData);

        // Fetch docs for each connector
        connectorsData.forEach(async (c: Connector) => {
          try {
            const docRes = await fetchWithAuth(`/integrations/connectors/${c.id}/documents`);
            if (docRes.ok) {
              const docs = (await docRes.json()) as ConnectorDocument[];
              setConnectorDocs((prev) => ({ ...prev, [c.id]: docs }));
            }
          } catch (e) {
            console.error("Failed to fetch docs for", c.id, e);
          }
        });
      }
    } catch (error) {
      console.error("Failed to fetch integration data", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setConnectionName(selectedIntegrationOAuth ? (selectedIntegration?.name ?? "") : "");
    setConnectionFields(
      (selectedIntegration?.ui_metadata.setup_fields ?? []).reduce<Record<string, string>>(
        (acc, field) => {
          const defaultValue = getFieldDefaultValue(field);
          if (defaultValue) {
            acc[field.name] = defaultValue;
          }
          return acc;
        },
        {},
      ),
    );
    setConnectionCredentials("");
    setAdvancedOpen(false);
  }, [selectedIntegration, selectedIntegrationOAuth]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    const oauthStatus = searchParams.get("oauth");
    if (!oauthStatus) {
      return;
    }

    const message = searchParams.get("message");

    if (oauthStatus === "connected") {
      toast.success(message || "Account connected successfully.");
    } else {
      toast.error(message || "Account connection failed.");
    }

    fetchData();
    router.replace("/dashboard/connectors", { scroll: false });
  }, [fetchData, router, searchParams]);

  const handleCreateConnector = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedIntegration) return;
    if (selectedIntegrationOAuth && !selectedIntegration.oauth_status?.configured) {
      toast.error(
        selectedIntegration.oauth_status?.message || "OAuth is not configured on this deployment.",
      );
      return;
    }
    setSubmitting(true);
    const setupFields = selectedIntegration.ui_metadata.setup_fields ?? [];
    const config = setupFields.reduce<Record<string, string | number>>((acc, field) => {
      const rawValue = connectionFields[field.name]?.trim() ?? "";
      if (!rawValue) {
        return acc;
      }
      acc[field.name] = field.type === "number" ? Number(rawValue) : rawValue;
      return acc;
    }, {});
    const resolvedConnectionName = selectedIntegrationOAuth
      ? connectionName.trim() || selectedIntegration.name
      : connectionName.trim();
    try {
      const res = await fetchWithAuth("/integrations/connectors", {
        method: "POST",
        body: JSON.stringify({
          name: resolvedConnectionName,
          integration_id: selectedIntegration.id,
          config,
          credentials: selectedIntegrationOAuth
            ? {}
            : connectionCredentials.trim()
              ? { credentials: connectionCredentials.trim() }
              : {},
        }),
      });
      const createText = await res.text();
      if (!res.ok) {
        throw new Error(extractApiErrorMessage(createText, `HTTP ${res.status}`));
      }
      const createdConnector = JSON.parse(createText) as Connector;
      if (selectedIntegrationOAuth) {
        const oauthRes = await fetchWithAuth(
          `/integrations/connectors/${createdConnector.id}/oauth/start`,
          {
            method: "POST",
          },
        );
        const oauthText = await oauthRes.text();
        let oauthData: {
          available?: boolean;
          authorization_url?: string | null;
          message?: string;
        } = {};
        if (oauthText) {
          try {
            oauthData = JSON.parse(oauthText) as typeof oauthData;
          } catch {
            oauthData = { message: oauthText };
          }
        }
        if (!oauthRes.ok || !oauthData.available || !oauthData.authorization_url) {
          throw new Error(
            extractApiErrorMessage(
              oauthText,
              oauthData.message || "OAuth flow could not be started.",
            ),
          );
        }
        window.location.assign(oauthData.authorization_url);
        return;
      }
      setShowAddModal(false);
      setConnectionName("");
      setConnectionFields({});
      setConnectionCredentials("");
      setSelectedIntegration(null);
      fetchData();
    } catch (error) {
      console.error("Failed to create connector", error);
      toast.error(error instanceof Error ? error.message : "Failed to create connector.");
    } finally {
      setSubmitting(false);
    }
  };

  const triggerSync = async (id: string) => {
    try {
      setConnectors((prev) => prev.map((c) => (c.id === id ? { ...c, status: "SYNCING" } : c)));
      await fetchWithAuth(`/integrations/connectors/${id}/sync`, { method: "POST" });
      fetchData();
    } catch (error) {
      console.error("Sync failed", error);
    }
  };

  const deleteConnector = async (id: string) => {
    if (
      !confirm(
        "Are you sure you want to delete this data pipeline? All ingested knowledge will be orphaned.",
      )
    )
      return;
    try {
      const res = await fetchWithAuth(`/integrations/connectors/${id}`, { method: "DELETE" });
      if (res.ok) {
        setShowSettingsModal(false);
        fetchData();
      }
    } catch (error) {
      console.error("Delete failed", error);
    }
  };

  const updateConnector = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingConnector) return;
    try {
      const res = await fetchWithAuth(`/integrations/connectors/${editingConnector.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: editingConnector.name,
          sync_frequency: editingConnector.sync_frequency,
        }),
      });
      if (res.ok) {
        setShowSettingsModal(false);
        fetchData();
      }
    } catch (error) {
      console.error("Update failed", error);
    }
  };

  const getIntegrationIcon = (slug: string) => {
    switch (slug) {
      case "web-crawler":
        return <Globe className="h-6 w-6" />;
      case "google-drive":
        return <Cloud className="h-6 w-6" />;
      case "slack":
        return <Slack className="h-6 w-6" />;
      case "github":
        return <Github className="h-6 w-6" />;
      case "notion":
        return <FileText className="h-6 w-6" />;
      case "gmail":
        return <Mail className="h-6 w-6" />;
      case "google-calendar":
        return <Calendar className="h-6 w-6" />;
      default:
        return <Cable className="h-6 w-6" />;
    }
  };

  return (
    <div className="flex flex-col gap-8 pb-10">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <DashboardSectionHeader
          icon={Network}
          title="Connectors"
          subtitle="INTELLIGENCE BRIDGE"
          actions={
            <div className="flex items-center gap-3">
              <Link
                href="/dashboard/proactive"
                prefetch={false}
                className="border-primary/20 bg-primary/5 text-primary hover:bg-primary/10 flex h-12 items-center gap-3 rounded-2xl border px-6 text-sm font-black tracking-widest uppercase transition-all hover:scale-[1.03] active:scale-95"
              >
                <Activity size={18} className="stroke-[2.5]" />
                Proactive Workspace
              </Link>
              <Link
                href="/dashboard/mcp"
                prefetch={false}
                className="border-primary/20 bg-primary/5 text-primary hover:bg-primary/10 flex h-12 items-center gap-3 rounded-2xl border px-6 text-sm font-black tracking-widest uppercase transition-all hover:scale-[1.03] active:scale-95"
              >
                <Cable size={18} className="stroke-[2.5]" />
                Official MCP Marketplace
              </Link>
              <button
                onClick={() => setShowAddModal(true)}
                className="bg-primary text-primary-foreground shadow-primary/20 flex h-12 items-center gap-3 rounded-2xl px-8 text-sm font-black tracking-widest uppercase shadow-xl transition-all hover:scale-[1.03] hover:brightness-110 active:scale-95"
              >
                <Plus size={18} className="stroke-[2.5]" />
                Add New Source
              </button>
            </div>
          }
        />
      </motion.div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <div className="theme-panel group relative overflow-hidden p-6">
          <div className="absolute top-0 right-0 p-4 opacity-10 transition-transform group-hover:scale-110">
            <Zap className="text-primary h-12 w-12" />
          </div>
          <p className="text-foreground/40 text-[10px] font-bold tracking-widest uppercase">
            Active Channels
          </p>
          <p className="text-foreground mt-1 text-3xl font-black">
            {connectors.filter((c) => normalizeStatus(c.status) === "ACTIVE").length}
          </p>
          <div className="mt-4 flex items-center gap-2 text-xs font-bold text-emerald-500">
            <div className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
            Intelligence Stream Healthy
          </div>
        </div>

        <div className="theme-panel group border-primary/20 relative col-span-1 overflow-hidden p-6 md:col-span-2">
          <div className="absolute top-0 right-0 p-4 opacity-10 transition-transform group-hover:rotate-12">
            <ShieldCheck className="text-primary h-12 w-12" />
          </div>
          <p className="text-primary flex items-center gap-2 text-[10px] font-bold tracking-widest uppercase">
            <RefreshCw size={10} className="animate-spin-slow" />
            Proactive Agent Pulse
          </p>
          <div className="mt-4 space-y-3">
            {activities.length > 0 ? (
              activities.slice(0, 3).map((act) => (
                <div key={act.id} className="flex items-center justify-between text-xs font-bold">
                  <span className="text-foreground/60 flex items-center gap-2">
                    {act.source === "gmail" ? (
                      <Mail size={12} className="text-primary" />
                    ) : act.source === "google-calendar" || act.source === "calendar" ? (
                      <Calendar size={12} className="text-primary" />
                    ) : (
                      <Zap size={12} className="text-primary" />
                    )}
                    {act.description}
                  </span>
                  <span className="text-foreground/40 text-[10px] whitespace-nowrap">
                    {formatUtcTime(act.created_at)}
                  </span>
                </div>
              ))
            ) : (
              <div className="flex items-center justify-between text-xs font-bold">
                <span className="text-foreground/60 flex items-center gap-2">
                  <Zap size={12} className="text-primary" />
                  Monitoring established pipelines...
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="theme-panel group flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <div
              className={`rounded-xl p-2 ${vitals.internet === "connected" ? "bg-emerald-500/10 text-emerald-500" : "bg-rose-500/10 text-rose-500"}`}
            >
              <Wifi size={16} />
            </div>
            <div className="flex flex-col">
              <span className="text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                Network
              </span>
              <span className="text-foreground text-xs font-bold">
                {vitals.internet === "connected" ? "Online" : "Offline"}
              </span>
            </div>
          </div>
          <div
            className={`h-2 w-2 rounded-full ${vitals.internet === "connected" ? "animate-pulse bg-emerald-500" : "bg-rose-500"}`}
          />
        </div>

        <div className="theme-panel group flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <div
              className={`rounded-xl p-2 ${vitals.llm === "connected" ? "bg-primary/10 text-primary" : "bg-rose-500/10 text-rose-500"}`}
            >
              <Cpu size={16} />
            </div>
            <div className="flex flex-col">
              <span className="text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                Intelligence
              </span>
              <span className="text-foreground text-xs font-bold">
                {vitals.llm === "connected" ? "LLM Core Linked" : "LLM Not Ready"}
              </span>
            </div>
          </div>
          <div
            className={`h-2 w-2 rounded-full ${vitals.llm === "connected" ? "bg-primary animate-pulse" : "bg-rose-500"}`}
          />
        </div>

        <div className="theme-panel group flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <div
              className={`rounded-xl p-2 ${vitals.web_search === "available" ? "bg-indigo-500/10 text-indigo-500" : "bg-foreground/5 text-foreground/20"}`}
            >
              <Search size={16} />
            </div>
            <div className="flex flex-col">
              <span className="text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                Web Engine
              </span>
              <span className="text-foreground text-xs font-bold">
                {vitals.web_search === "available" ? "Tavily Search active" : "Search Unavailable"}
              </span>
            </div>
          </div>
        </div>

        <div className="theme-panel group flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-orange-500/10 p-2 text-orange-500">
              <Network size={16} />
            </div>
            <div className="flex flex-col">
              <span className="text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                Knowledge Base
              </span>
              <span className="text-foreground text-xs font-bold">
                {vitals.sources} Pipelines Active
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-6">
        <h2 className="text-foreground/40 flex items-center gap-3 text-xs font-black tracking-[0.2em] uppercase">
          <div className="bg-primary h-4 w-1 rounded-full" />
          Established Pipelines
        </h2>

        {connectors.length === 0 && !loading ? (
          <div className="theme-panel border-2 border-dashed p-12 text-center">
            <div className="bg-foreground/5 text-foreground/20 mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-3xl">
              <Network size={32} />
            </div>
            <p className="text-foreground text-xl font-black">No Knowledge Sources</p>
            <p className="text-foreground/40 mx-auto mt-2 max-w-sm">
              Connect your first automated source to build your collective intelligence.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {connectors.map((connector) => (
              <motion.div
                key={connector.id}
                layout
                className="theme-panel group hover:border-primary/30 hover:shadow-primary/5 flex flex-col gap-4 p-5 shadow-lg transition-all"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-5">
                    <div
                      className={`rounded-2xl p-3 ${
                        normalizeStatus(connector.status) === "ACTIVE"
                          ? "bg-emerald-500/10 text-emerald-500"
                          : normalizeStatus(connector.status) === "SYNCING"
                            ? "bg-primary/10 text-primary"
                            : "bg-rose-500/10 text-rose-500"
                      }`}
                    >
                      {getIntegrationIcon(
                        integrations.find((i) => i.id === connector.integration_id)?.slug || "",
                      )}
                    </div>

                    <div className="space-y-1">
                      <h3 className="text-foreground flex items-center gap-3 text-lg font-black">
                        {connector.name}
                        {normalizeStatus(connector.status) === "SYNCING" && (
                          <RefreshCw className="text-primary h-4 w-4 animate-spin" />
                        )}
                      </h3>
                      <div className="text-foreground/40 flex items-center gap-4 text-[10px] font-bold tracking-widest uppercase">
                        <span className="flex items-center gap-1.5">
                          <Clock size={12} />
                          {connector.sync_frequency}
                        </span>
                        {connector.last_sync_at && (
                          <span className="flex items-center gap-1.5">
                            <CheckCircle2 size={12} className="text-emerald-500" />
                            {formatUtcDate(connector.last_sync_at)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <div className="mr-2 flex flex-col items-end text-right">
                      <span
                        className={`text-[10px] font-black tracking-widest uppercase ${
                          normalizeStatus(connector.status) === "ACTIVE"
                            ? "text-emerald-500"
                            : normalizeStatus(connector.status) === "SYNCING"
                              ? "text-primary"
                              : "text-rose-500"
                        }`}
                      >
                        {normalizeStatus(connector.status)}
                      </span>
                    </div>

                    <button
                      onClick={() => triggerSync(connector.id)}
                      disabled={normalizeStatus(connector.status) === "SYNCING"}
                      className="bg-foreground/5 hover:bg-primary/10 text-foreground/40 hover:text-primary flex items-center gap-3 rounded-xl px-5 py-2.5 text-xs font-bold transition-all disabled:opacity-50"
                    >
                      <RefreshCw
                        size={14}
                        className={
                          normalizeStatus(connector.status) === "SYNCING" ? "animate-spin" : ""
                        }
                      />
                      Sync Now
                    </button>

                    <button
                      onClick={() => {
                        setEditingConnector(connector);
                        setShowSettingsModal(true);
                      }}
                      className="bg-foreground/5 hover:bg-foreground/10 text-foreground/40 hover:text-foreground rounded-xl p-3 transition-all"
                    >
                      <Settings2 size={18} />
                    </button>
                  </div>
                </div>

                {connectorDocs[connector.id]?.length > 0 && (
                  <div className="space-y-3 pl-16">
                    <p className="text-foreground/20 flex items-center gap-2 text-[10px] font-black tracking-[0.2em] uppercase">
                      <FileText size={12} />
                      Intelligence Stream
                    </p>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      {connectorDocs[connector.id].slice(0, 4).map((doc) => (
                        <div
                          key={doc.id}
                          className="bg-foreground/[0.02] border-glass-border hover:border-primary/30 group/doc flex items-center justify-between rounded-xl border p-3 transition-all"
                        >
                          <div className="flex items-center gap-3 overflow-hidden">
                            <FileText size={14} className="text-foreground/20" />
                            <span className="text-foreground/60 truncate text-xs font-bold">
                              {doc.filename}
                            </span>
                          </div>
                          <button className="text-primary opacity-0 transition-all group-hover/doc:opacity-100">
                            <ExternalLink size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {connector.config?.mcp_tools_cache &&
                  connector.config.mcp_tools_cache.length > 0 && (
                    <div className="mt-2 space-y-3 pl-16">
                      <p className="text-foreground/20 flex items-center gap-2 text-[10px] font-black tracking-[0.2em] uppercase">
                        <Zap size={12} className="text-primary" />
                        Agentic Capabilities Unlocked
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {connector.config.mcp_tools_cache.map((tool) => (
                          <div
                            key={tool.name}
                            className="bg-primary/5 border-primary/10 hover:bg-primary/10 flex cursor-default items-center gap-1.5 rounded-lg border px-2.5 py-1 transition-all"
                            title={tool.description}
                          >
                            <Cpu size={10} className="text-primary" />
                            <span className="text-foreground/70 text-[9px] font-bold tracking-widest uppercase">
                              {tool.name}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-6 pt-10">
        <h2 className="text-foreground/40 flex items-center gap-3 text-xs font-black tracking-[0.2em] uppercase">
          <Zap size={16} className="text-primary" />
          Available Integrations
        </h2>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {integrations.map((int) => (
            <motion.div
              key={int.id}
              whileHover={{ y: -5 }}
              onClick={() => {
                setSelectedIntegration(int);
                setShowAddModal(true);
              }}
              className="theme-panel group hover:border-primary/50 hover:shadow-primary/10 cursor-pointer p-8 shadow-xl transition-all"
            >
              <div className="mb-8 flex items-start justify-between gap-3">
                <div className="bg-primary/10 text-primary shadow-primary/5 rounded-2xl p-4 shadow-lg transition-transform group-hover:scale-110">
                  {getIntegrationIcon(int.slug)}
                </div>
                <div className="flex items-center gap-2">
                  {getOAuthAvailabilityCopy(int) && (
                    <div
                      className={`theme-pill !bg-foreground/5 !border-foreground/10 !text-[10px] font-black tracking-widest uppercase ${getOAuthAvailabilityCopy(int)?.tone}`}
                    >
                      {getOAuthAvailabilityCopy(int)?.label}
                    </div>
                  )}
                  <div className="theme-pill !bg-foreground/5 !border-foreground/10 !text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                    STABLE
                  </div>
                  <AverQelTooltip
                    label={`${int.name} connector details`}
                    title={`${int.name} Details`}
                    content={renderIntegrationDetailContent(getIntegrationDetail(int.slug))}
                  />
                </div>
              </div>
              <h3 className="text-foreground mb-3 text-xl font-black">{int.name}</h3>
              <p className="text-foreground/40 mb-6 text-sm leading-relaxed">{int.description}</p>
              <div className="text-primary flex items-center gap-2 text-xs font-black tracking-widest uppercase opacity-0 transition-all group-hover:opacity-100">
                Connect Source <ArrowRight size={14} />
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      <Link
        href="/dashboard/proactive"
        prefetch={false}
        className="bg-primary text-primary-foreground shadow-primary/20 fixed right-5 bottom-5 z-40 inline-flex items-center gap-3 rounded-full px-5 py-3 text-[11px] font-black tracking-[0.24em] uppercase shadow-2xl transition hover:scale-[1.03] hover:brightness-110 active:scale-95"
      >
        <ShieldCheck size={14} className="stroke-[2.5]" />
        Live Proactive
      </Link>

      {/* Settings Modal */}
      <AnimatePresence>
        {showSettingsModal && editingConnector && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowSettingsModal(false)}
              className="bg-background/80 absolute inset-0 backdrop-blur-md"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: 20 }}
              className="theme-panel border-primary/20 relative w-full max-w-lg space-y-8 p-10 shadow-2xl"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-foreground text-3xl font-black">Pipeline Settings</h2>
                  <p className="text-foreground/40 mt-1 font-bold">
                    Customize your intelligence flow
                  </p>
                </div>
                <div className="bg-primary/10 text-primary shadow-primary/5 rounded-2xl p-4 shadow-lg">
                  {getIntegrationIcon(
                    integrations.find((i) => i.id === editingConnector.integration_id)?.slug || "",
                  )}
                </div>
              </div>

              <form onSubmit={updateConnector} className="space-y-6">
                <div className="space-y-2">
                  <label className="text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                    Source Name
                  </label>
                  <input
                    required
                    value={editingConnector.name}
                    onChange={(e) =>
                      setEditingConnector({ ...editingConnector, name: e.target.value })
                    }
                    className="bg-foreground/5 border-glass-border focus:ring-primary text-foreground h-14 w-full rounded-2xl px-5 font-bold transition-all outline-none focus:ring-2"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                    Sync Frequency
                  </label>
                  <select
                    value={editingConnector.sync_frequency}
                    onChange={(e) =>
                      setEditingConnector({ ...editingConnector, sync_frequency: e.target.value })
                    }
                    className="bg-foreground/5 border-glass-border focus:ring-primary text-foreground h-14 w-full appearance-none rounded-2xl px-5 font-bold transition-all outline-none focus:ring-2"
                  >
                    <option value="hourly">Hourly Pulse</option>
                    <option value="daily">Daily Batch</option>
                    <option value="weekly">Weekly Archive</option>
                    <option value="manual">Manual Trigger</option>
                  </select>
                </div>

                <div className="flex flex-col gap-4 pt-6">
                  <button
                    type="submit"
                    className="bg-primary text-primary-foreground shadow-primary/20 h-14 w-full rounded-2xl font-black tracking-widest uppercase shadow-xl transition-all hover:scale-[1.02] active:scale-95"
                  >
                    Save Configuration
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteConnector(editingConnector.id)}
                    className="bg-danger/10 hover:bg-danger text-danger border-danger/20 h-14 w-full rounded-2xl border font-black tracking-widest uppercase transition-all hover:text-white"
                  >
                    Purge Pipeline
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowSettingsModal(false)}
                    className="text-foreground/40 hover:bg-foreground/5 h-14 w-full rounded-2xl font-bold transition-all"
                  >
                    Close Panel
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Add Modal */}
      <AnimatePresence>
        {showAddModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => {
                setShowAddModal(false);
                setSelectedIntegration(null);
              }}
              className="bg-background/80 absolute inset-0 backdrop-blur-md"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: 20 }}
              className="theme-panel border-primary/20 relative w-full max-w-lg space-y-8 overflow-hidden p-10 shadow-2xl"
            >
              {!selectedIntegration ? (
                <div className="space-y-8">
                  <div>
                    <h2 className="text-foreground text-3xl font-black">Select Source</h2>
                    <p className="text-foreground/40 mt-1 font-bold">
                      Pick the platform you want to index
                    </p>
                  </div>
                  <div className="grid grid-cols-1 gap-3">
                    {integrations.map((int) => (
                      <button
                        key={int.id}
                        onClick={() => setSelectedIntegration(int)}
                        className="border-glass-border hover:border-primary/50 hover:bg-primary/5 group flex items-center gap-5 rounded-3xl border p-5 text-left transition-all"
                      >
                        <div className="bg-foreground/5 group-hover:bg-primary/20 group-hover:text-primary rounded-2xl p-4 shadow-lg shadow-black/10 transition-all">
                          {getIntegrationIcon(int.slug)}
                        </div>
                        <div>
                          <p className="text-foreground text-lg font-black">{int.name}</p>
                          <p className="text-foreground/30 text-xs font-bold tracking-widest uppercase">
                            {int.slug}
                          </p>
                        </div>
                        <ArrowRight
                          size={20}
                          className="text-foreground/10 group-hover:text-primary ml-auto transition-all"
                        />
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <form onSubmit={handleCreateConnector} className="space-y-8">
                  <div className="flex items-center gap-6">
                    <button
                      type="button"
                      onClick={() => setSelectedIntegration(null)}
                      className="bg-foreground/5 hover:bg-foreground/10 text-foreground/40 rounded-2xl p-3"
                    >
                      <ChevronLeft size={20} />
                    </button>
                    <div>
                      <h2 className="text-foreground text-3xl font-black">
                        {selectedIntegration.name}
                      </h2>
                      <p className="text-foreground/40 text-[10px] font-bold tracking-[0.2em] uppercase">
                        New Connection
                      </p>
                    </div>
                  </div>

                  <div className="space-y-6">
                    <div className="rounded-3xl border border-emerald-500/20 bg-emerald-500/10 p-4">
                      <p className="text-[10px] font-black tracking-[0.22em] text-emerald-300 uppercase">
                        Plug & Play
                      </p>
                      <p className="text-foreground/70 mt-2 text-sm leading-6">
                        {getQuickStartCopy(selectedIntegration.slug)}
                      </p>
                      {selectedIntegrationOAuth ? (
                        <p className="text-foreground/45 mt-3 text-xs leading-5">
                          AverQel will auto-name this connection after the provider consent step.
                        </p>
                      ) : null}
                    </div>

                    <div className="space-y-2">
                      {!selectedIntegrationOAuth ? (
                        <div className="space-y-2">
                          <label className="text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                            Connection Name
                          </label>
                          <input
                            required
                            value={connectionName}
                            onChange={(e) => setConnectionName(e.target.value)}
                            placeholder="e.g. Engineering Docs"
                            className="bg-foreground/5 border-glass-border focus:ring-primary text-foreground h-14 w-full rounded-2xl px-5 font-bold transition-all outline-none focus:ring-2"
                          />
                        </div>
                      ) : null}
                    </div>

                    {(selectedIntegration.ui_metadata.setup_fields ?? [])
                      .filter(isPrimarySetupField)
                      .map((field) => (
                        <div key={field.name} className="space-y-2">
                          <label className="text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                            {field.label}
                          </label>
                          {field.help_text ? (
                            <p className="text-foreground/35 text-[11px] leading-5">
                              {field.help_text}
                            </p>
                          ) : null}
                          {field.type === "textarea" ? (
                            <textarea
                              required={field.required}
                              value={connectionFields[field.name] ?? ""}
                              onChange={(event) =>
                                setConnectionFields((prev) => ({
                                  ...prev,
                                  [field.name]: event.target.value,
                                }))
                              }
                              placeholder={getFieldPlaceholder(field)}
                              className="bg-foreground/5 border-glass-border focus:ring-primary text-foreground min-h-28 w-full rounded-2xl px-5 py-4 font-bold transition-all outline-none focus:ring-2"
                            />
                          ) : (
                            <input
                              required={field.required}
                              type={field.type === "number" ? "number" : field.type}
                              value={connectionFields[field.name] ?? ""}
                              onChange={(event) =>
                                setConnectionFields((prev) => ({
                                  ...prev,
                                  [field.name]: event.target.value,
                                }))
                              }
                              placeholder={getFieldPlaceholder(field)}
                              className="bg-foreground/5 border-glass-border focus:ring-primary text-foreground h-14 w-full rounded-2xl px-5 font-bold transition-all outline-none focus:ring-2"
                            />
                          )}
                        </div>
                      ))}

                    {selectedIntegrationOAuth ? (
                      <div className="rounded-3xl border border-cyan-500/20 bg-cyan-500/10 p-5">
                        <p className="text-[10px] font-black tracking-[0.22em] text-cyan-300 uppercase">
                          Account Login
                        </p>
                        <p className="text-foreground/70 mt-2 text-sm leading-6">
                          {getOAuthSetupCopy(selectedIntegration.slug)}
                        </p>
                        {!selectedIntegration.oauth_status?.configured && (
                          <p className="mt-3 text-xs leading-5 font-bold text-rose-400">
                            {selectedIntegration.oauth_status?.message ||
                              "OAuth is not configured on this deployment."}
                          </p>
                        )}
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <label className="text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                          Authentication Secret / OAuth JSON
                        </label>
                        <p className="text-foreground/35 text-[11px] leading-5">
                          Paste the smallest thing that proves access: a token, PAT, service account
                          JSON, or OAuth user JSON.
                        </p>
                        <textarea
                          value={connectionCredentials}
                          onChange={(e) => setConnectionCredentials(e.target.value)}
                          placeholder="Paste your credential here"
                          className="bg-foreground/5 border-glass-border focus:ring-primary text-foreground min-h-28 w-full rounded-2xl px-5 py-4 font-bold transition-all outline-none focus:ring-2"
                        />
                      </div>
                    )}

                    {(selectedIntegration.ui_metadata.setup_fields ?? []).filter(
                      (field) => !isPrimarySetupField(field),
                    ).length > 0 && (
                      <div className="rounded-3xl border border-white/8 bg-white/[0.02] p-4">
                        <button
                          type="button"
                          onClick={() => setAdvancedOpen((value) => !value)}
                          className="flex w-full items-center justify-between gap-4 text-left"
                        >
                          <div>
                            <p className="text-foreground text-sm font-black tracking-widest uppercase">
                              Advanced settings
                            </p>
                            <p className="text-foreground/35 mt-1 text-[11px] leading-5">
                              Optional filters, limits, or scope hints. Leave them blank for the
                              simplest setup.
                            </p>
                          </div>
                          <span className="theme-pill text-foreground/55 border-white/10 bg-white/[0.03]">
                            {advancedOpen ? "Hide" : "Show"}
                          </span>
                        </button>

                        <AnimatePresence initial={false}>
                          {advancedOpen ? (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              className="mt-4 space-y-4 overflow-hidden"
                            >
                              {(selectedIntegration.ui_metadata.setup_fields ?? [])
                                .filter((field) => !isPrimarySetupField(field))
                                .map((field) => (
                                  <div key={field.name} className="space-y-2">
                                    <label className="text-foreground/40 text-[10px] font-black tracking-widest uppercase">
                                      {field.label}
                                    </label>
                                    {field.help_text ? (
                                      <p className="text-foreground/35 text-[11px] leading-5">
                                        {field.help_text}
                                      </p>
                                    ) : null}
                                    {field.type === "textarea" ? (
                                      <textarea
                                        required={field.required}
                                        value={connectionFields[field.name] ?? ""}
                                        onChange={(event) =>
                                          setConnectionFields((prev) => ({
                                            ...prev,
                                            [field.name]: event.target.value,
                                          }))
                                        }
                                        placeholder={getFieldPlaceholder(field)}
                                        className="bg-foreground/5 border-glass-border focus:ring-primary text-foreground min-h-28 w-full rounded-2xl px-5 py-4 font-bold transition-all outline-none focus:ring-2"
                                      />
                                    ) : (
                                      <input
                                        required={field.required}
                                        type={field.type === "number" ? "number" : field.type}
                                        value={connectionFields[field.name] ?? ""}
                                        onChange={(event) =>
                                          setConnectionFields((prev) => ({
                                            ...prev,
                                            [field.name]: event.target.value,
                                          }))
                                        }
                                        placeholder={getFieldPlaceholder(field)}
                                        className="bg-foreground/5 border-glass-border focus:ring-primary text-foreground h-14 w-full rounded-2xl px-5 font-bold transition-all outline-none focus:ring-2"
                                      />
                                    )}
                                  </div>
                                ))}
                            </motion.div>
                          ) : null}
                        </AnimatePresence>
                      </div>
                    )}
                  </div>

                  <div className="flex gap-4 pt-6">
                    <button
                      type="button"
                      onClick={() => {
                        setShowAddModal(false);
                        setSelectedIntegration(null);
                      }}
                      className="text-foreground/40 hover:bg-foreground/5 h-14 flex-1 rounded-2xl font-black tracking-widest uppercase transition-all"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={
                        submitting ||
                        (selectedIntegrationOAuth && !selectedIntegration.oauth_status?.configured)
                      }
                      className="bg-primary text-primary-foreground shadow-primary/20 h-14 flex-1 rounded-2xl font-black tracking-widest uppercase shadow-xl transition-all hover:scale-[1.02] active:scale-95 disabled:opacity-50"
                    >
                      {submitting
                        ? "Deploying..."
                        : selectedIntegrationOAuth
                          ? selectedIntegration.oauth_status?.configured
                            ? getOAuthButtonLabel(selectedIntegration.slug)
                            : "OAuth Not Configured"
                          : "Connect"}
                    </button>
                  </div>
                  {selectedIntegrationOAuth && !selectedIntegration.oauth_status?.configured && (
                    <p className="-mt-2 text-xs leading-5 font-bold text-rose-400">
                      Add the provider OAuth client configuration in the backend env, restart the
                      API, then try again.
                    </p>
                  )}
                </form>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
