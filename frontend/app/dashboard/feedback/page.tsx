"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquare,
  Send,
  Star,
  Trophy,
  Sparkles,
  ChevronRight,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/api";

interface Campaign {
  id: string;
  title: string;
  description: string;
  created_at: string;
}

type FeedbackCategory = "suggestion" | "bug" | "achievement" | "ux_improvement";

const categories: Array<{
  id: FeedbackCategory;
  label: string;
  icon: React.ReactNode;
  color: string;
}> = [
  { id: "suggestion", label: "Suggestion", icon: <Sparkles size={16} />, color: "text-amber-400" },
  { id: "bug", label: "Bug Report", icon: <MessageSquare size={16} />, color: "text-red-400" },
  {
    id: "achievement",
    label: "Achievement",
    icon: <Trophy size={16} />,
    color: "text-emerald-400",
  },
  {
    id: "ux_improvement",
    label: "UX Improvement",
    icon: <Star size={16} />,
    color: "text-blue-400",
  },
];

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";

export default function FeedbackPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null);
  const [formData, setFormData] = useState({
    subject: "",
    content: "",
    category: "suggestion" as FeedbackCategory,
  });

  useEffect(() => {
    fetchCampaigns();
  }, []);

  const fetchCampaigns = async () => {
    try {
      const res = await fetchWithAuth("/app-feedback/campaigns");

      if (res.ok) {
        const data = await res.json();
        setCampaigns(data);
      }
    } catch (err) {
      console.error("Failed to fetch campaigns", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await fetchWithAuth("/app-feedback/submit", {
        method: "POST",
        body: JSON.stringify({
          ...formData,
          campaign_id: selectedCampaign?.id || null,
        }),
      });

      if (res.ok) {
        setSuccess(true);
        setFormData({ subject: "", content: "", category: "suggestion" });
        setSelectedCampaign(null);
        setTimeout(() => setSuccess(false), 5000);
      }
    } catch (err) {
      console.error("Submission failed", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-10">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
      >
        <DashboardSectionHeader
          title="Feedback Center"
          subtitle="Help Us Shape The Future Of AverQel"
          icon={Sparkles}
          accentClassName="bg-amber-400 text-amber-400"
          accentGlowClassName="shadow-[0_0_20px_rgba(251,191,36,0.4)]"
        />
      </motion.div>

      <div className="grid grid-cols-1 gap-10 lg:grid-cols-3">
        {/* Left: Active Campaigns */}
        <div className="space-y-6 lg:col-span-1">
          <h2 className="flex items-center gap-2 text-xl font-semibold text-white/90">
            <Sparkles className="text-primary" size={20} />
            Active Requests
          </h2>

          {loading ? (
            <div className="flex h-32 items-center justify-center rounded-2xl border border-white/5 bg-white/[0.02]">
              <Loader2 className="text-primary animate-spin" size={24} />
            </div>
          ) : campaigns.length > 0 ? (
            <div className="space-y-4">
              {campaigns.map((c) => (
                <motion.button
                  key={c.id}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => {
                    setSelectedCampaign(c);
                    setFormData((prev) => ({ ...prev, subject: `Response to: ${c.title}` }));
                  }}
                  className={`w-full rounded-2xl border p-5 text-left transition-all ${
                    selectedCampaign?.id === c.id
                      ? "border-primary/50 bg-primary/10 shadow-[0_0_20px_rgba(var(--primary),0.1)]"
                      : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"
                  }`}
                >
                  <h3 className="mb-1 font-bold text-white">{c.title}</h3>
                  <p className="text-muted-foreground line-clamp-2 text-sm">{c.description}</p>
                  <div className="text-primary/70 mt-4 flex items-center gap-1 text-[10px] font-bold tracking-widest uppercase">
                    Respond Now <ChevronRight size={10} />
                  </div>
                </motion.button>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-8 text-center">
              <p className="text-muted-foreground text-sm">
                No active feedback requests at the moment. General suggestions are always welcome!
              </p>
            </div>
          )}
        </div>

        <div className="lg:col-span-2">
          <motion.div layout className="theme-panel p-8 shadow-2xl backdrop-blur-xl">
            <AnimatePresence mode="wait">
              {success ? (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  className="flex flex-col items-center justify-center py-20 text-center"
                >
                  <div className="mb-6 rounded-full bg-emerald-500/20 p-4 text-emerald-500 shadow-[0_0_30px_rgba(16,185,129,0.2)]">
                    <CheckCircle2 size={48} />
                  </div>
                  <h2 className="text-foreground text-2xl font-bold">Thank You!</h2>
                  <p className="text-muted-foreground mt-2">
                    Your feedback has been submitted successfully. We appreciate your input!
                  </p>

                  <button
                    onClick={() => setSuccess(false)}
                    className="bg-foreground/10 text-foreground hover:bg-foreground/20 mt-8 rounded-xl px-6 py-2 text-sm font-semibold transition-all"
                  >
                    Send Another
                  </button>
                </motion.div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-8">
                  {selectedCampaign && (
                    <motion.div
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      className="bg-primary/10 border-primary/20 flex items-center justify-between rounded-xl border p-4"
                    >
                      <div>
                        <p className="text-primary text-[10px] font-bold tracking-widest uppercase">
                          Responding to request
                        </p>
                        <p className="text-foreground text-sm font-semibold">
                          {selectedCampaign.title}
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          setSelectedCampaign(null);
                          setFormData((prev) => ({ ...prev, subject: "" }));
                        }}
                        className="text-muted-foreground hover:text-foreground transition-colors"
                      >
                        Cancel
                      </button>
                    </motion.div>
                  )}

                  <div className="flex flex-wrap gap-3">
                    {categories.map((cat) => (
                      <button
                        key={cat.id}
                        type="button"
                        onClick={() => setFormData({ ...formData, category: cat.id })}
                        className={`flex min-w-[140px] flex-1 items-center gap-3 rounded-xl border p-4 transition-all ${
                          formData.category === cat.id
                            ? "border-primary/30 bg-primary/10 text-primary shadow-[0_0_15px_rgba(var(--primary),0.1)]"
                            : "border-foreground/10 bg-foreground/[0.02] hover:bg-foreground/[0.05]"
                        }`}
                      >
                        <span className={cat.color}>{cat.icon}</span>
                        <span
                          className={`text-sm font-bold ${formData.category === cat.id ? "text-primary" : "text-foreground"}`}
                        >
                          {cat.label}
                        </span>
                      </button>
                    ))}
                  </div>

                  <div className="space-y-6">
                    <div className="space-y-2">
                      <label className="text-muted-foreground text-xs font-bold tracking-widest uppercase">
                        Subject
                      </label>
                      <input
                        required
                        value={formData.subject}
                        onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                        placeholder="What's on your mind?"
                        className="border-foreground/10 bg-foreground/[0.02] text-foreground placeholder:text-muted-foreground/30 focus:border-primary/50 focus:bg-foreground/[0.05] w-full rounded-xl border p-4 transition-all focus:outline-none"
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="text-muted-foreground text-xs font-bold tracking-widest uppercase">
                        Description
                      </label>
                      <textarea
                        required
                        rows={6}
                        value={formData.content}
                        onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                        placeholder="Tell us more about your suggestion, bug, or achievement..."
                        className="border-foreground/10 bg-foreground/[0.02] text-foreground placeholder:text-muted-foreground/30 focus:border-primary/50 focus:bg-foreground/[0.05] w-full resize-none rounded-2xl border p-4 transition-all focus:outline-none"
                      />
                    </div>
                  </div>

                  <button
                    disabled={submitting}
                    className="bg-primary flex w-full items-center justify-center gap-2 rounded-2xl py-4 font-black !text-white shadow-[0_0_20px_rgba(var(--primary),0.2)] transition-all hover:shadow-[0_0_30px_rgba(var(--primary),0.3)] active:scale-[0.99] disabled:opacity-50"
                  >
                    {submitting ? (
                      <Loader2 className="animate-spin !text-white" size={20} />
                    ) : (
                      <Send className="!text-white" size={20} />
                    )}
                    Submit Feedback
                  </button>
                </form>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
