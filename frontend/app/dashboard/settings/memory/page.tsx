"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Trash2,
  Search,
  ShieldAlert,
  Clock,
  Info,
  Database,
} from "lucide-react";
import { toast } from "react-hot-toast";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { apiV1 } from "@/lib/api";

type MemoryFact = {
  id: string;
  key: string;
  value: string;
  scope: string;
  tags: string[];
  created_at: string;
  updated_at?: string | null;
};

export default function MemoryManagementPage() {
  const [memories, setMemories] = useState<MemoryFact[]>([]);
  const [search, setSearch] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchMemories = async () => {
    try {
      const data = await apiV1.get<MemoryFact[]>("/deepspace/chats/memory");
      setMemories(data);
    } catch {
      toast.error("Failed to load memories");
    }
  };

  useEffect(() => {
    void fetchMemories();
  }, []);

  const deleteMemory = async (key: string) => {
    setDeletingId(key);
    try {
      await apiV1.delete(`/deepspace/chats/memory/${encodeURIComponent(key)}`);
      setMemories((prev) => prev.filter((m) => m.key !== key));
      toast.success("Fact removed");
    } catch {
      toast.error("Deletion failed");
    } finally {
      setDeletingId(null);
    }
  };

  const filteredMemories = memories.filter(
    (m) =>
      m.key.toLowerCase().includes(search.toLowerCase()) ||
      m.value.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-6 overflow-hidden">
      <DashboardSectionHeader
        title="Autonomous Memory"
        subtitle="Audit and manage the persistent facts and live tasks AverQel has acquired."
        icon={Brain}
        accentClassName="bg-primary text-primary"
        accentGlowClassName="shadow-[0_0_20px_rgba(var(--primary),0.4)]"
      />

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-hidden">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm">
                <div className="text-foreground/40 mb-2 flex items-center gap-3">
                  <Database size={16} />
                  <span className="text-[11px] font-bold tracking-wider uppercase">
                    Total Facts
                  </span>
                </div>
                <div className="text-3xl font-black">{memories.length}</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm">
                <div className="text-foreground/40 mb-2 flex items-center gap-3">
                  <Clock size={16} />
                  <span className="text-[11px] font-bold tracking-wider uppercase">Last Sync</span>
                </div>
                <div className="text-xl font-bold">
                  {memories.length > 0
                    ? new Date(memories[0].created_at).toLocaleDateString()
                    : "N/A"}
                </div>
              </div>
              <div className="rounded-2xl border border-amber-500/10 border-white/10 bg-white/5 p-5 backdrop-blur-sm">
                <div className="mb-2 flex items-center gap-3 text-amber-500/40">
                  <ShieldAlert size={16} />
                  <span className="text-[11px] font-bold tracking-wider uppercase">
                    Security Tier
                  </span>
                </div>
                <div className="text-xl font-bold tracking-tight text-amber-500/80">
                  Level 3 Persistent
                </div>
              </div>
            </div>

            <div className="flex flex-col items-center gap-4 md:flex-row">
              <div className="relative w-full flex-1">
                <Search
                  className="text-foreground/20 absolute top-1/2 left-4 -translate-y-1/2"
                  size={18}
                />
                <input
                  type="text"
                  placeholder="Search through learned facts..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="focus:border-primary/40 w-full rounded-xl border border-white/10 bg-white/5 py-3 pr-4 pl-12 text-sm font-medium transition-all focus:outline-none"
                />
              </div>
            </div>

            <div className="theme-panel border-glass-border/40 flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl border bg-white/[0.03]">
              <div className="custom-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
                <AnimatePresence mode="popLayout">
                  {filteredMemories.length === 0 ? (
                    <div className="flex min-h-[18rem] flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.03] text-center">
                      <Database size={28} className="text-foreground/25" />
                      <p className="text-foreground/45 mt-4 text-sm font-medium">
                        No memories found.
                      </p>
                    </div>
                  ) : (
                    filteredMemories.map((memory) => (
                      <motion.div
                        key={memory.id}
                        layout
                        initial={{ opacity: 0, scale: 0.98 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.98 }}
                        className="group relative rounded-2xl border border-white/10 bg-white/5 p-6 transition-all hover:bg-white/[0.07]"
                      >
                        <div className="flex items-start justify-between gap-6">
                          <div className="flex-1 space-y-2">
                            <div className="flex items-center gap-3">
                              <h3 className="text-foreground/90 text-lg font-black tracking-tight">
                                {memory.key}
                              </h3>
                              <span className="bg-primary/10 text-primary border-primary/20 rounded-full border px-2 py-0.5 text-[10px] font-black tracking-widest uppercase">
                                {memory.scope}
                              </span>
                            </div>
                            <p className="text-foreground/50 text-sm leading-relaxed font-medium">
                              {memory.value}
                            </p>
                          </div>
                          <button
                            onClick={() => deleteMemory(memory.key)}
                            disabled={deletingId === memory.key}
                            className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-red-500 opacity-0 transition-all group-hover:opacity-100 hover:bg-red-500/20"
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      </motion.div>
                    ))
                  )}
                </AnimatePresence>
              </div>
            </div>
          </div>
      </div>

      <div className="bg-primary/5 border-primary/10 flex items-start gap-4 rounded-2xl border p-6">
        <div className="bg-primary/20 text-primary shrink-0 rounded-xl p-2">
          <Info size={20} />
        </div>
        <div className="space-y-1">
          <h4 className="text-foreground text-sm font-bold">How Autonomous Memory Works</h4>
          <p className="text-foreground/50 text-xs leading-relaxed font-medium">
            AverQel automatically stores important facts, workspace patterns, and user preferences
            to improve it proactively over time. These memories are stored locally in your workspace
            database and are never used for training models outside your tenant. You can remove
            individual facts or clear the entire cache at any time.
          </p>
        </div>
      </div>
    </div>
  );
}
