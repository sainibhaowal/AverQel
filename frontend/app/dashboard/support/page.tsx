"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import toast from "react-hot-toast";
import {
  Send,
  History,
  Loader2,
  AlertCircle,
  HelpCircle,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  LifeBuoy,
} from "lucide-react";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";
import { useAuth } from "@/app/context/AuthContext";

interface Ticket {
  id: string;
  subject: string;
  description: string;
  category: string;
  status: string;
  created_at: string;
}

export default function SupportPage() {
  const { userDisabled } = useAuth();
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<"complaint" | "feedback" | "query">("query");
  const [submitting, setSubmitting] = useState(false);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedTicket, setExpandedTicket] = useState<string | null>(null);

  const loadTickets = async () => {
    try {
      const res = await fetchWithAuth("/support/tickets");
      if (res.ok) {
        const data = await res.json();
        setTickets(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadTickets();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subject.trim() || !description.trim()) {
      toast.error("Please fill in all fields.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetchWithAuth("/support/tickets", {
        method: "POST",
        body: JSON.stringify({ subject, description, category }),
      });

      if (res.ok) {
        toast.success("Support ticket submitted successfully.");
        setSubject("");
        setDescription("");
        setCategory("query");
        void loadTickets();
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to submit ticket.");
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "open":
        return "bg-blue-500/10 text-blue-400 border-blue-500/20";
      case "in_progress":
        return "bg-yellow-500/10 text-yellow-400 border-yellow-500/20";
      case "resolved":
        return "bg-green-500/10 text-green-400 border-green-500/20";
      case "closed":
        return "bg-slate-500/10 text-slate-400 border-slate-500/20";
      default:
        return "bg-slate-500/10 text-slate-400 border-slate-500/20";
    }
  };

  return (
    <div className="w-full space-y-8 pb-12">
      {userDisabled && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-4 rounded-[2rem] border border-amber-500/20 bg-amber-500/10 p-6"
        >
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-amber-500/20 text-amber-500">
            <AlertCircle size={24} />
          </div>
          <div>
            <h4 className="text-xs font-bold tracking-wider text-amber-500 uppercase">
              Account Restricted
            </h4>
            <p className="mt-1 text-sm text-amber-200/70">
              Your account is currently disabled. Please use this form to submit a request for
              reactivation or inquiry.
            </p>
          </div>
        </motion.div>
      )}
      <DashboardSectionHeader
        title="Support Center"
        subtitle="Global Resolution Gateway"
        icon={LifeBuoy}
        accentClassName="bg-purple-500 text-purple-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(168,85,247,0.4)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
      />

      <div className="grid gap-8 lg:grid-cols-[1fr_24rem]">
        {/* Submit Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="theme-panel rounded-[2rem] p-8"
        >
          <div className="mb-8">
            <h2 className="text-foreground text-xl font-bold">How can we help?</h2>
            <p className="text-muted-foreground mt-2 text-sm">
              Submit your queries, feedback or complaints. Our team will get back to you shortly.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid gap-8 lg:grid-cols-2">
              <div className="space-y-2">
                <label className="text-muted-foreground text-xs font-bold tracking-[0.15em] uppercase">
                  Topic / Category
                </label>

                <div className="flex flex-wrap gap-2">
                  {(["query", "feedback", "complaint"] as const).map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => setCategory(cat)}
                      className={`min-w-[90px] flex-1 rounded-xl border py-3 text-[10px] font-black tracking-[0.12em] uppercase transition ${
                        category === cat
                          ? "border-primary bg-primary/10 text-primary shadow-[0_0_15px_rgba(var(--primary),0.1)]"
                          : "border-foreground/10 bg-foreground/5 text-muted-foreground hover:bg-foreground/10"
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-muted-foreground text-xs font-bold tracking-[0.15em] uppercase">
                  Subject
                </label>
                <input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Summarize your issue..."
                  className="border-foreground/10 bg-foreground/5 text-foreground focus:border-primary/40 focus:ring-primary/20 w-full rounded-xl border px-4 py-3 text-sm transition outline-none focus:ring-1"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-muted-foreground text-xs font-bold tracking-[0.15em] uppercase">
                Detailed Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Please provide as much detail as possible..."
                rows={6}
                className="border-foreground/10 bg-foreground/5 text-foreground focus:border-primary/40 focus:ring-primary/20 w-full resize-none rounded-2xl border px-4 py-4 text-sm transition outline-none focus:ring-1"
              />
            </div>

            <div className="flex justify-end pt-2">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                disabled={submitting}
                className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-xl px-8 py-3.5 text-sm font-bold text-white shadow-[0_8px_16px_rgba(var(--primary),0.25)] transition disabled:opacity-50"
              >
                {submitting ? (
                  <Loader2 className="animate-spin text-white" size={18} />
                ) : (
                  <Send className="text-white" size={18} />
                )}
                Submit Ticket
              </motion.button>
            </div>
          </form>
        </motion.div>

        {/* History Section */}
        <div className="space-y-6">
          <div className="theme-panel rounded-[2rem] p-6">
            <div className="mb-6 flex items-center gap-3">
              <History className="text-primary" size={20} />
              <h3 className="text-foreground text-sm font-bold tracking-[0.15em] uppercase">
                Recent Tickets
              </h3>
            </div>

            <div className="space-y-4">
              {loading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="animate-spin text-slate-500" size={24} />
                </div>
              ) : tickets.length === 0 ? (
                <div className="bg-foreground/[0.03] border-foreground/10 rounded-2xl border border-dashed p-8 text-center">
                  <HelpCircle className="text-muted-foreground mx-auto mb-3" size={32} />
                  <p className="text-muted-foreground text-sm italic">No tickets submitted yet.</p>
                </div>
              ) : (
                tickets.map((ticket) => (
                  <div
                    key={ticket.id}
                    className="group border-foreground/10 bg-foreground/[0.03] hover:border-primary/20 overflow-hidden rounded-2xl border transition"
                  >
                    <button
                      onClick={() =>
                        setExpandedTicket(expandedTicket === ticket.id ? null : ticket.id)
                      }
                      className="flex w-full items-start gap-4 p-4 text-left"
                    >
                      <div className="mt-1 flex flex-col items-center gap-1">
                        <span
                          className={`h-2 w-2 rounded-full ${
                            ticket.status === "open"
                              ? "bg-blue-500"
                              : ticket.status === "in_progress"
                                ? "bg-yellow-500"
                                : ticket.status === "resolved"
                                  ? "bg-green-500"
                                  : "bg-slate-500"
                          }`}
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-foreground truncate text-sm font-semibold">
                          {ticket.subject}
                        </p>

                        <div className="mt-2 flex items-center gap-2">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-tighter uppercase ${getStatusColor(ticket.status)}`}
                          >
                            {ticket.status.replace("_", " ")}
                          </span>
                          <span className="text-muted-foreground text-[10px]">
                            {new Date(ticket.created_at).toLocaleDateString()}
                          </span>
                        </div>
                      </div>
                      <div className="text-muted-foreground group-hover:text-primary mt-1 transition-colors">
                        {expandedTicket === ticket.id ? (
                          <ChevronUp size={16} />
                        ) : (
                          <ChevronDown size={16} />
                        )}
                      </div>
                    </button>

                    {expandedTicket === ticket.id && (
                      <div className="text-muted-foreground border-foreground/5 bg-foreground/5 mt-2 border-t px-4 py-3 pt-0 pb-4 text-xs">
                        <p className="leading-relaxed whitespace-pre-wrap">{ticket.description}</p>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Help Card */}
          <div className="bg-primary/10 border-primary/20 rounded-[2rem] border p-6">
            <div className="text-primary mb-3 flex items-center gap-3">
              <ShieldCheck size={20} />
              <h4 className="text-sm font-bold tracking-wider uppercase">Priority Support</h4>
            </div>
            <p className="text-muted-foreground text-xs leading-relaxed font-medium">
              Our support team is available 24/7 for critical infrastructure issues. Non-critical
              queries are typically resolved within 2-4 business hours.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
