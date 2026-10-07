"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { Settings2, Tag, Folder, Webhook, WandSparkles, Clock3, Plus } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import toast from "react-hot-toast";
import { averqelAlert, averqelPrompt } from "@/app/components/ui/AverQelDialogHost";
import { useAuth } from "@/app/context/AuthContext";
import { hasAdminRole, normalizeRole } from "@/lib/roles";

type Item = {
  id: string;
  name: string;
  color?: string;
  filename_pattern?: string;
  content_type?: string | null;
  priority?: number;
  enabled?: boolean;
  interval_seconds?: number;
  endpoint_url?: string;
  match_count?: number;
  match_mode?: "all" | "any";
};

export default function DocumentOrganizationPanel() {
  const { user } = useAuth();
  const roles = user?.roles ?? [];
  const isAdmin = hasAdminRole(roles);
  const isEditor = isAdmin || roles.some((role) => normalizeRole(role) === "editor");
  const [tags, setTags] = useState<Item[]>([]);
  const [folders, setFolders] = useState<Item[]>([]);
  const [views, setViews] = useState<Item[]>([]);
  const [rules, setRules] = useState<Item[]>([]);
  const [schedules, setSchedules] = useState<Item[]>([]);
  const [webhooks, setWebhooks] = useState<Item[]>([]);
  const [smartCollections, setSmartCollections] = useState<Item[]>([]);
  const [open, setOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("averqel.documents.organization.open") === "true";
  });
  const [busy, setBusy] = useState(false);

  // Keep the user's explicit Manage/Hide choice across refreshes and data
  // reloads. Loading organization data must never collapse the panel.
  useEffect(() => {
    window.localStorage.setItem("averqel.documents.organization.open", String(open));
  }, [open]);

  const load = useCallback(async () => {
    try {
      const basicResults = (await Promise.all([
        fetchWithAuth("/documents/organization/tags"),
        fetchWithAuth("/documents/organization/folders"),
      ])) as Response[];
      const basicJson = await Promise.all(
        basicResults.map((response) => (response.ok ? response.json() : { items: [] })),
      );
      setTags(basicJson[0].items ?? []);
      setFolders(basicJson[1].items ?? []);
      if (isEditor) {
        const advancedResults = (await Promise.all([
          fetchWithAuth("/documents/organization/saved-views"),
          fetchWithAuth("/documents/organization/classification-rules"),
          fetchWithAuth("/documents/organization/automation-schedules"),
        ])) as Response[];
        const advancedJson = await Promise.all(
          advancedResults.map((response) => (response.ok ? response.json() : { items: [] })),
        );
        setViews(advancedJson[0].items ?? []);
        setRules(advancedJson[1].items ?? []);
        setSchedules(advancedJson[2].items ?? []);
      }
      if (isAdmin) {
        const [webhookResponse, smartResponse] = (await Promise.all([
          fetchWithAuth("/documents/webhooks"),
          fetchWithAuth("/documents/organization/smart-collections"),
        ])) as Response[];
        if (webhookResponse.ok) {
          const webhookPayload = await webhookResponse.json();
          setWebhooks(
            (Array.isArray(webhookPayload)
              ? webhookPayload
              : (webhookPayload.items ?? [])) as Item[],
          );
        } else {
          setWebhooks([]);
        }
        setSmartCollections(
          smartResponse.ok ? (((await smartResponse.json()).items ?? []) as Item[]) : [],
        );
      }
    } catch (error) {
      console.error("Failed to load document organization", error);
    }
  }, [isAdmin, isEditor]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  const create = async (path: string, payload: object, label: string) => {
    setBusy(true);
    try {
      const response = (await fetchWithAuth(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })) as Response;
      if (!response.ok) throw new Error(`Could not create ${label}.`);
      const result = await response.json();
      if (label === "tag") setTags((items) => [...items, result]);
      if (label === "folder") setFolders((items) => [...items, result]);
      if (label === "view") setViews((items) => [...items, result]);
      if (label === "rule") setRules((items) => [...items, result]);
      if (label === "schedule") setSchedules((items) => [...items, result]);
      if (label === "smart collection") setSmartCollections((items) => [...items, result]);
      if (label === "webhook") {
        setWebhooks((items) => [...items, result]);
        if (result.secret)
          await averqelAlert(`Copy this webhook secret now. It is shown once:\n\n${result.secret}`);
      }
      toast.success(`${label[0].toUpperCase()}${label.slice(1)} created.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : `Could not create ${label}.`);
    } finally {
      setBusy(false);
    }
  };

  const createFromPrompt = async (label: string, path: string, fields: string[]) => {
    const values: string[] = [];
    for (const field of fields) {
      const value = await averqelPrompt(field, field === "Filename pattern" ? "*" : "");
      if (!value?.trim()) return;
      values.push(value.trim());
    }
    const payload =
      label === "rule"
        ? { name: values[0], filename_pattern: values[1] }
        : label === "webhook"
          ? {
              endpoint_url: values[0],
              event_types: ["document.indexed", "document.failed", "document.status.updated"],
            }
          : label === "schedule"
            ? { name: values[0], interval_seconds: 3600 }
            : label === "view"
              ? { name: values[0], filters: {} }
              : { name: values[0] };
    await create(path, payload, label);
  };

  const createSmartCollection = async () => {
    const name = await averqelPrompt("Smart collection name");
    if (!name?.trim()) return;
    const mode = (await averqelPrompt("Match mode: all or any", "all"))?.trim().toLowerCase();
    if (mode !== "all" && mode !== "any") {
      toast.error("Match mode must be all or any.");
      return;
    }
    const field = (
      await averqelPrompt(
        "Condition field: status, quarantined, ocr_confidence, content_type, filename, tag, or folder",
      )
    )?.trim();
    const conditionOperator = (
      await averqelPrompt(
        "Condition operator: equals, not_equals, contains, starts_with, greater_than, or less_than",
      )
    )?.trim();
    const value = await averqelPrompt("Condition value (for tag/folder use the ID)");
    if (!field || !conditionOperator || !value?.trim()) return;
    await create(
      "/documents/organization/smart-collections",
      {
        name: name.trim(),
        match_mode: mode,
        conditions: [{ field, operator: conditionOperator, value: value.trim() }],
      },
      "smart collection",
    );
  };

  return (
    <section className="theme-panel rounded-[1.5rem] p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Settings2 size={18} className="text-emerald-500" />
          <div>
            <h2 className="text-foreground text-sm font-bold tracking-[0.16em] uppercase">
              Organization & automation
            </h2>
            <p className="text-muted-foreground mt-1 text-xs">
              {isAdmin
                ? "Tags, folders, views, classification, schedules, smart collections, and webhooks."
                : isEditor
                  ? "Tags, folders, saved views, classification, and schedules."
                  : "Tags and folders for your workspace."}
            </p>
          </div>
        </div>
        <motion.button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          whileTap={{ scale: 0.96 }}
          className="theme-pill min-w-20 px-3 py-2 text-xs font-bold"
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={open ? "hide" : "manage"}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.16 }}
            >
              {open ? "Hide" : "Manage"}
            </motion.span>
          </AnimatePresence>
        </motion.button>
      </div>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="organization-controls"
            initial={{ opacity: 0, height: 0, y: -8 }}
            animate={{ opacity: 1, height: "auto", y: 0 }}
            exit={{ opacity: 0, height: 0, y: -8 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="mt-5 grid gap-4 overflow-hidden md:grid-cols-2 xl:grid-cols-3"
          >
            <ManagerCard
              icon={<Tag size={15} />}
              title="Tags"
              items={tags}
              onAdd={() =>
                void createFromPrompt("tag", "/documents/organization/tags", ["Tag name"])
              }
            />
            <ManagerCard
              icon={<Folder size={15} />}
              title="Folders"
              items={folders}
              onAdd={() =>
                void createFromPrompt("folder", "/documents/organization/folders", ["Folder name"])
              }
            />
            {isEditor ? (
              <>
                <ManagerCard
                  icon={<Settings2 size={15} />}
                  title="Saved views"
                  items={views}
                  onAdd={() =>
                    void createFromPrompt("view", "/documents/organization/saved-views", [
                      "Saved view name",
                    ])
                  }
                />
                <ManagerCard
                  icon={<WandSparkles size={15} />}
                  title="Classification rules"
                  items={rules}
                  onAdd={() =>
                    void createFromPrompt("rule", "/documents/organization/classification-rules", [
                      "Rule name",
                      "Filename pattern",
                    ])
                  }
                />
                <ManagerCard
                  icon={<Clock3 size={15} />}
                  title="Automation schedules"
                  items={schedules}
                  onAdd={() =>
                    void createFromPrompt(
                      "schedule",
                      "/documents/organization/automation-schedules",
                      ["Schedule name"],
                    )
                  }
                />
              </>
            ) : null}
            {isAdmin ? (
              <>
                <ManagerCard
                  icon={<WandSparkles size={15} />}
                  title="Smart collections"
                  items={smartCollections}
                  onAdd={() => void createSmartCollection()}
                />
                <ManagerCard
                  icon={<Webhook size={15} />}
                  title="Webhooks"
                  items={webhooks}
                  onAdd={() =>
                    void createFromPrompt("webhook", "/documents/webhooks", [
                      "HTTPS webhook endpoint",
                    ])
                  }
                />
              </>
            ) : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
      {busy ? <p className="text-muted-foreground mt-3 text-xs">Saving securely…</p> : null}
    </section>
  );
}

function ManagerCard({
  icon,
  title,
  items,
  onAdd,
}: {
  icon: ReactNode;
  title: string;
  items: Item[];
  onAdd: () => void;
}) {
  const slug = title.toLowerCase().replaceAll(" ", "-");
  return (
    <div className="border-glass-border bg-background/30 rounded-xl border p-4">
      <div className="flex items-center justify-between">
        <Link
          href={`/dashboard/documents/organization/${slug}`}
          className="text-foreground hover:text-primary flex items-center gap-2 text-xs font-bold tracking-wider uppercase"
        >
          {icon}
          {title}
        </Link>
        <button
          type="button"
          onClick={onAdd}
          className="text-primary hover:bg-primary/10 rounded-lg p-1.5"
          aria-label={`Add ${title}`}
        >
          <Plus size={15} />
        </button>
      </div>
      <div className="mt-3 flex min-h-10 items-center justify-between gap-3">
        <p className="text-muted-foreground/70 text-xs">
          {items.length ? `${items.length} configured` : "None configured."}
        </p>
        <Link
          href={`/dashboard/documents/organization/${slug}`}
          className="text-primary text-[10px] font-bold tracking-wider uppercase hover:underline"
        >
          Open page
        </Link>
      </div>
    </div>
  );
}
