"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  Copy,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  KeyRound,
  Save,
  Trash2,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import { useAuth } from "@/app/context/AuthContext";
import { hasAdminRole, normalizeRole } from "@/lib/roles";
import { averqelConfirm, averqelPrompt } from "@/app/components/ui/AverQelDialogHost";
import toast from "react-hot-toast";
import SavedViewsPanel from "./SavedViewsPanel";
import ClassificationRulesPanel from "./ClassificationRulesPanel";
import AutomationSchedulesPanel from "./AutomationSchedulesPanel";
import SmartCollectionsPanel from "./SmartCollectionsPanel";

type Item = Record<string, unknown> & {
  id: string;
  name?: string;
  color?: string;
  usage_count?: number;
};
type DocumentItem = {
  document_id: string;
  filename: string;
  status: string;
  quarantined?: boolean;
};
type PageKind =
  | "tags"
  | "folders"
  | "saved-views"
  | "classification-rules"
  | "automation-schedules"
  | "webhooks"
  | "smart-collections";

const pageMeta: Record<
  PageKind,
  { title: string; description: string; path: string; admin?: boolean; editor?: boolean }
> = {
  tags: {
    title: "Tags",
    description: "Create reusable labels and apply them to selected documents.",
    path: "/documents/organization/tags",
  },
  folders: {
    title: "Folders",
    description: "Manage your document folder tree and move selected files into a folder.",
    path: "/documents/organization/folders",
  },
  "saved-views": {
    title: "Saved Views",
    description: "Save repeatable document filters and reopen them as live views.",
    path: "/documents/organization/saved-views",
    editor: true,
  },
  "classification-rules": {
    title: "Classification Rules",
    description: "Automatically classify new documents with filename and content rules.",
    path: "/documents/organization/classification-rules",
    editor: true,
  },
  "automation-schedules": {
    title: "Automation Schedules",
    description: "Run recurring classification and processing maintenance safely.",
    path: "/documents/organization/automation-schedules",
    editor: true,
  },
  webhooks: {
    title: "Webhooks",
    description: "Manage signed external notifications and inspect delivery attempts.",
    path: "/documents/organization/webhooks",
    admin: true,
  },
  "smart-collections": {
    title: "Smart Collections",
    description: "Dynamic document groups that recalculate from live rules.",
    path: "/documents/organization/smart-collections",
    admin: true,
  },
};

function apiPath(kind: PageKind) {
  return kind === "webhooks" ? "/documents/webhooks" : `/documents/organization/${kind}`;
}

const tagColorOptions = [
  ["emerald", "Emerald"],
  ["blue", "Blue"],
  ["violet", "Violet"],
  ["amber", "Amber"],
  ["rose", "Rose"],
] as const;

const webhookEventOptions = [
  ["document.indexed", "Document indexed"],
  ["document.failed", "Document failed"],
  ["document.status.updated", "Document status updated"],
] as const;

function RoundedColorSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = tagColorOptions.find(([option]) => option === value)?.[1] ?? "Emerald";

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label="Tag color"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="theme-input flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-sm"
      >
        {selected}
        <ChevronDown size={15} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open ? (
        <div
          role="listbox"
          className="bg-background border-primary/25 absolute inset-x-0 top-full z-50 mt-1 overflow-hidden rounded-xl border p-1 shadow-xl"
        >
          {tagColorOptions.map(([option, label]) => (
            <button
              key={option}
              type="button"
              role="option"
              aria-selected={option === value}
              onClick={() => {
                onChange(option);
                setOpen(false);
              }}
              className={`w-full rounded-lg px-3 py-2 text-left text-sm ${option === value ? "bg-primary/10 text-primary" : "text-foreground hover:bg-primary/5"}`}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function OrganizationPageClient({ kind }: { kind: PageKind }) {
  const { user, loading } = useAuth();
  const roles = user?.roles ?? [];
  const admin = hasAdminRole(roles);
  const editor = admin || roles.some((role) => normalizeRole(role) === "editor");
  const meta = pageMeta[kind];
  const allowed = (!meta.admin && !meta.editor) || (meta.admin ? admin : editor);
  const [items, setItems] = useState<Item[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [selectedTagIds, setSelectedTagIds] = useState<Set<string>>(new Set());
  const [tagAction, setTagAction] = useState<"add" | "remove">("add");
  const [tagActionMenuOpen, setTagActionMenuOpen] = useState(false);
  const tagActionButtonRef = useRef<HTMLButtonElement>(null);
  const [tagActionMenuPosition, setTagActionMenuPosition] = useState({
    top: 0,
    left: 0,
    width: 176,
  });
  const [documentTags, setDocumentTags] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [tagColor, setTagColor] = useState("emerald");
  const [endpoint, setEndpoint] = useState("");
  const [webhookEventTypes, setWebhookEventTypes] = useState<string[]>(
    webhookEventOptions.map(([value]) => value),
  );
  const [deliveries, setDeliveries] = useState<Record<string, Item[]>>({});
  const [deliveryCursors, setDeliveryCursors] = useState<Record<string, string | null>>({});
  const [secret, setSecret] = useState<string | null>(null);
  const disabledAlertsShown = useRef<Set<string>>(new Set());

  const load = useCallback(async () => {
    if (!allowed) return;
    setBusy(true);
    try {
      const response = (await fetchWithAuth(apiPath(kind))) as Response;
      if (!response.ok) throw new Error("Could not load this workspace.");
      const payload = await response.json();
      if (kind === "webhooks" && Array.isArray(payload)) {
        payload.forEach((webhook: Item) => {
          if (webhook.disabled_reason && !disabledAlertsShown.current.has(webhook.id)) {
            disabledAlertsShown.current.add(webhook.id);
            toast.error(`Webhook disabled: ${String(webhook.disabled_reason)}`);
          }
        });
      }
      setItems((kind === "webhooks" ? payload : (payload.items ?? [])) as Item[]);
      if (kind === "tags" || kind === "folders") {
        const docResponse = (await fetchWithAuth("/documents")) as Response;
        if (docResponse.ok)
          setDocuments(((await docResponse.json()).items ?? []) as DocumentItem[]);
        if (kind === "tags") {
          const assignmentsResponse = (await fetchWithAuth(
            "/documents/organization/tags/assignments",
          )) as Response;
          if (assignmentsResponse.ok) {
            const assignmentItems = ((await assignmentsResponse.json()).items ?? []) as Array<{
              document_id: string;
              tag_ids: string[];
            }>;
            setDocumentTags(
              Object.fromEntries(assignmentItems.map((item) => [item.document_id, item.tag_ids])),
            );
          }
        }
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load this workspace.");
    } finally {
      setBusy(false);
    }
  }, [allowed, kind]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  const create = async () => {
    let payload: Record<string, unknown>;
    if (kind === "tags") payload = { name: name.trim(), color: tagColor };
    else if (kind === "folders" || kind === "saved-views") payload = { name: name.trim() };
    else if (kind === "webhooks")
      payload = {
        endpoint_url: endpoint.trim(),
        event_types: webhookEventTypes,
      };
    else payload = { name: name.trim() };
    if ((payload.name === "" || payload.endpoint_url === "") && kind !== "webhooks") {
      toast.error("A name is required.");
      return;
    }
    if (kind === "webhooks" && !endpoint.trim()) {
      toast.error("An HTTPS endpoint is required.");
      return;
    }
    if (kind === "webhooks" && webhookEventTypes.length === 0) {
      toast.error("Select at least one event type.");
      return;
    }
    setBusy(true);
    try {
      const response = (await fetchWithAuth(apiPath(kind), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })) as Response;
      if (!response.ok) throw new Error((await response.text()) || "Could not create item.");
      const result = await response.json();
      setItems((current) => [...current, result]);
      setName("");
      setEndpoint("");
      if (result.secret) setSecret(String(result.secret));
      toast.success(`${meta.title.slice(0, -1)} created.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create item.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    const item = items.find((entry) => entry.id === id);
    const usage = kind === "tags" ? Number(item?.usage_count ?? 0) : 0;
    if (
      !(await averqelConfirm(
        `Delete this ${meta.title.toLowerCase().replace(/s$/, "")}?${usage ? `\n\nIt is currently applied to ${usage} document${usage === 1 ? "" : "s"}. Those assignments will also be removed.` : ""}`,
      ))
    )
      return;
    const response = (await fetchWithAuth(`${apiPath(kind)}/${id}`, {
      method: "DELETE",
    })) as Response;
    if (response.ok) {
      setItems((current) => current.filter((item) => item.id !== id));
      toast.success("Deleted.");
    } else toast.error("Delete was not permitted.");
  };

  const applySelection = async () => {
    if (!selected.size || kind !== "tags" || !selectedTagIds.size) return;
    const response = (await fetchWithAuth(
      `/documents/bulk/${tagAction === "add" ? "tag" : "untag"}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: [...selected], tag_ids: [...selectedTagIds] }),
      },
    )) as Response;
    if (response.ok) {
      setDocumentTags((current) => {
        const next = { ...current };
        selected.forEach((documentId) => {
          next[documentId] =
            tagAction === "add"
              ? [...new Set([...(next[documentId] ?? []), ...selectedTagIds])]
              : (next[documentId] ?? []).filter((tagId) => !selectedTagIds.has(tagId));
        });
        return next;
      });
      toast.success(
        `${selectedTagIds.size} tag${selectedTagIds.size === 1 ? "" : "s"} ${tagAction === "add" ? "applied to" : "removed from"} ${selected.size} document${selected.size === 1 ? "" : "s"}.`,
      );
    } else toast.error("Could not apply selected tags.");
  };

  const editTag = async (item: Item) => {
    const name = await averqelPrompt("Tag name", String(item.name ?? ""));
    if (!name?.trim()) return;
    const color =
      (
        await averqelPrompt(
          "Tag color (emerald, blue, violet, amber, rose)",
          String(item.color ?? "emerald"),
        )
      )
        ?.trim()
        .toLowerCase() || "emerald";
    if (!["emerald", "blue", "violet", "amber", "rose"].includes(color)) {
      toast.error("Choose a supported tag color.");
      return;
    }
    const response = (await fetchWithAuth(`/documents/organization/tags/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim(), color }),
    })) as Response;
    if (response.ok) {
      const updated = await response.json();
      setItems((current) => current.map((entry) => (entry.id === item.id ? updated : entry)));
      toast.success("Tag updated.");
    } else toast.error("Could not update tag.");
  };

  const loadDeliveries = async (id: string, cursor?: string | null, append = false) => {
    const response = (await fetchWithAuth(
      `/documents/webhooks/${id}/deliveries?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    )) as Response;
    if (response.ok) {
      const payload = await response.json();
      setDeliveries((current) => ({
        ...current,
        [id]: append ? [...(current[id] ?? []), ...payload] : payload,
      }));
      setDeliveryCursors((current) => ({ ...current, [id]: response.headers.get("x-next-cursor") }));
    }
  };

  const updateWebhook = async (item: Item) => {
    const nextEndpoint = await averqelPrompt(
      "Webhook HTTPS endpoint",
      String(item.endpoint_url ?? ""),
    );
    if (!nextEndpoint?.trim()) return;
    const eventTypes = await averqelPrompt(
      "Event types (comma separated)",
      Array.isArray(item.event_types) ? (item.event_types as string[]).join(", ") : webhookEventTypes.join(", "),
    );
    if (!eventTypes?.trim()) return;
    const selectedEventTypes = eventTypes.split(",").map((value) => value.trim()).filter(Boolean);
    if (selectedEventTypes.some((value) => !webhookEventOptions.some(([option]) => option === value))) {
      toast.error("Choose only supported webhook event types.");
      return;
    }
    const response = (await fetchWithAuth(`/documents/webhooks/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint_url: nextEndpoint.trim(), event_types: selectedEventTypes }),
    })) as Response;
    if (response.ok) {
      const updated = await response.json();
      setItems((current) => current.map((entry) => (entry.id === item.id ? updated : entry)));
      toast.success("Webhook updated.");
    } else toast.error("Could not update webhook.");
  };

  const rotateWebhookSecret = async (id: string) => {
    const response = (await fetchWithAuth(`/documents/webhooks/${id}/rotate-secret`, {
      method: "POST",
    })) as Response;
    if (response.ok) {
      const updated = await response.json();
      setItems((current) => current.map((entry) => (entry.id === id ? updated : entry)));
      if (updated.secret) setSecret(String(updated.secret));
      toast.success("Webhook secret rotated. Update the receiving service now.");
    } else toast.error("Could not rotate webhook secret.");
  };

  const retryDelivery = async (webhookId: string, deliveryId: string) => {
    const response = (await fetchWithAuth(
      `/documents/webhooks/${webhookId}/deliveries/${deliveryId}/retry`,
      { method: "POST" },
    )) as Response;
    if (response.ok) {
      await loadDeliveries(webhookId);
      toast.success("Delivery retry queued.");
    } else toast.error("Could not retry delivery.");
  };

  const toggleWebhook = async (item: Item) => {
    const response = (await fetchWithAuth(`/documents/webhooks/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: !Boolean(item.active) }),
    })) as Response;
    if (response.ok) {
      const updated = await response.json();
      setItems((current) => current.map((entry) => (entry.id === item.id ? updated : entry)));
      toast.success(updated.active ? "Webhook resumed." : "Webhook paused.");
    } else toast.error("Could not change webhook state.");
  };

  const testWebhook = async (id: string) => {
    const response = (await fetchWithAuth(`/documents/webhooks/${id}/test`, {
      method: "POST",
    })) as Response;
    if (response.ok) {
      await loadDeliveries(id);
      toast.success("Signed test delivery queued.");
    } else toast.error("Could not queue test delivery.");
  };

  const tagActionOverlay =
    kind === "tags" && tagActionMenuOpen && typeof document !== "undefined"
      ? createPortal(
          <div
            role="listbox"
            aria-label="Tag action"
            style={{
              position: "fixed",
              top: tagActionMenuPosition.top,
              left: tagActionMenuPosition.left,
              width: tagActionMenuPosition.width,
            }}
            className="theme-panel border-primary/25 pointer-events-auto z-[99999] overflow-hidden rounded-xl border p-1 shadow-2xl"
          >
            <button
              type="button"
              role="option"
              aria-selected={tagAction === "add"}
              onClick={() => {
                setTagAction("add");
                setTagActionMenuOpen(false);
              }}
              className={`block w-full rounded-lg px-3 py-2 text-left text-xs font-bold ${tagAction === "add" ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-primary/10"}`}
            >
              Add selected tags
            </button>
            <button
              type="button"
              role="option"
              aria-selected={tagAction === "remove"}
              onClick={() => {
                setTagAction("remove");
                setTagActionMenuOpen(false);
              }}
              className={`block w-full rounded-lg px-3 py-2 text-left text-xs font-bold ${tagAction === "remove" ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-primary/10"}`}
            >
              Remove selected tags
            </button>
          </div>,
          document.body,
        )
      : null;

  if (loading) return null;
  if (!allowed)
    return (
      <div className="theme-panel p-8">
        <h1 className="text-xl font-bold">Feature unavailable</h1>
        <p className="text-muted-foreground mt-2">
          This Documents Hub feature is not available for your current plan.
        </p>
      </div>
    );
  if (kind === "folders") return <FolderExplorer />;
  if (kind === "saved-views") return <SavedViewsPanel />;
  if (kind === "classification-rules") return <ClassificationRulesPanel />;
  if (kind === "automation-schedules") return <AutomationSchedulesPanel />;
  if (kind === "smart-collections") return <SmartCollectionsPanel />;

  return (
    <main className="documents-theme-scope mx-auto w-full max-w-[1500px] space-y-6 p-4 md:p-8">
      {tagActionOverlay}
      <Link
        href="/dashboard/documents"
        className="text-muted-foreground hover:text-primary inline-flex items-center gap-2 text-xs font-bold"
      >
        <ArrowLeft size={15} /> Documents Hub
      </Link>
      <header className="theme-panel flex flex-wrap items-center justify-between gap-4 p-6">
        <div>
          <p className="text-primary text-[10px] font-black tracking-[0.2em] uppercase">
            Documents Hub / Organization
          </p>
          <h1 className="text-foreground mt-2 text-2xl font-black">{meta.title}</h1>
          <p className="text-muted-foreground mt-2 text-sm">{meta.description}</p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="theme-pill flex items-center gap-2 px-4 py-2 text-xs font-bold"
        >
          <RefreshCw size={14} className={busy ? "animate-spin" : ""} /> Refresh
        </button>
      </header>
      <section className="grid gap-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div className="theme-panel p-6">
          <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
            Create and configure
          </h2>
          <div className="mt-4 space-y-3">
            {kind !== "webhooks" ? (
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={`${meta.title.slice(0, -1)} name`}
                className="theme-input w-full rounded-xl px-3 py-3 text-sm"
              />
            ) : (
              <input
                value={endpoint}
                onChange={(event) => setEndpoint(event.target.value)}
                placeholder="https://example.com/events"
                className="theme-input w-full rounded-xl px-3 py-3 text-sm"
              />
            )}
            {kind === "webhooks" ? (
              <fieldset className="border-glass-border rounded-xl border p-3">
                <legend className="text-muted-foreground px-1 text-[10px] font-black uppercase">
                  Events to deliver
                </legend>
                <div className="space-y-2">
                  {webhookEventOptions.map(([value, label]) => (
                    <label key={value} className="text-foreground flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={webhookEventTypes.includes(value)}
                        onChange={(event) =>
                          setWebhookEventTypes((current) =>
                            event.target.checked
                              ? [...new Set([...current, value])]
                              : current.filter((item) => item !== value),
                          )
                        }
                        className="accent-primary"
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : null}
            {kind === "tags" ? (
              <RoundedColorSelect value={tagColor} onChange={setTagColor} />
            ) : null}
            <button
              type="button"
              onClick={() => void create()}
              disabled={busy}
              className="bg-primary text-primary-foreground flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-xs font-black uppercase disabled:opacity-50"
            >
              <Plus size={15} /> Create
            </button>
          </div>
        </div>
        <div className="theme-panel p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
              Configured {meta.title}
            </h2>
            <span className="text-muted-foreground text-xs">{items.length} total</span>
          </div>
          <div className="mt-4 space-y-2">
            {items.length ? (
              items.map((item) => (
                <div
                  key={item.id}
                  className="border-glass-border bg-background/30 rounded-xl border p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-foreground truncate text-sm font-bold">
                        {String(item.name ?? item.endpoint_url ?? "Unnamed")}
                      </p>
                      {kind === "tags" ? (
                        <p className="text-muted-foreground mt-1 text-[10px]">
                          {String(item.usage_count ?? 0)} document
                          {Number(item.usage_count ?? 0) === 1 ? "" : "s"} ·{" "}
                          {String(item.color ?? "emerald")}
                        </p>
                      ) : null}
                      {kind === "webhooks" ? (
                        <p className="text-muted-foreground mt-1 text-[10px]">
                          {item.active ? "Active" : "Paused"} · {String(item.failure_count ?? 0)}{" "}
                          consecutive failures
                        </p>
                      ) : null}
                      {kind === "webhooks" && Array.isArray(item.event_types) ? (
                        <p className="text-muted-foreground mt-1 text-[10px]">
                          Events: {(item.event_types as string[]).join(", ") || "none"}
                        </p>
                      ) : null}
                      {item.match_count !== undefined ? (
                        <p className="text-primary mt-1 text-xs">
                          {String(item.match_count)} matching documents
                        </p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {kind === "tags" ? (
                        <button
                          type="button"
                          onClick={() => void editTag(item)}
                          aria-label={`Edit ${item.name ?? "tag"}`}
                          className="theme-pill p-2"
                        >
                          <Pencil size={14} />
                        </button>
                      ) : null}
                      {kind === "webhooks" ? (
                        <>
                          <button
                            type="button"
                            onClick={() => void updateWebhook(item)}
                            aria-label="Edit webhook"
                            className="theme-pill p-2"
                          >
                            <Pencil size={14} />
                          </button>
                          <button
                            type="button"
                            onClick={() => void toggleWebhook(item)}
                            aria-label={item.active ? "Pause webhook" : "Resume webhook"}
                            className="theme-pill p-2"
                          >
                            {item.active ? (
                              <span className="text-[10px] font-black">Ⅱ</span>
                            ) : (
                              <Play size={14} />
                            )}
                          </button>
                          <button
                            type="button"
                            onClick={() => void testWebhook(item.id)}
                            className="theme-pill flex items-center gap-1 px-2 py-2 text-[10px] font-bold"
                          >
                            <Play size={12} /> Test
                          </button>
                          <button
                            type="button"
                            onClick={() => void rotateWebhookSecret(item.id)}
                            aria-label="Rotate webhook secret"
                            className="theme-pill p-2"
                          >
                            <KeyRound size={14} />
                          </button>
                        </>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => void remove(item.id)}
                        aria-label={`Delete ${meta.title} item`}
                        className="text-danger hover:bg-danger/10 rounded-lg p-2"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                  {kind === "webhooks" ? (
                    <>
                      <button
                        type="button"
                        onClick={() => void loadDeliveries(item.id)}
                        className="text-primary mt-3 text-[10px] font-bold uppercase"
                      >
                        Refresh delivery history
                      </button>
                      {deliveries[item.id]?.length ? (
                        <div className="mt-3 space-y-2">
                          {deliveries[item.id].map((delivery) => (
                            <div
                              key={delivery.id}
                              className="border-glass-border bg-background/30 rounded-lg border p-3 text-[10px]"
                            >
                              <div className="grid gap-1 sm:grid-cols-4">
                                <span className="font-bold">{String(delivery.event_type)}</span>
                                <span>
                                  {String(delivery.status)} · {String(delivery.attempt_count)}{" "}
                                  attempts
                                </span>
                                <span>HTTP {String(delivery.response_status ?? "—")}</span>
                                <span
                                  className="text-muted-foreground truncate"
                                  title={String(delivery.error_message ?? "")}
                                >
                                  {String(delivery.error_message ?? "No error")}
                                </span>
                                {String(delivery.status) !== "delivered" ? (
                                  <button
                                    type="button"
                                    onClick={() => void retryDelivery(item.id, delivery.id)}
                                    className="text-primary text-left font-bold uppercase"
                                  >
                                    Retry
                                  </button>
                                ) : null}
                              </div>
                              {Array.isArray(delivery.attempt_history) ? (
                                <div className="border-primary/10 mt-2 border-t pt-2">
                                  <p className="text-primary mb-1 font-bold uppercase">
                                    Retry timeline
                                  </p>
                                  <div className="flex flex-wrap gap-2">
                                    {(
                                      delivery.attempt_history as Array<Record<string, unknown>>
                                    ).map((attempt, index) => (
                                      <span
                                        key={`${delivery.id}-${index}`}
                                        className="bg-primary/5 rounded-md px-2 py-1"
                                      >
                                        #{String(attempt.attempt ?? index + 1)}{" "}
                                        {String(attempt.status ?? "unknown")}{" "}
                                        {attempt.response_status
                                          ? `· HTTP ${String(attempt.response_status)}`
                                          : ""}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              ) : null}
                            </div>
                          ))}
                          {deliveryCursors[item.id] ? (
                            <button
                              type="button"
                              onClick={() => void loadDeliveries(item.id, deliveryCursors[item.id], true)}
                              className="text-primary text-[10px] font-bold uppercase"
                            >
                              Load more history
                            </button>
                          ) : null}
                        </div>
                      ) : (
                        <p className="text-muted-foreground mt-2 text-[10px]">
                          No delivery attempts loaded.
                        </p>
                      )}
                      {item.disabled_reason ? (
                        <p className="text-danger mt-2 rounded-lg border border-red-300/30 bg-red-500/5 p-2 text-[10px] font-bold">
                          Webhook disabled: {String(item.disabled_reason)}
                        </p>
                      ) : null}
                    </>
                  ) : null}
                </div>
              ))
            ) : (
              <p className="text-muted-foreground py-10 text-center text-sm">
                Nothing configured yet.
              </p>
            )}
          </div>
        </div>
      </section>
      {kind === "tags" ? (
        <section className="theme-panel relative z-0 overflow-visible p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-foreground text-sm font-black tracking-wider uppercase">
                Apply tags to documents
              </h2>
              <p className="text-muted-foreground mt-1 text-xs">
                Select documents and tags, then apply the action.
              </p>
              <p className="text-primary mt-2 text-xs font-black" aria-live="polite">
                {selected.size} document{selected.size === 1 ? "" : "s"} selected ·{" "}
                {selectedTagIds.size} tag{selectedTagIds.size === 1 ? "" : "s"} selected
              </p>
              <div className="relative z-[100] mt-3 flex flex-wrap items-center gap-2 overflow-visible">
                <div className="relative z-[110]">
                  <button
                    ref={tagActionButtonRef}
                    type="button"
                    aria-haspopup="listbox"
                    aria-expanded={tagActionMenuOpen}
                    onClick={() => {
                      const rect = tagActionButtonRef.current?.getBoundingClientRect();
                      if (rect)
                        setTagActionMenuPosition({
                          top: rect.bottom + 6,
                          left: rect.left,
                          width: Math.max(rect.width, 176),
                        });
                      setTagActionMenuOpen((open) => !open);
                    }}
                    className="theme-input flex min-w-44 items-center justify-between gap-3 rounded-xl px-3 py-2 text-xs font-bold"
                  >
                    <span>
                      {tagAction === "add" ? "Add selected tags" : "Remove selected tags"}
                    </span>
                    <ChevronDown
                      size={14}
                      className={`transition-transform ${tagActionMenuOpen ? "rotate-180" : ""}`}
                    />
                  </button>
                  {tagActionMenuOpen ? (
                    <div
                      role="listbox"
                      aria-label="Tag action"
                      style={{
                        top: tagActionMenuPosition.top,
                        left: tagActionMenuPosition.left,
                        width: tagActionMenuPosition.width,
                      }}
                      className="theme-panel border-primary/25 pointer-events-auto fixed z-[9999] overflow-hidden rounded-xl border p-1 shadow-2xl"
                    >
                      <button
                        type="button"
                        role="option"
                        aria-selected={tagAction === "add"}
                        onClick={() => {
                          setTagAction("add");
                          setTagActionMenuOpen(false);
                        }}
                        className={`block w-full rounded-lg px-3 py-2 text-left text-xs font-bold ${tagAction === "add" ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-primary/10"}`}
                      >
                        Add selected tags
                      </button>
                      <button
                        type="button"
                        role="option"
                        aria-selected={tagAction === "remove"}
                        onClick={() => {
                          setTagAction("remove");
                          setTagActionMenuOpen(false);
                        }}
                        className={`block w-full rounded-lg px-3 py-2 text-left text-xs font-bold ${tagAction === "remove" ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-primary/10"}`}
                      >
                        Remove selected tags
                      </button>
                    </div>
                  ) : null}
                </div>
                {items.map((item) => {
                  const isSelected = selectedTagIds.has(item.id);
                  return (
                    <label
                      key={item.id}
                      className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-2 text-xs font-bold transition-all duration-200 ${isSelected ? "border-primary bg-primary text-primary-foreground ring-primary/30 shadow-[0_0_16px_rgba(16,185,129,0.35)] ring-2" : "border-glass-border bg-background/60 text-foreground/70 hover:border-primary/60 hover:text-primary"}`}
                    >
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={isSelected}
                        onChange={() =>
                          setSelectedTagIds((current) => {
                            const next = new Set(current);
                            if (next.has(item.id)) next.delete(item.id);
                            else next.add(item.id);
                            return next;
                          })
                        }
                      />
                      {isSelected ? <Check size={13} strokeWidth={3} /> : null}
                      <span>{String(item.name ?? "Unnamed")}</span>
                    </label>
                  );
                })}
              </div>
            </div>
            <button
              type="button"
              onClick={() => void applySelection()}
              disabled={!selected.size || !selectedTagIds.size}
              className={`flex h-10 items-center gap-2 rounded-xl px-4 py-2 text-xs font-black transition-all ${selected.size && selectedTagIds.size ? "bg-primary text-primary-foreground shadow-[0_0_18px_rgba(16,185,129,0.3)] hover:scale-[1.02]" : "border-glass-border text-foreground/35 cursor-not-allowed border"}`}
            >
              <Save size={14} /> {tagAction === "add" ? "Apply" : "Remove"}{" "}
              {selectedTagIds.size ? `(${selectedTagIds.size})` : ""}
            </button>
          </div>
          <div className="relative z-0 mt-4 grid gap-2 md:grid-cols-2">
            {documents.map((document) => {
              const isSelected = selected.has(document.document_id);
              return (
                <label
                  key={document.document_id}
                  className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 text-xs transition-all duration-200 ${isSelected ? "border-primary bg-primary/10 ring-primary/25 shadow-[0_0_18px_rgba(16,185,129,0.18)] ring-2" : "border-glass-border bg-background/20 hover:border-primary/50"}`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() =>
                      setSelected((current) => {
                        const next = new Set(current);
                        if (next.has(document.document_id)) next.delete(document.document_id);
                        else next.add(document.document_id);
                        return next;
                      })
                    }
                  />
                  <span
                    className={`min-w-0 flex-1 truncate ${isSelected ? "text-primary font-black" : ""}`}
                  >
                    {document.filename}
                  </span>
                  <span className="flex flex-wrap justify-end gap-1">
                    {(documentTags[document.document_id] ?? []).map((tagId) => (
                      <span
                        key={tagId}
                        className="bg-primary/10 text-primary rounded-md px-1.5 py-0.5 text-[9px]"
                      >
                        {String(items.find((item) => item.id === tagId)?.name ?? "tag")}
                      </span>
                    ))}
                  </span>
                  <span className="text-muted-foreground">{document.status}</span>
                </label>
              );
            })}
          </div>
        </section>
      ) : null}
      {secret ? (
        <div className="fixed inset-0 z-[250] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-md">
          <section
            role="dialog"
            aria-modal="true"
            className="theme-panel border-primary/20 w-full max-w-lg rounded-2xl border p-6 shadow-2xl"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-primary text-[10px] font-black tracking-[0.2em] uppercase">
                  AverQel secure setup
                </p>
                <h2 className="text-foreground mt-2 text-lg font-black">
                  Copy your webhook secret
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setSecret(null)}
                aria-label="Close secret dialog"
                className="theme-pill p-2"
              >
                ×
              </button>
            </div>
            <p className="text-muted-foreground mt-3 text-sm">
              This secret is shown only once. Store it securely and use it to verify the
              X-AverQel-Signature and X-AverQel-Timestamp headers. Reject old timestamps and
              deduplicate X-AverQel-Event-Id.
            </p>
            <div className="theme-input mt-4 flex items-center gap-2 rounded-xl p-3">
              <code className="min-w-0 flex-1 text-xs break-all">{secret}</code>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(secret);
                  toast.success("Secret copied.");
                }}
                className="theme-pill flex shrink-0 items-center gap-2 px-3 py-2 text-xs font-bold"
              >
                <Copy size={14} /> Copy
              </button>
            </div>
            <button
              type="button"
              onClick={() => setSecret(null)}
              className="bg-primary text-primary-foreground mt-5 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-xs font-black"
            >
              <Check size={15} /> I saved it
            </button>
          </section>
        </div>
      ) : null}
    </main>
  );
}

type ExplorerFolder = { id: string; name: string; parent_id?: string | null };
type ExplorerDocument = {
  document_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  quarantined: boolean;
  processing_progress: number;
};

function FolderExplorer() {
  const [folders, setFolders] = useState<ExplorerFolder[]>([]);
  const [files, setFiles] = useState<ExplorerDocument[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [folderName, setFolderName] = useState("");
  const [busy, setBusy] = useState(false);

  const loadFolders = async () => {
    const response = (await fetchWithAuth("/documents/organization/folders")) as Response;
    if (response.ok) setFolders(((await response.json()).items ?? []) as ExplorerFolder[]);
  };
  const loadFiles = async (folderId: string | null) => {
    const response = (await fetchWithAuth(
      `/documents/organization/folders/${folderId ?? "unfiled"}/documents`,
    )) as Response;
    if (response.ok) setFiles(((await response.json()).items ?? []) as ExplorerDocument[]);
  };
  const refresh = async () => {
    await Promise.all([loadFolders(), loadFiles(selectedFolder)]);
  };
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
    // The loader functions are intentionally local to this explorer; the selected folder
    // is the only reactive input that should trigger a refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFolder]);

  const createFolder = async () => {
    if (!folderName.trim()) return;
    const response = (await fetchWithAuth("/documents/organization/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: folderName.trim(), parent_id: selectedFolder }),
    })) as Response;
    if (response.ok) {
      setFolderName("");
      await loadFolders();
      toast.success("Folder created.");
    } else toast.error("Could not create folder.");
  };
  const renameFolder = async (folder: ExplorerFolder) => {
    const name = await averqelPrompt("Folder name", folder.name);
    if (!name?.trim()) return;
    const response = (await fetchWithAuth(`/documents/organization/folders/${folder.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    })) as Response;
    if (response.ok) {
      await loadFolders();
      toast.success("Folder renamed.");
    }
  };
  const deleteFolder = async (folder: ExplorerFolder) => {
    if (
      !(await averqelConfirm(`Delete folder ${folder.name}? Files will remain in Documents Hub.`))
    )
      return;
    const response = (await fetchWithAuth(`/documents/organization/folders/${folder.id}`, {
      method: "DELETE",
    })) as Response;
    if (response.ok) {
      if (selectedFolder === folder.id) setSelectedFolder(null);
      await loadFolders();
      toast.success("Folder deleted.");
    }
  };
  const moveFiles = async (documentIds: string[], folderId: string) => {
    const response = (await fetchWithAuth("/documents/bulk/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_ids: documentIds, folder_id: folderId }),
    })) as Response;
    if (response.ok) {
      setSelectedFiles(new Set());
      await loadFiles(selectedFolder);
      toast.success("Files moved.");
    } else toast.error("Could not move files.");
  };
  const uploadFiles = async (fileList: FileList | null, destination = selectedFolder) => {
    if (!fileList?.length) return;
    setBusy(true);
    try {
      for (const file of Array.from(fileList)) {
        const form = new FormData();
        form.append("file", file);
        const upload = (await fetchWithAuth("/documents/upload", {
          method: "POST",
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: form,
        })) as Response;
        if (!upload.ok) throw new Error(`Could not upload ${file.name}.`);
        const result = (await upload.json()) as { document_id: string };
        if (destination) await moveFiles([result.document_id], destination);
      }
      await loadFiles(destination);
      toast.success("Files uploaded.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  };
  const current = folders.find((folder) => folder.id === selectedFolder);
  const renderFolderTree = (parentId: string | null, depth = 0): ReactNode =>
    folders
      .filter((folder) => (folder.parent_id ?? null) === parentId)
      .map((folder) => (
        <div
          key={folder.id}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            const id = event.dataTransfer.getData("text/document-id");
            if (id) void moveFiles([id], folder.id);
            else if (event.dataTransfer.files.length)
              void uploadFiles(event.dataTransfer.files, folder.id);
          }}
        >
          <button
            type="button"
            onClick={() => setSelectedFolder(folder.id)}
            className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs ${selectedFolder === folder.id ? "bg-primary/10 text-primary font-bold" : "text-muted-foreground hover:bg-foreground/5"}`}
            style={{ paddingLeft: `${12 + depth * 16}px` }}
          >
            <span className="min-w-0 truncate">📁 {folder.name}</span>
            <span className="ml-2 flex shrink-0 gap-1">
              <span
                role="button"
                tabIndex={0}
                aria-label={`Rename ${folder.name}`}
                onClick={(event) => {
                  event.stopPropagation();
                  void renameFolder(folder);
                }}
              >
                ✎
              </span>
              <span
                role="button"
                tabIndex={0}
                aria-label={`Delete ${folder.name}`}
                onClick={(event) => {
                  event.stopPropagation();
                  void deleteFolder(folder);
                }}
              >
                ×
              </span>
            </span>
          </button>
          {renderFolderTree(folder.id, depth + 1)}
        </div>
      ));

  return (
    <main className="documents-theme-scope mx-auto w-full max-w-[1500px] space-y-5 p-4 md:p-8">
      <Link
        href="/dashboard/documents"
        className="text-muted-foreground hover:text-primary inline-flex items-center gap-2 text-xs font-bold"
      >
        <ArrowLeft size={15} /> Documents Hub
      </Link>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-primary text-[10px] font-black tracking-[0.2em] uppercase">
            Documents Hub / Explorer
          </p>
          <h1 className="text-foreground mt-2 text-2xl font-black">Folders</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Organize, open, upload, and preview files in a native workspace explorer.
          </p>
        </div>
        <label className="bg-primary text-primary-foreground flex cursor-pointer items-center gap-2 rounded-xl px-4 py-3 text-xs font-black uppercase">
          <Plus size={15} /> Add files
          <input
            type="file"
            multiple
            className="hidden"
            onChange={(event) => void uploadFiles(event.target.files)}
          />
        </label>
      </div>
      <div className="theme-panel flex min-h-[560px] overflow-hidden rounded-2xl border">
        <aside
          className="border-glass-border bg-background/30 w-64 shrink-0 border-r p-4"
          onDragOver={(event) => event.preventDefault()}
        >
          <button
            type="button"
            onClick={() => setSelectedFolder(null)}
            className={`mb-2 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-bold ${selectedFolder === null ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-foreground/5"}`}
          >
            Unfiled files
          </button>
          <div className="space-y-1">{renderFolderTree(null)}</div>
          <div className="border-glass-border mt-4 border-t pt-4">
            <input
              value={folderName}
              onChange={(event) => setFolderName(event.target.value)}
              placeholder={current ? `New folder in ${current.name}` : "New folder"}
              className="theme-input w-full rounded-lg px-3 py-2 text-xs"
            />
            <button
              type="button"
              onClick={() => void createFolder()}
              className="theme-pill mt-2 flex w-full items-center justify-center gap-2 py-2 text-xs font-bold"
            >
              <Plus size={13} /> Create folder
            </button>
          </div>
        </aside>
        <section
          className="min-w-0 flex-1 p-5"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            if (event.dataTransfer.files.length) void uploadFiles(event.dataTransfer.files);
          }}
        >
          <div className="border-glass-border text-muted-foreground mb-4 flex items-center gap-2 border-b pb-3 text-xs">
            <button
              type="button"
              onClick={() => setSelectedFolder(null)}
              className="hover:text-primary"
            >
              Documents
            </button>
            {current ? (
              <>
                <span>/</span>
                <span className="text-foreground font-bold">{current.name}</span>
              </>
            ) : null}
          </div>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-foreground text-sm font-black">
                {current?.name ?? "Unfiled files"}
              </h2>
              <p className="text-muted-foreground mt-1 text-xs">
                {files.length} file{files.length === 1 ? "" : "s"}
              </p>
            </div>
            <label className="theme-pill flex cursor-pointer items-center gap-2 px-3 py-2 text-xs font-bold">
              <Plus size={13} /> Add here
              <input
                type="file"
                multiple
                className="hidden"
                onChange={(event) => void uploadFiles(event.target.files)}
              />
            </label>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {files.map((file) => (
              <div
                key={file.document_id}
                draggable
                onDragStart={(event) =>
                  event.dataTransfer.setData("text/document-id", file.document_id)
                }
                className="border-glass-border bg-background/40 flex items-center gap-3 rounded-xl border p-3 text-xs"
              >
                <input
                  type="checkbox"
                  checked={selectedFiles.has(file.document_id)}
                  onChange={() =>
                    setSelectedFiles((currentSet) => {
                      const next = new Set(currentSet);
                      if (next.has(file.document_id)) next.delete(file.document_id);
                      else next.add(file.document_id);
                      return next;
                    })
                  }
                />
                <span className="min-w-0 flex-1 truncate">{file.filename}</span>
                <span className="text-muted-foreground">{file.status}</span>
                <Link
                  href={`/dashboard/documents/${file.document_id}`}
                  className="text-primary font-bold hover:underline"
                >
                  Open
                </Link>
              </div>
            ))}
          </div>
          {selectedFiles.size ? (
            <div className="bg-primary/5 mt-4 flex items-center justify-between rounded-xl p-3 text-xs">
              <span>{selectedFiles.size} selected</span>
              {folders.length > 1 ? (
                <select
                  defaultValue=""
                  onChange={(event) => {
                    if (event.target.value) void moveFiles([...selectedFiles], event.target.value);
                  }}
                  className="theme-input rounded-lg px-3 py-2"
                >
                  <option value="">Move to…</option>
                  {folders
                    .filter((folder) => folder.id !== selectedFolder)
                    .map((folder) => (
                      <option key={folder.id} value={folder.id}>
                        {folder.name}
                      </option>
                    ))}
                </select>
              ) : (
                <span className="text-muted-foreground">Drop files on a folder to move them.</span>
              )}
            </div>
          ) : null}
          {busy ? <p className="text-muted-foreground mt-4 text-xs">Uploading securely…</p> : null}
          {!files.length ? (
            <div className="text-muted-foreground flex min-h-48 items-center justify-center text-sm">
              This folder is empty. Add files or drop a document here.
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
