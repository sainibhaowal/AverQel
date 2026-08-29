"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import toast from "react-hot-toast";
import {
  MessageSquare,
  Search,
  Loader2,
  User,
  CheckCircle2,
  Clock,
  ChevronRight,
  Trash2,
  Mail,
  MoreVertical,
  LifeBuoy,
} from "lucide-react";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";

interface Ticket {
  id: string;
  subject: string;
  description: string;
  category: string;
  status: string;
  created_at: string;
  updated_at: string;
}

interface UserSummary {
  user_id: string;
  email: string;
  ticket_count: number;
  last_ticket_at: string;
  latest_tickets: Ticket[];
}

function SupportContent() {
  const searchParams = useSearchParams();
  const queryUserId = searchParams.get("user");

  const [users, setUsers] = useState<UserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(queryUserId);
  const [searchQuery, setSearchQuery] = useState("");

  const loadData = useCallback(async () => {
    try {
      const res = await fetchWithAuth("/support/admin/tickets");
      if (res.ok) {
        const data = await res.json();
        setUsers(data.items);
        if (data.items.length > 0 && !selectedUserId) {
          setSelectedUserId(data.items[0].user_id);
        } else if (queryUserId && data.items.some((u: UserSummary) => u.user_id === queryUserId)) {
          setSelectedUserId(queryUserId);
        }
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to load support data.");
    } finally {
      setLoading(false);
    }
  }, [queryUserId, selectedUserId]);

  useEffect(() => {
    queueMicrotask(() => void loadData());
  }, [loadData]);

  const handleUpdateStatus = async (ticketId: string, newStatus: string) => {
    try {
      const res = await fetchWithAuth(`/support/admin/tickets/${ticketId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        toast.success(`Status updated to ${newStatus}`);
        void loadData();
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to update status.");
    }
  };

  const selectedUser = users.find((u) => u.user_id === selectedUserId);
  const filteredUsers = users.filter((u) =>
    u.email.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case "open":
        return <Clock className="text-blue-400" size={14} />;
      case "in_progress":
        return <Loader2 className="animate-spin text-yellow-400" size={14} />;
      case "resolved":
        return <CheckCircle2 className="text-green-400" size={14} />;
      case "closed":
        return <CheckCircle2 className="text-slate-500" size={14} />;
      default:
        return <Clock size={14} />;
    }
  };

  return (
    <div className="flex min-h-[calc(100svh-14rem)] w-full flex-col lg:h-[calc(100svh-14rem)]">
      <DashboardSectionHeader
        title="Support Management"
        subtitle="Manage user queries, feedback and complaints"
        icon={LifeBuoy}
        accentClassName="bg-purple-500 text-purple-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(168,85,247,0.4)]"
      />

      <div className="mt-6 flex flex-1 flex-col gap-6 overflow-hidden xl:flex-row">
        {/* Users List - Left Side */}
        <div className="theme-panel flex w-full flex-col overflow-hidden rounded-[2rem] border-white/10 xl:w-80">
          <div className="border-b border-white/10 p-6">
            <div className="relative">
              <Search
                className="absolute top-1/2 left-3 -translate-y-1/2 text-slate-500"
                size={16}
              />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search users..."
                className="focus:border-primary/40 w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pr-4 pl-10 text-xs text-white transition outline-none"
              />
            </div>
          </div>

          <div className="flex-1 space-y-2 overflow-y-auto p-3">
            {loading ? (
              <div className="flex justify-center py-20">
                <Loader2 className="text-primary animate-spin" size={32} />
              </div>
            ) : filteredUsers.length === 0 ? (
              <div className="py-20 text-center text-xs text-slate-500 italic">No users found.</div>
            ) : (
              filteredUsers.map((u) => (
                <button
                  key={u.user_id}
                  onClick={() => setSelectedUserId(u.user_id)}
                  className={`group flex w-full items-center gap-3 rounded-2xl p-3 transition ${
                    selectedUserId === u.user_id
                      ? "bg-primary/10 border-primary/20 border"
                      : "border border-transparent hover:bg-white/5"
                  }`}
                >
                  <div
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl font-bold ${
                      selectedUserId === u.user_id
                        ? "bg-primary text-black"
                        : "bg-white/10 text-slate-300"
                    }`}
                  >
                    {u.email[0].toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1 text-left">
                    <p
                      className={`truncate text-xs font-bold ${selectedUserId === u.user_id ? "text-white" : "text-slate-300"}`}
                    >
                      {u.email}
                    </p>
                    <p className="mt-0.5 text-[10px] text-slate-500">
                      {u.ticket_count} {u.ticket_count === 1 ? "ticket" : "tickets"}
                    </p>
                  </div>
                  {selectedUserId === u.user_id && (
                    <ChevronRight className="text-primary" size={14} />
                  )}
                </button>
              ))
            )}
          </div>
        </div>

        {/* Tickets View - Right Side */}
        <div className="theme-panel flex flex-1 flex-col overflow-hidden rounded-[2rem] border-white/10">
          {selectedUser ? (
            <>
              <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.02] p-8">
                <div className="flex items-center gap-4">
                  <div className="text-primary flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
                    <User size={28} />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">{selectedUser.email}</h3>
                    <p className="text-xs text-slate-500">User ID: {selectedUser.user_id}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-slate-400 transition hover:text-white">
                    <Mail size={18} />
                  </button>
                  <button className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-slate-400 transition hover:text-white">
                    <MoreVertical size={18} />
                  </button>
                </div>
              </div>

              <div className="flex-1 space-y-6 overflow-y-auto p-8">
                {selectedUser.latest_tickets.map((ticket) => (
                  <motion.div
                    key={ticket.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03]"
                  >
                    <div className="p-6">
                      <div className="mb-4 flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span
                              className={`rounded-full border px-2 py-0.5 text-[9px] font-black tracking-tighter uppercase ${
                                ticket.category === "complaint"
                                  ? "border-red-500/20 bg-red-500/10 text-red-400"
                                  : ticket.category === "feedback"
                                    ? "border-purple-500/20 bg-purple-500/10 text-purple-400"
                                    : "border-blue-500/20 bg-blue-500/10 text-blue-400"
                              }`}
                            >
                              {ticket.category}
                            </span>
                            <span className="font-mono text-[10px] text-slate-600">
                              #{ticket.id.slice(0, 8)}
                            </span>
                          </div>
                          <h4 className="text-base font-bold text-white">{ticket.subject}</h4>
                        </div>

                        <div className="flex items-center gap-2">
                          <div
                            className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-[10px] font-bold ${
                              ticket.status === "open"
                                ? "border-blue-500/20 text-blue-400"
                                : ticket.status === "in_progress"
                                  ? "border-yellow-500/20 text-yellow-400"
                                  : ticket.status === "resolved"
                                    ? "border-green-500/20 text-green-400"
                                    : "border-white/10 text-slate-500"
                            }`}
                          >
                            {getStatusIcon(ticket.status)}
                            {ticket.status.replace("_", " ").toUpperCase()}
                          </div>
                        </div>
                      </div>

                      <div className="rounded-2xl border border-white/5 bg-black/40 p-5 text-sm leading-relaxed text-slate-300">
                        {ticket.description}
                      </div>

                      <div className="mt-6 flex items-center justify-between">
                        <p className="text-[10px] font-medium text-slate-500">
                          Submitted on {new Date(ticket.created_at).toLocaleString()}
                        </p>

                        <div className="flex items-center gap-2">
                          {ticket.status !== "resolved" && (
                            <button
                              onClick={() => handleUpdateStatus(ticket.id, "resolved")}
                              className="rounded-lg border border-green-500/20 bg-green-500/10 px-3 py-1.5 text-[10px] font-bold text-green-400 transition hover:bg-green-500/20"
                            >
                              Mark Resolved
                            </button>
                          )}
                          {ticket.status === "open" && (
                            <button
                              onClick={() => handleUpdateStatus(ticket.id, "in_progress")}
                              className="rounded-lg border border-yellow-500/20 bg-yellow-500/10 px-3 py-1.5 text-[10px] font-bold text-yellow-400 transition hover:bg-yellow-500/20"
                            >
                              In Progress
                            </button>
                          )}
                          <button className="rounded-lg border border-red-500/10 bg-red-500/5 px-3 py-1.5 text-[10px] font-bold text-red-500/40 transition hover:bg-red-500/10 hover:text-red-500">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center p-20 text-center">
              <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-3xl bg-white/5 text-slate-700">
                <MessageSquare size={48} />
              </div>
              <h3 className="mb-2 text-xl font-bold text-white">No User Selected</h3>
              <p className="max-w-md text-slate-500">
                Select a user from the left panel to view their support history and manage tickets.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AdminSupportPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full w-full items-center justify-center">
          <Loader2 className="text-primary animate-spin" size={48} />
        </div>
      }
    >
      <SupportContent />
    </Suspense>
  );
}
