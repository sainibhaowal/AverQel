"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

import {
  MessageSquare,
  Plus,
  Sparkles,
  Users,
  Calendar,
  Search,
  Filter,
  MoreVertical,
  CheckCircle2,
  AlertCircle,
  Trophy,
  Star,
  Loader2,
  Trash2,
} from "lucide-react";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";

interface Submission {
  id: string;
  email: string;
  subject: string;
  content: string;
  category: string;
  created_at: string;
}

interface Campaign {
  id: string;
  title: string;
  description: string;
  is_active: boolean;
  created_at: string;
}

export default function AdminFeedbackPage() {
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateCampaign, setShowCreateCampaign] = useState(false);
  const [newCampaign, setNewCampaign] = useState({ title: "", description: "" });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [subRes, campRes] = await Promise.all([
        fetchWithAuth("/app-feedback/admin/submissions"),
        fetchWithAuth("/app-feedback/campaigns"),
      ]);

      if (subRes.ok) setSubmissions(await subRes.json());
      if (campRes.ok) setCampaigns(await campRes.json());
    } catch (err) {
      console.error("Failed to fetch admin data", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const res = await fetchWithAuth("/app-feedback/admin/campaigns", {
        method: "POST",
        body: JSON.stringify(newCampaign),
      });

      if (res.ok) {
        setShowCreateCampaign(false);
        setNewCampaign({ title: "", description: "" });
        fetchData();
      }
    } catch (err) {
      console.error("Failed to create campaign", err);
    } finally {
      setCreating(false);
    }
  };

  const getCategoryStyles = (category: string) => {
    switch (category) {
      case "bug":
        return { icon: <AlertCircle size={14} />, color: "text-red-400 bg-red-400/10" };
      case "achievement":
        return { icon: <Trophy size={14} />, color: "text-emerald-400 bg-emerald-400/10" };
      case "ux_improvement":
        return { icon: <Star size={14} />, color: "text-blue-400 bg-blue-400/10" };
      default:
        return { icon: <Sparkles size={14} />, color: "text-amber-400 bg-amber-400/10" };
    }
  };

  if (loading) {
    return (
      <div className="flex h-[80vh] items-center justify-center">
        <Loader2 className="text-primary animate-spin" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <div className="flex items-center justify-between">
        <DashboardSectionHeader
          title="Feedback Center"
          subtitle="Manage User Engagement And Feedback Requests"
          icon={Sparkles}
          accentClassName="bg-amber-500 text-amber-500"
          accentGlowClassName="shadow-[0_0_20px_rgba(245,158,11,0.4)]"
        />

        <button
          onClick={() => setShowCreateCampaign(true)}
          className="bg-primary shadow-primary/20 flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-bold text-black shadow-lg transition-all hover:scale-[1.02] active:scale-98"
        >
          <Plus size={18} />
          Launch Campaign
        </button>
      </div>

      <div className="grid grid-cols-1 gap-10 lg:grid-cols-4">
        {/* Campaigns Column */}
        <div className="space-y-6 lg:col-span-1">
          <h2 className="text-muted-foreground px-1 text-xs font-bold tracking-widest uppercase">
            Active Requests
          </h2>
          <div className="space-y-4">
            {campaigns.map((c) => (
              <div key={c.id} className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-primary text-[10px] font-bold uppercase">Active</span>
                  <button className="text-muted-foreground hover:text-white">
                    <MoreVertical size={14} />
                  </button>
                </div>
                <h3 className="text-sm font-bold text-white">{c.title}</h3>
                <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">{c.description}</p>
                <div className="text-muted-foreground mt-4 flex items-center gap-4 text-[10px]">
                  <span className="flex items-center gap-1">
                    <Users size={12} /> 12 Responses
                  </span>
                  <span className="flex items-center gap-1">
                    <Calendar size={12} /> 2d ago
                  </span>
                </div>
              </div>
            ))}
            {campaigns.length === 0 && (
              <p className="text-muted-foreground rounded-2xl border border-dashed border-white/10 py-10 text-center text-sm">
                No active campaigns
              </p>
            )}
          </div>
        </div>

        {/* Submissions Column */}
        <div className="space-y-6 lg:col-span-3">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-muted-foreground text-xs font-bold tracking-widest uppercase">
              User Submissions
            </h2>
            <div className="flex items-center gap-4">
              <div className="relative">
                <Search
                  size={14}
                  className="text-muted-foreground absolute top-1/2 left-3 -translate-y-1/2"
                />
                <input
                  placeholder="Search feedback..."
                  className="focus:border-primary/50 rounded-lg border border-white/10 bg-white/5 py-1.5 pr-4 pl-9 text-xs text-white focus:outline-none"
                />
              </div>
              <button className="text-muted-foreground flex items-center gap-2 text-xs hover:text-white">
                <Filter size={14} /> Filter
              </button>
            </div>
          </div>

          <div className="space-y-4">
            {submissions.map((s) => {
              const styles = getCategoryStyles(s.category);
              return (
                <motion.div
                  key={s.id}
                  layout
                  className="group relative rounded-3xl border border-white/5 bg-white/[0.03] p-6 transition-all hover:border-white/10 hover:bg-white/[0.05]"
                >
                  <div className="flex items-start justify-between gap-6">
                    <div className="flex-1 space-y-4">
                      <div className="flex items-center gap-3">
                        <span
                          className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-[10px] font-bold tracking-wider uppercase ${styles.color}`}
                        >
                          {styles.icon}
                          {s.category.replace("_", " ")}
                        </span>
                        <span className="text-muted-foreground text-xs">
                          from <b>{s.email}</b>
                        </span>
                        <span className="text-muted-foreground text-xs">
                          • {new Date(s.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-white">{s.subject}</h3>
                        <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
                          {s.content}
                        </p>
                      </div>
                    </div>
                    <div className="flex gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                      <button className="rounded-lg bg-emerald-500/10 p-2 text-emerald-500 transition-all hover:bg-emerald-500/20">
                        <CheckCircle2 size={18} />
                      </button>
                      <button className="rounded-lg bg-red-500/10 p-2 text-red-500 transition-all hover:bg-red-500/20">
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </div>
                </motion.div>
              );
            })}
            {submissions.length === 0 && (
              <div className="flex flex-col items-center justify-center rounded-3xl border border-dashed border-white/10 py-32 text-center">
                <div className="text-muted-foreground mb-4 rounded-full bg-white/5 p-4">
                  <MessageSquare size={32} />
                </div>
                <h3 className="font-bold text-white">No feedback yet</h3>
                <p className="text-muted-foreground mt-2 max-w-xs text-sm">
                  Start a campaign to encourage users to share their thoughts and experiences.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create Campaign Modal */}
      <AnimatePresence>
        {showCreateCampaign && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-6 backdrop-blur-sm"
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-surface-1 w-full max-w-lg rounded-3xl border border-white/10 p-8 shadow-2xl"
            >
              <h2 className="mb-2 text-2xl font-bold text-white">Launch New Campaign</h2>
              <p className="text-muted-foreground mb-8 text-sm">
                Request specific feedback from your users about features or improvements.
              </p>

              <form onSubmit={handleCreateCampaign} className="space-y-6">
                <div className="space-y-2">
                  <label className="text-muted-foreground text-[10px] font-bold tracking-[0.2em] uppercase">
                    Campaign Title
                  </label>
                  <input
                    required
                    value={newCampaign.title}
                    onChange={(e) => setNewCampaign({ ...newCampaign, title: e.target.value })}
                    placeholder="e.g. New DeepSpace Experience"
                    className="focus:border-primary/50 w-full rounded-xl border border-white/10 bg-white/5 p-4 text-white transition-all focus:outline-none"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-muted-foreground text-[10px] font-bold tracking-[0.2em] uppercase">
                    Request Details
                  </label>
                  <textarea
                    required
                    rows={4}
                    value={newCampaign.description}
                    onChange={(e) =>
                      setNewCampaign({ ...newCampaign, description: e.target.value })
                    }
                    placeholder="What specific input do you need from users?"
                    className="focus:border-primary/50 w-full resize-none rounded-xl border border-white/10 bg-white/5 p-4 text-white transition-all focus:outline-none"
                  />
                </div>

                <div className="flex gap-4 pt-4">
                  <button
                    type="button"
                    onClick={() => setShowCreateCampaign(false)}
                    className="flex-1 rounded-xl border border-white/10 py-3 text-sm font-bold text-white transition-all hover:bg-white/5"
                  >
                    Cancel
                  </button>
                  <button
                    disabled={creating}
                    className="bg-primary flex-1 rounded-xl py-3 text-sm font-bold text-black transition-all hover:scale-[1.02] active:scale-98 disabled:opacity-50"
                  >
                    {creating ? <Loader2 className="animate-spin" size={18} /> : "Launch Now"}
                  </button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
