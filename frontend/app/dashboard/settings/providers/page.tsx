"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  Zap,
  RefreshCw,
  Database,
  Activity,
  ScanSearch,
  Bot,
  Globe2,
  AlertCircle,
  CheckCircle2,
  LayoutGrid,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  Link2Off,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import toast from "react-hot-toast";

import ProviderDeleteDialog from "@/app/components/providers/ProviderDeleteDialog";
import ProviderDisableDialog from "@/app/components/providers/ProviderDisableDialog";
import ProviderForm from "@/app/components/providers/ProviderForm";
import ProviderListTable from "@/app/components/providers/ProviderListTable";
import ProviderHealthBadge from "@/app/components/providers/ProviderHealthBadge";
import {
  providerHasConfiguredRuntime,
  providerMatchesInventoryTab,
} from "@/app/components/providers/provider-visibility";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import type {
  ProviderCatalogEntry,
  ProviderConfig,
  CreateProviderInput,
  UpdateProviderInput,
  ProviderModel,
} from "@/lib/providers-api";
import {
  createProvider,
  deleteProvider,
  disconnectProvider,
  listProviders,
  listSupportedProviderTypes,
  testProvider,
  updateProvider,
  refreshProviderModels,
  listProviderModels,
  pullProviderModel,
} from "@/lib/providers-api";

type TabKind = "runtime" | "chat" | "embedding" | "reranker" | "web";

const HIDDEN_CATALOG_TYPES = new Set(["groq-openai-compatible"]);

function normalizeCatalogType(providerType: string | null | undefined): string | null {
  if (!providerType) return null;
  if (providerType === "groq-openai-compatible") return "groq";
  return providerType;
}

function compareProvidersForDefault(a: ProviderConfig, b: ProviderConfig): number {
  if (a.priority !== b.priority) return b.priority - a.priority;
  const aUpdated = Date.parse(a.updated_at) || 0;
  const bUpdated = Date.parse(b.updated_at) || 0;
  if (aUpdated !== bUpdated) return bUpdated - aUpdated;
  return a.display_name.localeCompare(b.display_name);
}

export default function ProvidersSettingsPage() {
  const [entered, setEntered] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKind>("chat");
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [catalog, setCatalog] = useState<ProviderCatalogEntry[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null);
  const [showCreateFlow, setShowCreateFlow] = useState(false);
  const [selectedCatalogType, setSelectedCatalogType] = useState<string | null>(null);
  const [browsingCatalog, setBrowsingCatalog] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(0);

  // Accordion state for mobile
  const [isInventoryExpanded, setIsInventoryExpanded] = useState(true);

  const [loading, setLoading] = useState(true);
  const [busyProviderAction, setBusyProviderAction] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProviderConfig | null>(null);
  const [disconnectTarget, setDisconnectTarget] = useState<ProviderConfig | null>(null);

  const [providerModels, setProviderModels] = useState<ProviderModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [pullModelName, setPullModelName] = useState("");
  const [pullingModel, setPullingModel] = useState(false);

  const [pingStates, setPingStates] = useState<
    Record<
      string,
      { status: "idle" | "pinging" | "healthy" | "error"; message?: string; latency?: number }
    >
  >({});

  const loadPage = useCallback(async () => {
    setLoading(true);
    try {
      const [p, c] = await Promise.all([listProviders(), listSupportedProviderTypes()]);
      setProviders(p);
      setCatalog(c);
    } catch {
      toast.error("Failed to load providers");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPage();
  }, [loadPage]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    const updateViewport = () => {
      setViewportWidth(window.visualViewport?.width || window.innerWidth || 0);
    };

    updateViewport();
    window.addEventListener("resize", updateViewport);
    window.visualViewport?.addEventListener("resize", updateViewport);
    return () => {
      window.removeEventListener("resize", updateViewport);
      window.visualViewport?.removeEventListener("resize", updateViewport);
    };
  }, []);

  const isNarrowViewport = viewportWidth > 0 && viewportWidth < 1024;

  useEffect(() => {
    if (loading || activeTab === "runtime" || showCreateFlow || browsingCatalog) return;

    const kindProviders = providers
      .filter((pr) => providerMatchesInventoryTab(pr, activeTab))
      .sort(compareProvidersForDefault);

    if (kindProviders.length === 0) {
      if (selectedProviderId !== null) setSelectedProviderId(null);
      return;
    }

    const hasSelectedProvider = selectedProviderId
      ? kindProviders.some((provider) => provider.id === selectedProviderId)
      : false;

    if (!hasSelectedProvider) {
      setSelectedProviderId(kindProviders[0].id);
    }
  }, [activeTab, browsingCatalog, loading, providers, selectedProviderId, showCreateFlow]);

  const loadModels = useCallback(async (id: string) => {
    setLoadingModels(true);
    try {
      let m: ProviderModel[];
      try {
        m = await refreshProviderModels(id);
      } catch (refreshError) {
        console.warn(
          "Provider model refresh failed, falling back to cached inventory",
          refreshError,
        );
        m = await listProviderModels(id);
      }
      setProviderModels(m);
    } catch (error) {
      console.error("Failed to load model inventory", error);
    } finally {
      setLoadingModels(false);
    }
  }, []);

  useEffect(() => {
    if (selectedProviderId) {
      void loadModels(selectedProviderId);
      if (isNarrowViewport) setIsInventoryExpanded(false); // Auto-collapse on mobile when selected
    } else {
      setProviderModels([]);
    }
  }, [loadModels, selectedProviderId, isNarrowViewport]);

  async function handleRefreshModels() {
    if (!selectedProvider) return;
    setLoadingModels(true);
    try {
      const m = await refreshProviderModels(selectedProvider.id);
      setProviderModels(m);
      toast.success("Model inventory synchronized");
    } catch {
      toast.error("Synchronization failed");
    } finally {
      setLoadingModels(false);
    }
  }

  async function handlePullModel() {
    if (!selectedProvider || !pullModelName.trim()) return;
    setPullingModel(true);
    try {
      await pullProviderModel(selectedProvider.id, pullModelName);
      toast.success("Model pull initiated");
      setPullModelName("");
      if (selectedProviderId) await loadModels(selectedProviderId);
    } catch {
      toast.error("Model pull failed");
    } finally {
      setPullingModel(false);
    }
  }

  const selectedProvider = useMemo(
    () => providers.find((p) => p.id === selectedProviderId) || null,
    [providers, selectedProviderId],
  );

  const selectedCatalogEntry = useMemo(
    () =>
      catalog.find(
        (c) =>
          c.provider_type ===
          normalizeCatalogType(selectedProvider?.provider_type || selectedCatalogType),
      ) || null,
    [catalog, selectedProvider, selectedCatalogType],
  );

  async function handleProviderSubmit(payload: CreateProviderInput | UpdateProviderInput) {
    setBusyProviderAction(selectedProvider ? `update:${selectedProvider.id}` : "create");
    try {
      if (selectedProvider) {
        await updateProvider(selectedProvider.id, payload as UpdateProviderInput);
        toast.success("Connection updated");
      } else {
        const created = await createProvider(payload as CreateProviderInput);
        setSelectedProviderId(created.id);
        setShowCreateFlow(false);
        toast.success("Connection linked");
      }
      await loadPage();
    } catch {
      toast.error("Action failed");
    } finally {
      setBusyProviderAction(null);
    }
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setBusyProviderAction(`delete:${deleteTarget.id}`);
    try {
      await deleteProvider(deleteTarget.id);
      toast.success("Connection removed");
      setSelectedProviderId(null);
      setDeleteTarget(null);
      await loadPage();
    } catch {
      toast.error("Delete failed");
    } finally {
      setBusyProviderAction(null);
    }
  }

  async function handleDisconnectConfirm() {
    if (!disconnectTarget) return;
    setBusyProviderAction(`disconnect:${disconnectTarget.id}`);
    try {
      await disconnectProvider(disconnectTarget.id);
      setSelectedProviderId((current) => (current === disconnectTarget.id ? null : current));
      toast.success("Connection terminated");
      setDisconnectTarget(null);
      await loadPage();
    } catch {
      toast.error("Terminate failed");
    } finally {
      setBusyProviderAction(null);
    }
  }

  async function handleTest(provider: ProviderConfig) {
    setPingStates((p) => ({ ...p, [provider.id]: { status: "pinging", message: "Testing..." } }));
    try {
      const res = await testProvider(provider.id);
      setPingStates((p) => ({
        ...p,
        [provider.id]: {
          status: res.status === "healthy" ? "healthy" : "error",
          latency: res.latency_ms || undefined,
          message:
            res.status === "healthy"
              ? `Connection healthy · ${res.latency_ms}ms`
              : res.error_message_redacted || "Ping failed",
        },
      }));
      if (res.status === "healthy") toast.success("Connection verified");
      else toast.error("Verification failed");
      await loadPage();
    } catch {
      setPingStates((p) => ({
        ...p,
        [provider.id]: { status: "error", message: "Network error" },
      }));
      toast.error("Test failed");
    }
  }

  function handleTabChange(tab: TabKind) {
    setActiveTab(tab);
    setShowCreateFlow(false);
    setBrowsingCatalog(false);
    setSelectedCatalogType(null);
    setIsInventoryExpanded(true); // Re-expand on tab change

    if (tab === "runtime") {
      setSelectedProviderId(null);
      return;
    }

    const nextProviders = providers.filter((p) => providerMatchesInventoryTab(p, tab));
    if (nextProviders.length > 0) setSelectedProviderId(nextProviders[0].id);
    else setSelectedProviderId(null);
  }

  const runtimeActive = useMemo(
    () => ({
      llm:
        providers
          .filter((p) => p.enabled && providerMatchesInventoryTab(p, "chat"))
          .sort(compareProvidersForDefault)[0] || null,
      embedding:
        providers
          .filter((p) => p.enabled && providerMatchesInventoryTab(p, "embedding"))
          .sort(compareProvidersForDefault)[0] || null,
      reranker:
        providers
          .filter((p) => p.enabled && providerMatchesInventoryTab(p, "reranker"))
          .sort(compareProvidersForDefault)[0] || null,
      web:
        providers
          .filter((p) => p.enabled && providerMatchesInventoryTab(p, "web"))
          .sort(compareProvidersForDefault)[0] || null,
    }),
    [providers],
  );

  const runtimeCards = [
    {
      key: "llm" as const,
      title: "LLM active",
      provider: runtimeActive.llm,
      pingState: runtimeActive.llm ? pingStates[runtimeActive.llm.id] : undefined,
      onPing: () => runtimeActive.llm && handleTest(runtimeActive.llm),
      onDisconnect: () => runtimeActive.llm && setDisconnectTarget(runtimeActive.llm),
    },
    {
      key: "embedding" as const,
      title: "Embedding active",
      provider: runtimeActive.embedding,
      pingState: runtimeActive.embedding ? pingStates[runtimeActive.embedding.id] : undefined,
      onPing: () => runtimeActive.embedding && handleTest(runtimeActive.embedding),
      onDisconnect: () => runtimeActive.embedding && setDisconnectTarget(runtimeActive.embedding),
    },
    {
      key: "reranker" as const,
      title: "Reranker active",
      provider: runtimeActive.reranker,
      pingState: runtimeActive.reranker ? pingStates[runtimeActive.reranker.id] : undefined,
      onPing: () => runtimeActive.reranker && handleTest(runtimeActive.reranker),
      onDisconnect: () => runtimeActive.reranker && setDisconnectTarget(runtimeActive.reranker),
    },
    {
      key: "web" as const,
      title: "Web search active",
      provider: runtimeActive.web,
      pingState: runtimeActive.web ? pingStates[runtimeActive.web.id] : undefined,
      onPing: () => runtimeActive.web && handleTest(runtimeActive.web),
      onDisconnect: () => runtimeActive.web && setDisconnectTarget(runtimeActive.web),
    },
  ].filter((card) => card.provider && providerHasConfiguredRuntime(card.provider));

  if (loading) {
    return (
      <div className="text-foreground flex h-full w-full flex-col">
        <div className="shrink-0">
          <DashboardSectionHeader
            title="Providers"
            subtitle="Manage foundation models and runtime connectivity"
            icon={Zap}
            accentClassName="bg-primary text-primary"
            accentGlowClassName="shadow-[0_0_18px_hsl(var(--primary)/0.28)]"
            backHref="/dashboard/settings"
            backLabel="Back To Settings"
          />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="space-y-4 text-center">
            <div className="border-primary mx-auto h-10 w-10 animate-spin rounded-full border-2 border-t-transparent"></div>
            <p className="text-muted-foreground">Loading providers...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`providers-page-enter text-foreground flex h-full w-full flex-col gap-6 ${
        entered ? "is-entered" : ""
      }`}
    >
      <div className={`providers-page-section shrink-0 ${entered ? "is-entered" : ""}`}>
        <DashboardSectionHeader
          title="Providers"
          subtitle="Manage foundation models and runtime connectivity"
          icon={Zap}
          accentClassName="bg-primary text-primary"
          accentGlowClassName="shadow-[0_0_18px_hsl(var(--primary)/0.28)]"
          backHref="/dashboard/settings"
          backLabel="Back To Settings"
          actions={
            <div className="border-glass-border bg-surface-1/50 flex flex-wrap items-center gap-1 rounded-xl border p-1 shadow-inner">
              <NavItem
                active={activeTab === "runtime"}
                label="Navigator"
                icon={<LayoutGrid size={12} />}
                onClick={() => handleTabChange("runtime")}
              />
              <NavItem
                active={activeTab === "chat"}
                label="LLM"
                icon={<Bot size={12} />}
                onClick={() => handleTabChange("chat")}
              />
              <NavItem
                active={activeTab === "embedding"}
                label="Embedding"
                icon={<Database size={12} />}
                onClick={() => handleTabChange("embedding")}
              />
              <NavItem
                active={activeTab === "reranker"}
                label="Reranker"
                icon={<ScanSearch size={12} />}
                onClick={() => handleTabChange("reranker")}
              />
              <NavItem
                active={activeTab === "web"}
                label="Web"
                icon={<Globe2 size={12} />}
                onClick={() => handleTabChange("web")}
              />
            </div>
          }
        />
      </div>

      <div
        className={`providers-page-section mt-1 flex min-h-0 w-full flex-1 flex-col overflow-hidden px-0 sm:px-0 ${
          entered ? "is-entered" : ""
        }`}
      >
        <div
          className={`${
            isNarrowViewport
              ? "custom-scrollbar flex flex-col space-y-6 overflow-y-auto px-4 pb-24"
              : "grid h-full w-full grid-cols-12 gap-5 overflow-hidden lg:gap-8 xl:gap-12"
          }`}
        >
          {activeTab === "runtime" ? (
            <div
              className={`col-span-12 ${isNarrowViewport ? "space-y-4" : "grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4"}`}
            >
              {runtimeCards.map((card) => (
                <RuntimeCard
                  key={card.key}
                  title={card.title}
                  provider={card.provider}
                  pingState={card.pingState}
                  onPing={card.onPing}
                  onDisconnect={card.onDisconnect}
                />
              ))}
              {runtimeCards.length === 0 && (
                <div className="theme-card col-span-full flex min-h-[14rem] items-center justify-center">
                  <div className="text-center">
                    <p className="text-muted-foreground/60 text-xs font-bold tracking-[0.22em] uppercase">
                      Navigator
                    </p>
                    <h3 className="mt-3 text-xl font-bold">No runtime cards configured</h3>
                    <p className="text-muted-foreground mt-2 text-sm">
                      Connect LLM, embedding, reranker, or web providers to show them here.
                    </p>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <>
              {/* Sidebar Navigator / Inventory Section */}
              <aside
                className={`theme-panel-muted mt-1 flex flex-col rounded-2xl p-4 sm:p-5 ${
                  isNarrowViewport
                    ? "w-full shrink-0 border border-white/5"
                    : "col-span-12 min-h-0 lg:col-span-3"
                }`}
              >
                <div className="mb-4 flex shrink-0 items-center justify-between px-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-muted-foreground/60 font-mono text-[9px] font-bold tracking-[0.2em] uppercase">
                      {browsingCatalog ? "Select Family" : "Inventory"}
                    </h3>
                    {isNarrowViewport && (
                      <button
                        onClick={() => setIsInventoryExpanded(!isInventoryExpanded)}
                        className="text-zinc-500 transition-colors hover:text-white"
                      >
                        {isInventoryExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      </button>
                    )}
                  </div>
                  <button
                    onClick={() => {
                      setBrowsingCatalog(!browsingCatalog);
                      if (isNarrowViewport) setIsInventoryExpanded(true);
                    }}
                    className={`rounded-lg p-1.5 transition-all ${
                      browsingCatalog
                        ? "bg-primary rotate-45 text-slate-950"
                        : "bg-surface-2 text-primary hover:bg-primary/10"
                    }`}
                  >
                    <Plus size={14} />
                  </button>
                </div>

                <AnimatePresence>
                  {(isInventoryExpanded || !isNarrowViewport) && (
                    <motion.div
                      initial={isNarrowViewport ? { height: 0, opacity: 0 } : false}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className={`relative w-full overflow-hidden ${isNarrowViewport ? "" : "flex-1"}`}
                    >
                      <div
                        className={`w-full ${isNarrowViewport ? "max-h-[300px] overflow-y-auto pb-4" : "custom-scrollbar h-full overflow-y-auto"}`}
                      >
                        <AnimatePresence mode="wait">
                          {browsingCatalog ? (
                            <motion.div
                              key="catalog"
                              initial={{ opacity: 0, x: -20 }}
                              animate={{ opacity: 1, x: 0 }}
                              exit={{ opacity: 0, x: -20 }}
                              className="w-full space-y-2 pr-1"
                            >
                              <button
                                onClick={() => setBrowsingCatalog(false)}
                                className="hover:bg-surface-1 group flex w-full items-center gap-2 rounded-xl p-3 text-left transition-all"
                              >
                                <ArrowLeft
                                  size={14}
                                  className="transition-transform group-hover:-translate-x-1"
                                />
                                <span className="text-xs font-bold">Back to Inventory</span>
                              </button>
                              {catalog
                                .filter((entry) => !HIDDEN_CATALOG_TYPES.has(entry.provider_type))
                                .filter((entry) => {
                                  if (activeTab === "chat") return entry.supports_chat;
                                  if (activeTab === "embedding") return entry.supports_embeddings;
                                  if (activeTab === "reranker")
                                    return Boolean(entry.supports_reranking);
                                  if (activeTab === "web")
                                    return Boolean(entry.supports_web_search);
                                  return true;
                                })
                                .map((entry) => (
                                  <button
                                    key={entry.provider_type}
                                    onClick={() => {
                                      setSelectedProviderId(null);
                                      setSelectedCatalogType(entry.provider_type);
                                      setShowCreateFlow(true);
                                      if (isNarrowViewport) setIsInventoryExpanded(false);
                                    }}
                                    className={`flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all ${
                                      selectedCatalogType === entry.provider_type
                                        ? "border-primary/40 bg-primary/5 ring-primary/20 ring-1"
                                        : "border-glass-border bg-surface-0 hover:border-primary/20 hover:bg-surface-1"
                                    }`}
                                  >
                                    <div className="theme-panel-muted text-primary flex h-8 w-8 items-center justify-center rounded-lg">
                                      <Zap size={16} />
                                    </div>
                                    <div>
                                      <p className="text-foreground text-xs leading-none font-bold">
                                        {entry.display_name}
                                      </p>
                                      <p className="text-muted-foreground mt-1 text-[9px] tracking-widest uppercase">
                                        {entry.provider_type}
                                      </p>
                                    </div>
                                  </button>
                                ))}
                            </motion.div>
                          ) : (
                            <motion.div
                              key="list"
                              initial={{ opacity: 0, x: 20 }}
                              animate={{ opacity: 1, x: 0 }}
                              exit={{ opacity: 0, x: 20 }}
                              className="flex w-full flex-col"
                            >
                              <ProviderListTable
                                activeServiceKind={activeTab}
                                providers={providers}
                                selectedProviderId={selectedProviderId}
                                onSelect={(id) => {
                                  setSelectedProviderId(id);
                                  setShowCreateFlow(false);
                                  setBrowsingCatalog(false);
                                  if (isNarrowViewport) setIsInventoryExpanded(false);
                                }}
                                onDelete={(provider) => setDeleteTarget(provider)}
                                countLabel={activeTab.toUpperCase()}
                              />
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </aside>

              {/* Configuration Area / Setup Section */}
              <main
                className={`flex min-w-0 flex-col ${
                  isNarrowViewport ? "w-full" : "col-span-12 h-full min-h-0 lg:col-span-9"
                }`}
              >
                {!isInventoryExpanded && isNarrowViewport && (
                  <button
                    onClick={() => setIsInventoryExpanded(true)}
                    className="text-primary mb-2 flex items-center gap-2 px-1 text-[10px] font-bold tracking-widest uppercase"
                  >
                    <ArrowLeft size={12} /> Back to Inventory
                  </button>
                )}

                <div
                  className={`theme-panel-strong flex flex-col rounded-2xl border border-white/5 bg-white/[0.02] ${isNarrowViewport ? "min-h-0" : "h-full overflow-hidden"}`}
                >
                  <div
                    className={`flex-1 ${isNarrowViewport ? "" : "custom-scrollbar overflow-y-auto"} p-4 sm:p-8`}
                  >
                    {selectedProvider || showCreateFlow ? (
                      <ProviderForm
                        catalogEntry={selectedCatalogEntry}
                        provider={selectedProvider}
                        models={providerModels}
                        loadingModels={loadingModels}
                        kind={
                          activeTab === "chat"
                            ? "chat"
                            : activeTab === "embedding"
                              ? "embedding"
                              : activeTab === "reranker"
                                ? "reranker"
                                : "web"
                        }
                        saving={
                          !!(
                            busyProviderAction?.startsWith("create") ||
                            busyProviderAction?.startsWith("update")
                          )
                        }
                        busyAction={busyProviderAction}
                        onCancel={() => {
                          setShowCreateFlow(false);
                          setSelectedProviderId(null);
                          if (isNarrowViewport) setIsInventoryExpanded(true);
                        }}
                        onSubmit={handleProviderSubmit}
                        onTest={handleTest}
                        onDelete={setDeleteTarget}
                        onDisconnect={setDisconnectTarget}
                        onReconnect={async (prv) => {
                          setBusyProviderAction(`enable:${prv.id}`);
                          await updateProvider(prv.id, { enabled: true });
                          await loadPage();
                          setBusyProviderAction(null);
                        }}
                        onRefreshModels={handleRefreshModels}
                        onPullModel={handlePullModel}
                        pullModelName={pullModelName}
                        onPullModelNameChange={setPullModelName}
                        pullingModel={pullingModel}
                      />
                    ) : (
                      <div className="flex h-full flex-col items-center justify-center space-y-6 py-12 text-center">
                        <div className="bg-primary/10 text-primary rounded-3xl p-6 shadow-[0_0_40px_rgba(var(--primary-rgb),0.1)]">
                          <Zap size={48} className="animate-pulse" />
                        </div>
                        <div className="max-w-sm space-y-3 px-4">
                          <h3 className="text-xl font-bold tracking-tight">System Navigator</h3>
                          <p className="text-muted-foreground text-sm leading-relaxed">
                            Select a provider from the inventory to adjust its parameters or test
                            connectivity.
                          </p>
                          {isNarrowViewport && !isInventoryExpanded && (
                            <button
                              onClick={() => setIsInventoryExpanded(true)}
                              className="theme-chip bg-primary mt-6 rounded-xl px-8 py-3 text-[10px] font-bold tracking-widest text-slate-950 uppercase"
                            >
                              Open Inventory
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </main>
            </>
          )}
        </div>
      </div>

      <ProviderDeleteDialog
        open={!!deleteTarget}
        title="Delete Connection"
        body={`Are you sure you want to delete the ${deleteTarget?.display_name} connection? This cannot be undone.`}
        confirmLabel="Delete Runtime"
        busy={busyProviderAction === `delete:${deleteTarget?.id}`}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDeleteConfirm}
      />
      <ProviderDisableDialog
        open={!!disconnectTarget}
        title="Terminate Connection"
        body={`Terminate connectivity to ${disconnectTarget?.display_name}? The provider will be disabled and can be resumed later.`}
        confirmLabel="Terminate Connection"
        busy={busyProviderAction === `disconnect:${disconnectTarget?.id}`}
        onCancel={() => setDisconnectTarget(null)}
        onConfirm={handleDisconnectConfirm}
      />
    </div>
  );
}

function NavItem({
  active,
  label,
  icon,
  onClick,
}: {
  active: boolean;
  label: string;
  icon: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative inline-flex items-center gap-2 rounded-xl px-4 py-2.5 font-mono text-[11px] tracking-[0.12em] uppercase transition-all ${
        active
          ? "bg-surface-0 border-glass-border text-primary border shadow-sm"
          : "text-muted-foreground hover:bg-surface-2 hover:text-foreground border border-transparent"
      }`}
    >
      <span className="relative z-10">{icon}</span>
      <span className="relative z-10">{label}</span>
      {active && (
        <motion.div layoutId="nav-pill" className="bg-primary absolute inset-x-0 bottom-0 h-0.5" />
      )}
    </button>
  );
}

function RuntimeCard({
  title,
  provider,
  pingState,
  onPing,
  onDisconnect,
}: {
  title: string;
  provider: ProviderConfig | null;
  pingState?: { status: string; message?: string; latency?: number };
  onPing: () => void;
  onDisconnect: () => void;
}) {
  return (
    <div className="theme-card flex flex-col space-y-6 border border-white/5 bg-white/[0.02]">
      <div className="flex items-start justify-between">
        <div className="theme-panel-muted text-primary rounded-xl p-3">
          {title.includes("LLM") ? (
            <Bot size={22} />
          ) : title.includes("Embedding") ? (
            <Database size={22} />
          ) : (
            <ScanSearch size={22} />
          )}
        </div>
        <ProviderHealthBadge health={provider?.latest_health || null} />
      </div>

      <div className="space-y-1">
        <p className="text-muted-foreground font-mono text-[10px] tracking-[0.24em] uppercase">
          {title}
        </p>
        <h3 className="text-foreground truncate text-xl font-bold">
          {provider?.display_name ?? "None"}
        </h3>
        <p className="text-muted-foreground truncate text-sm">
          {provider?.default_chat_model ||
            provider?.default_embedding_model ||
            provider?.default_reranker_model ||
            "No model assigned"}
        </p>
      </div>

      <div className="border-glass-border border-t pt-4">
        {!pingState ? (
          provider ? (
            <p className="text-xs font-bold tracking-widest text-emerald-400/80 uppercase">
              Ready by default
            </p>
          ) : (
            <p className="text-muted-foreground text-xs tracking-tighter uppercase">
              Connectivity status unknown
            </p>
          )
        ) : pingState.status === "pinging" ? (
          <div className="text-primary flex items-center gap-2">
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            <span className="text-[11px] font-bold tracking-widest uppercase">Pinging...</span>
          </div>
        ) : pingState.status === "healthy" ? (
          <div className="flex items-center gap-2 text-emerald-500">
            <CheckCircle2 size={14} />
            <span className="truncate text-[11px] font-bold tracking-widest uppercase">
              {pingState.message}
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-rose-500">
            <AlertCircle size={14} />
            <span className="truncate text-[11px] font-bold tracking-widest uppercase">
              {pingState.message}
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 pt-2">
        <button
          onClick={onPing}
          className="theme-chip hover:text-primary flex flex-1 items-center justify-center gap-2 rounded-xl py-3 text-[10px] font-bold tracking-widest uppercase transition-colors"
        >
          <Activity size={12} />
          Verify
        </button>
        <button
          onClick={onDisconnect}
          className="theme-chip flex flex-1 items-center justify-center gap-2 rounded-xl py-3 text-[10px] font-bold tracking-widest uppercase transition-colors hover:text-amber-400"
        >
          <Link2Off size={12} />
          Terminate
        </button>
      </div>
    </div>
  );
}
