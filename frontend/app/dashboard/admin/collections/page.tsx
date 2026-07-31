"use client";

/* The existing collection API has multiple server response versions; its
 * compatibility boundary is intentionally isolated to this page. */
/* eslint-disable @typescript-eslint/no-explicit-any */
/* User avatars are remote or data URLs and must bypass Next's server image optimizer. */
/* eslint-disable @next/next/no-img-element */

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Copy,
  FolderKanban,
  Users,
  MessageSquare,
  Search,
  Plus,
  Check,
  X,
  FileStack,
  Trash2,
  ChevronLeft,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import toast from "react-hot-toast";

const DEFAULT_AVATAR_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%23f59e0b"/><stop offset="100%" stop-color="%2310b981"/></linearGradient></defs><circle cx="50" cy="50" r="50" fill="url(%23g)"/><path d="M50 30a15 15 0 1 0 0 30 15 15 0 0 0 0-30zM50 67c-18 0-32 10-32 20v3h64v-3c0-10-14-20-32-20z" fill="%230f172a"/></svg>`;
import { fetchWithAuth } from "@/lib/api";
import { AnimatePresence, motion } from "framer-motion";
import CollectionDetailClient from "./[collectionId]/CollectionDetailClient";
import { getUnreadCount, incrementUnreadCount, saveLocalMessage } from "@/lib/localDb";
import { deriveKey, decryptMessage } from "@/lib/crypto";

interface Collection {
  id: string;
  name: string;
  description: string;
  connection_code: string;
  requester_access_role?: "owner" | "member" | "pending" | null;
  member_count: number;
  other_member_email?: string | null;
  other_member_avatar?: string | null;
  created_at: string;
}

interface Invitation extends Collection {
  inviter_user_id?: string | null;
  inviter_user_email?: string | null;
}

export default function AdminCollectionsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const collectionsBasePath = pathname.startsWith("/dashboard/admin/collections")
    ? "/dashboard/admin/collections"
    : "/dashboard/collections";

  const [collections, setCollections] = useState<Collection[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);

  // Unread badge counts state
  const [unreadCounts, setUnreadCounts] = useState<Record<string, number>>({});

  // Sidebar selection & collapse
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Load unread counts from local IndexedDB cache
  useEffect(() => {
    const loadUnread = async () => {
      const counts: Record<string, number> = {};
      for (const col of collections) {
        try {
          counts[col.id] = await getUnreadCount(col.id);
        } catch {
          counts[col.id] = 0;
        }
      }
      setUnreadCounts(counts);
    };

    void loadUnread();
    const interval = window.setInterval(loadUnread, 4500);
    return () => window.clearInterval(interval);
  }, [collections, activeCollectionId]);

  // Manage background WebSocket connections for non-active chats (WhatsApp-style real-time delivery and badges)
  const bgSocketsRef = useRef<Record<string, WebSocket>>({});
  useEffect(() => {
    if (typeof window === "undefined" || collections.length === 0) return;
    const token = window.localStorage.getItem("averqel_token");
    const tenantId = window.localStorage.getItem("averqel_tenant_id");
    if (!token) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;

    const activeBgIds = new Set(
      collections
        .filter((c) => c.id !== activeCollectionId)
        .map((c) => c.id)
    );

    // 1. Terminate sockets that are no longer needed
    Object.keys(bgSocketsRef.current).forEach((id) => {
      if (!activeBgIds.has(id)) {
        console.log(`Closing background socket for collection: ${id}`);
        bgSocketsRef.current[id].close();
        delete bgSocketsRef.current[id];
      }
    });

    // 2. Open background sockets for non-active chats
    collections.forEach((col) => {
      if (col.id === activeCollectionId) return;
      if (bgSocketsRef.current[col.id]) return; // Already connected

      const params = new URLSearchParams();
      params.set("token", token);
      if (tenantId) params.set("tenant_id", tenantId);
      const wsUrl = `${protocol}//${host}/api/v1/collections/${col.id}/ws?${params.toString()}`;

      console.log(`Opening background socket for collection: ${col.id}`);
      const ws = new WebSocket(wsUrl);
      bgSocketsRef.current[col.id] = ws;

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);
          if (!data.payload && data.data) data.payload = data.data;

          if (data.type === "new_message" && data.payload) {
            const msg = data.payload;

            // Decrypt the background message using derived E2EE key
            const key = await deriveKey(col.id, col.connection_code);
            let decryptedText = msg.message;
            try {
              decryptedText = await decryptMessage(msg.message, key);
            } catch (decErr) {
              console.warn("Failed to decrypt background message:", decErr);
            }

            const decryptedMsg = { ...msg, message: decryptedText };
            await saveLocalMessage(decryptedMsg);

            // Respond with 'delivered' status so sender sees double tick
            ws.send(JSON.stringify({ action: "delivered", message_id: msg.id }));

            // Increment local unread counts
            const nextCount = await incrementUnreadCount(col.id);
            setUnreadCounts((prev) => ({
              ...prev,
              [col.id]: nextCount,
            }));
          }
        } catch (err) {
          console.error(`Error in background WS for collection ${col.id}:`, err);
        }
      };

      ws.onclose = () => {
        if (bgSocketsRef.current[col.id] === ws) {
          delete bgSocketsRef.current[col.id];
        }
      };
    });

    return () => {};
  }, [collections, activeCollectionId]);

  useEffect(() => {
    return () => {
      // Close all sockets when component is completely unmounted
      Object.values(bgSocketsRef.current).forEach((ws) => ws.close());
      bgSocketsRef.current = {};
    };
  }, []);

  // Drawer state synced from parent to child
  const [activeDrawer, setActiveDrawer] = useState<"documents" | "members" | null>(null);

  // Modal Flow
  const [showCreate, setShowCreate] = useState(false);
  const [createMode, setCreateMode] = useState<"direct" | "group">("direct");
  const [directCode, setDirectCode] = useState("");
  const [directName, setDirectName] = useState("");
  const [groupName, setGroupName] = useState("");
  const [groupDesc, setGroupDesc] = useState("");
  const [groupCodes, setGroupCodes] = useState(""); // Comma separated codes

  const [mutatingId, setMutatingId] = useState<string | null>(null);
  const [myCollectionCode, setMyCollectionCode] = useState("");
  const [showProfileSettings, setShowProfileSettings] = useState(false);
  const [userProfile, setUserProfile] = useState<any>(null);
  const [previewAvatar, setPreviewAvatar] = useState("");
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    if (showProfileSettings && userProfile) {
      setPreviewAvatar(userProfile.avatar || DEFAULT_AVATAR_SVG);
      setZoom(1);
    }
  }, [showProfileSettings, userProfile]);
  const notifiedPendingRef = useRef(false);

  // Sync initial selection from search params or legacy dynamic route params
  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    const queryId = searchParams.get("id");
    if (queryId) {
      setActiveCollectionId(queryId);
      return;
    }

    const parts = pathname.split("/");
    const pathId = parts[parts.length - 1];
    if (pathId && pathId !== "collections" && pathId !== "admin") {
      setActiveCollectionId(pathId);
    } else {
      setActiveCollectionId(null);
    }
  }, [pathname, searchParams]);

  // Synchronize state with browser back/forward button clicks (popstate)
  useEffect(() => {
    const handlePopState = () => {
      const searchParams = new URLSearchParams(window.location.search);
      const queryId = searchParams.get("id");
      if (queryId) {
        setActiveCollectionId(queryId);
        return;
      }

      const parts = window.location.pathname.split("/");
      const pathId = parts[parts.length - 1];
      if (pathId && pathId !== "collections" && pathId !== "admin") {
        setActiveCollectionId(pathId);
      } else {
        setActiveCollectionId(null);
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const fetchCollections = async () => {
    try {
      const [collectionsRes, invitationsRes, profileRes] = await Promise.all([
        fetchWithAuth("/collections"),
        fetchWithAuth("/collections/invitations"),
        fetchWithAuth("/auth/profile"),
      ]);
      if (collectionsRes.ok) {
        setCollections(await collectionsRes.json());
      }
      if (profileRes.ok) {
        const profileData = (await profileRes.json()) as any;
        setMyCollectionCode(profileData.collection_code);
        setUserProfile(profileData);
      }
      if (invitationsRes.ok) {
        const pendingItems = (await invitationsRes.json()) as Invitation[];
        setInvitations(pendingItems);
        if (pendingItems.length > 0 && !notifiedPendingRef.current) {
          toast(
            `${pendingItems.length} collection invitation${pendingItems.length > 1 ? "s" : ""} waiting`,
            { icon: "📨" }
          );
          notifiedPendingRef.current = true;
        }
      } else {
        setInvitations([]);
      }
    } catch (error) {
      console.error(error);
      toast.error("Failed to load collection bridge data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchCollections();
    const interval = window.setInterval(() => {
      void fetchCollections();
    }, 15000);
    return () => window.clearInterval(interval);
  }, []);

  const handleCreateDirectChat = async () => {
    const targetCode = directCode.trim().toUpperCase();
    if (!targetCode) {
      toast.error("Please enter a valid Connection ID.");
      return;
    }
    setLoading(true);
    try {
      const createRes = await fetchWithAuth("/collections", {
        method: "POST",
        body: JSON.stringify({
          name: directName.trim() || "Direct Chat",
          description: `1:1 Connection with ${targetCode}`,
        }),
      });
      if (!createRes.ok) throw new Error("Failed to initialize chat connection.");
      const newColl = await createRes.json();

      try {
        const permRes = await fetchWithAuth(`/collections/${newColl.id}/permissions`, {
          method: "POST",
          body: JSON.stringify({ connection_code: targetCode }),
        });
        if (!permRes.ok) {
          const errData = await permRes.json().catch(() => ({}));
          throw new Error(errData.message || "Failed to dispatch connection request.");
        }

        toast.success("Direct connection request dispatched.");
        setDirectCode("");
        setDirectName("");
        setShowCreate(false);
        await fetchCollections();
        handleSelectCollection(newColl.id);
      } catch (err: any) {
        // Clean up the empty collection
        await fetchWithAuth(`/collections/${newColl.id}`, { method: "DELETE" });
        throw err;
      }
    } catch (error) {
      console.error(error);
      toast.error(error instanceof Error ? error.message : "Failed to establish direct connection.");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateGroupChat = async () => {
    const name = groupName.trim();
    if (!name) {
      toast.error("Please enter a Group Name.");
      return;
    }
    const codes = groupCodes
      .split(/[\s,]+/)
      .map((c) => c.trim().toUpperCase())
      .filter(Boolean);

    setLoading(true);
    try {
      const createRes = await fetchWithAuth("/collections", {
        method: "POST",
        body: JSON.stringify({
          name: name,
          description: groupDesc.trim() || "Shared group bridge workspace.",
        }),
      });
      if (!createRes.ok) throw new Error("Failed to initialize group bridge.");
      const newColl = await createRes.json();

      if (codes.length > 0) {
        const invitePromises = codes.map((code) =>
          fetchWithAuth(`/collections/${newColl.id}/permissions`, {
            method: "POST",
            body: JSON.stringify({ connection_code: code }),
          })
        );
        await Promise.all(invitePromises);
      }

      toast.success("Group workspace bridge created.");
      setGroupName("");
      setGroupDesc("");
      setGroupCodes("");
      setShowCreate(false);
      await fetchCollections();

      handleSelectCollection(newColl.id);
    } catch (error) {
      console.error(error);
      toast.error("Failed to establish group bridge connection.");
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      toast.error("Profile picture must be under 2MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setPreviewAvatar(reader.result);
        setZoom(1);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleSaveProfile = async () => {
    try {
      let finalAvatarUrl = previewAvatar;
      // If it is a custom uploaded image, crop it with the zoom!
      if (previewAvatar && previewAvatar.startsWith("data:image/") && !previewAvatar.includes("svg+xml")) {
        const img = new Image();
        img.src = previewAvatar;
        await new Promise((resolve) => { img.onload = resolve; });
        const canvas = document.createElement("canvas");
        canvas.width = 150;
        canvas.height = 150;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          // Center and draw with zoom!
          const size = Math.min(img.width, img.height);
          const cropSize = size / zoom;
          const sx = (img.width - cropSize) / 2;
          const sy = (img.height - cropSize) / 2;
          ctx.drawImage(img, sx, sy, cropSize, cropSize, 0, 0, 150, 150);
          finalAvatarUrl = canvas.toDataURL("image/jpeg", 0.85);
        }
      }
      // Send to backend profile PUT
      const res = await fetchWithAuth("/auth/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ avatar: finalAvatarUrl }),
      });
      if (res.ok) {
        const updated = await res.json();
        setUserProfile(updated);
        toast.success("Profile avatar updated successfully!");
        setShowProfileSettings(false);
        // Refresh collections to push user updates
        void fetchCollections();
      } else {
        toast.error("Failed to update avatar.");
      }
    } catch (err) {
      console.error("Save profile error:", err);
      toast.error("Error cropping profile picture.");
    }
  };

  const handleCopyCollectionCode = async (connectionCode: string) => {
    try {
      await navigator.clipboard.writeText(connectionCode);
      toast.success("Collection ID copied.");
    } catch {
      toast.error("Failed to copy collection ID.");
    }
  };

  const handleRespondToInvitation = async (collectionId: string, action: "approve" | "deny") => {
    setMutatingId(collectionId);
    try {
      const res = await fetchWithAuth(`/collections/${collectionId}/invitations/respond`, {
        method: "POST",
        body: JSON.stringify({ action }),
      });
      if (!res.ok) throw new Error("Failed to respond to invitation.");
      toast.success(action === "approve" ? "Collection bridge connected." : "Invitation denied.");
      await fetchCollections();
      if (action === "approve") {
        handleSelectCollection(collectionId);
      }
    } catch (error) {
      console.error(error);
      toast.error("Failed to update invitation.");
    } finally {
      setMutatingId(null);
    }
  };

  const handleLeaveOrDelete = async (collection: Collection) => {
    const isOwner = collection.requester_access_role === "owner";
    const confirmed = window.confirm(
      isOwner ? `Delete "${collection.name}" for all members?` : `Leave "${collection.name}"?`,
    );
    if (!confirmed) {
      return;
    }
    setMutatingId(collection.id);
    try {
      const res = isOwner
        ? await fetchWithAuth(`/collections/${collection.id}`, {
            method: "DELETE",
          })
        : await fetchWithAuth(`/collections/${collection.id}/permissions`, {
            method: "DELETE",
            body: JSON.stringify({ user_ids: [] }),
          });
      if (res.ok) {
        toast.success(isOwner ? "Collection deleted." : "You left the collection.");
        if (activeCollectionId === collection.id) {
          setActiveCollectionId(null);
          window.history.pushState(null, "", pathname);
        }
        await fetchCollections();
      }
    } catch (error) {
      console.error(error);
      toast.error(isOwner ? "Failed to delete collection." : "Failed to leave collection.");
    } finally {
      setMutatingId(null);
    }
  };

  const handleSelectCollection = (colId: string) => {
    setActiveCollectionId(colId);
    const newPath = `${pathname}?id=${colId}`;
    window.history.pushState({ path: newPath }, "", newPath);
  };

  const handleBackToStandby = () => {
    setActiveCollectionId(null);
    window.history.pushState(null, "", pathname);
  };

  const filteredCollections = collections.filter((c) =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const activeCollection = collections.find((c) => c.id === activeCollectionId);

  return (
    <div className="w-full h-full flex flex-col min-h-0 space-y-4 text-foreground">

      {/* A. Global Top Header Bar (Outside the right-side chat container) */}
      <div className="flex flex-row items-center justify-between gap-3 p-4 rounded-[1.6rem] border border-foreground/10 dark:border-white/5 bg-background/50 backdrop-blur-lg shadow-none relative overflow-visible shrink-0">

        {/* Left Side: Info context & Navigation */}
        <div className="flex items-center gap-3 min-w-0">

          {/* Back/Menu Navigation Button Container */}
          <div className="h-10 w-10 flex-shrink-0 flex items-center justify-center relative">
            <AnimatePresence mode="wait">
              {activeCollection ? (
                <motion.button
                  key="back-btn"
                  initial={{ opacity: 0, scale: 0.9, rotate: -12 }}
                  animate={{ opacity: 1, scale: 1, rotate: 0 }}
                  exit={{ opacity: 0, scale: 0.9, rotate: -12 }}
                  transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                  onClick={handleBackToStandby}
                  className="ui-tooltip ui-tooltip-start h-10 w-10 rounded-xl border border-foreground/10 bg-foreground/5 text-foreground hover:bg-foreground/10 hover:text-foreground flex items-center justify-center transition-all cursor-pointer hover:scale-[1.02] active:scale-95 shrink-0"
                  data-tooltip="Back to Workspace Home"
                >
                  <ChevronLeft size={18} />
                </motion.button>
              ) : (
                <motion.button
                  key="menu-btn"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                  onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
                  className="ui-tooltip ui-tooltip-start h-10 w-10 rounded-xl border border-foreground/10 bg-foreground/5 text-foreground hover:bg-foreground/10 hover:text-foreground flex items-center justify-center transition-all cursor-pointer hover:scale-[1.02] active:scale-95 shrink-0"
                  data-tooltip={isSidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
                >
                  {isSidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
                </motion.button>
              )}
            </AnimatePresence>
          </div>

          {/* AverQel Folder Logo Box or Partner Avatar */}
          <div className="h-11 w-11 rounded-2xl overflow-hidden flex items-center justify-center flex-shrink-0 border border-amber-500/20 bg-amber-500/10">
            {activeCollection?.other_member_avatar ? (
              <img src={activeCollection.other_member_avatar} alt="Partner" className="h-full w-full object-cover" />
            ) : (
              <div className="text-amber-500 flex items-center justify-center h-full w-full">
                <FolderKanban size={17} />
              </div>
            )}
          </div>

          <div className="min-w-0 h-10 flex flex-col justify-center">
            <AnimatePresence mode="wait">
              {activeCollection ? (
                <motion.div
                  key={`title-${activeCollection.id}`}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-amber-500 font-bold uppercase tracking-widest leading-none">Active Bridge</span>
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  </div>
                  <h1 className="text-sm sm:text-lg font-black tracking-tight mt-0.5 truncate max-w-[8rem] sm:max-w-none text-foreground leading-tight">
                    {activeCollection.name}
                  </h1>
                </motion.div>
              ) : (
                <motion.div
                  key="title-standby"
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                >
                  <span className="text-[10px] text-slate-550 dark:text-slate-500 font-bold uppercase tracking-widest leading-none">AverQel Connect</span>
                  <h1 className="text-sm sm:text-lg font-black tracking-tight mt-0.5 text-foreground leading-tight">Document Bridge Control</h1>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Right Side: Shared Documents & Bridge Members buttons placed outside the chat area */}
        <div className="flex items-center gap-2 flex-shrink-0 justify-end min-h-[40px]">
          {/* Permanent Profile Settings Button */}
          <button
            onClick={() => setShowProfileSettings(true)}
            className="ui-tooltip h-10 w-10 border border-foreground/10 bg-foreground/5 hover:bg-foreground/10 rounded-xl flex items-center justify-center active:scale-95 transition-all cursor-pointer shrink-0 overflow-hidden"
            data-tooltip="Profile Settings"
          >
            {userProfile?.avatar ? (
              <img src={userProfile.avatar} alt="Avatar" className="h-full w-full object-cover" />
            ) : (
              <img src={DEFAULT_AVATAR_SVG} alt="Avatar" className="h-8 w-8 object-cover" />
            )}
          </button>

          <AnimatePresence mode="wait">
            {activeCollection ? (
              <motion.div
                key={`actions-${activeCollection.id}`}
                initial={{ opacity: 0, scale: 0.96, x: 10 }}
                animate={{ opacity: 1, scale: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.96, x: 10 }}
                transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                className="flex items-center gap-2"
              >
                {/* New Connection Button placed on top bar */}
                <button
                  onClick={() => setShowCreate(true)}
                  aria-label="+ New Collection"
                  className="ui-tooltip h-10 w-10 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl flex items-center justify-center active:scale-95 transition-all cursor-pointer border border-emerald-500/20 shrink-0"
                  data-tooltip="Start New Connection"
                >
                  <Plus size={18} />
                </button>

                {/* Document Drawer Toggle Button */}
                <button
                  onClick={() => setActiveDrawer(activeDrawer === "documents" ? null : "documents")}
                  className={`ui-tooltip ui-tooltip-end flex items-center gap-2 p-2.5 sm:px-4 sm:py-2.5 rounded-xl border text-xs font-bold uppercase tracking-widest cursor-pointer transition-all hover:scale-[1.02] active:scale-95 ${
                    activeDrawer === "documents"
                      ? "bg-amber-500 border-amber-500 text-slate-950 font-black"
                      : "border-foreground/10 bg-foreground/5 text-foreground hover:bg-foreground/10 hover:text-foreground"
                  }`}
                  data-tooltip="Shared Documents"
                >
                  <FileStack size={14} />
                  <span className="hidden sm:inline">Shared Documents</span>
                </button>

                {/* Members Drawer Toggle Button */}
                <button
                  onClick={() => setActiveDrawer(activeDrawer === "members" ? null : "members")}
                  className={`ui-tooltip ui-tooltip-end flex items-center gap-2 p-2.5 sm:px-4 sm:py-2.5 rounded-xl border text-xs font-bold uppercase tracking-widest cursor-pointer transition-all hover:scale-[1.02] active:scale-95 ${
                    activeDrawer === "members"
                      ? "bg-amber-500 border-amber-500 text-slate-950 font-black"
                      : "border-foreground/10 bg-foreground/5 text-foreground hover:bg-foreground/10 hover:text-foreground"
                  }`}
                  data-tooltip="Bridge Members"
                >
                  <Users size={14} />
                  <span className="hidden sm:inline">Bridge Members</span>
                </button>

                {/* Trash/Delete Button placed globally */}
                <button
                  onClick={() => void handleLeaveOrDelete(activeCollection)}
                  disabled={mutatingId === activeCollection.id}
                  aria-label={activeCollection.requester_access_role === "owner" ? "Delete Collection" : "Leave Collection"}
                  className="ui-tooltip ui-tooltip-end h-10 w-10 rounded-xl border border-red-500/20 bg-red-500/5 hover:bg-red-500/10 text-red-500 flex items-center justify-center transition-all hover:scale-[1.02] active:scale-95 cursor-pointer flex-shrink-0"
                  data-tooltip={activeCollection.requester_access_role === "owner" ? "Delete Collection" : "Leave Collection"}
                >
                  <Trash2 size={15} />
                </button>
              </motion.div>
            ) : (
              <motion.button
                key="action-new"
                initial={{ opacity: 0, scale: 0.96, x: -10 }}
                animate={{ opacity: 1, scale: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.96, x: -10 }}
                transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                onClick={() => setShowCreate(true)}
                aria-label="+ New Collection"
                className="ui-tooltip ui-tooltip-end h-10 w-10 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl flex items-center justify-center active:scale-95 transition-all cursor-pointer border border-emerald-500/20 shrink-0"
                data-tooltip="Start New Connection"
              >
                <Plus size={18} />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* B. App Shell Workspace Container */}
      <div className="flex flex-1 min-h-0 w-full overflow-hidden rounded-[1.8rem] border border-foreground/10 dark:border-white/5 bg-background/30 backdrop-blur-md shadow-none">

        {/* Sidebar (Left Column) */}
        <div
          className={`h-full flex-shrink-0 flex-col border-r border-foreground/10 dark:border-white/5 bg-foreground/[0.015] dark:bg-slate-950/20 transition-all duration-300 ${
            isSidebarCollapsed ? "w-0 overflow-hidden border-r-0" : "w-full md:w-[24rem]"
          } ${activeCollectionId ? "hidden md:flex" : "flex"}`}
        >
          {/* Sidebar Top: User search and connections */}
          <div className="p-4 border-b border-foreground/10 dark:border-white/5 flex flex-col gap-3.5 bg-foreground/[0.01]">

            {/* My Connection ID Area */}
            {myCollectionCode && (
              <div className="bg-foreground/[0.02] border border-foreground/10 dark:border-white/5 flex items-center justify-between rounded-xl px-3 py-2.5 text-[10px]">
                <div className="flex flex-col">
                  <span className="text-slate-500 font-bold uppercase tracking-wider">My Code</span>
                  <span className="font-mono text-foreground font-black tracking-widest mt-0.5">{myCollectionCode}</span>
                </div>
                <button
                  onClick={() => void handleCopyCollectionCode(myCollectionCode)}
                  className="bg-white/[0.04] hover:bg-white/[0.08] text-foreground px-2 py-1.5 rounded-lg font-bold flex items-center gap-1.5 transition border border-foreground/10 dark:border-white/5"
                >
                  <Copy size={10} /> Copy
                </button>
              </div>
            )}

            {/* Search Input bar */}
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search chats or documents..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-background/80 border border-foreground/10 dark:border-white/5 rounded-xl pl-9 pr-4 py-2 text-xs text-foreground placeholder-slate-500 outline-none focus:border-amber-500/30 transition"
              />
            </div>
          </div>

          {/* Sidebar Chat List Tiles (Scrollable) */}
          <div className="flex-1 overflow-y-auto divide-y divide-foreground/5 dark:divide-white/5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden p-2 space-y-1.5">

            {/* Inline Pending Invitations Segment */}
            {invitations.length > 0 && (
              <div className="bg-amber-500/5 rounded-xl p-3 space-y-2 border border-amber-500/10">
                <span className="text-[9px] text-amber-400 font-bold uppercase tracking-widest block">Pending invites</span>
                {invitations.map((inv) => (
                  <div key={inv.id} className="bg-background/80 p-2.5 rounded-lg border border-foreground/10 dark:border-white/5 flex items-center justify-between gap-3 text-xs">
                    <div className="min-w-0">
                      <p className="font-bold text-foreground truncate">{inv.name}</p>
                      <p className="text-[9px] text-slate-500 truncate mt-0.5">From: {inv.inviter_user_email || "User"}</p>
                    </div>
                    <div className="flex gap-1.5 flex-shrink-0">
                      <button
                        onClick={() => void handleRespondToInvitation(inv.id, "deny")}
                        className="h-6 w-6 rounded-md bg-red-500/10 text-red-400 hover:bg-red-500/20 flex items-center justify-center transition border border-red-500/20"
                      >
                        <X size={12} />
                      </button>
                      <button
                        onClick={() => void handleRespondToInvitation(inv.id, "approve")}
                        className="h-6 w-6 rounded-md bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 flex items-center justify-center transition border border-emerald-500/20"
                      >
                        <Check size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Normal Chats styled as premium obsidian glass cards */}
            {loading ? (
              <div className="p-4 text-xs text-slate-500 animate-pulse text-center">Loading tiles...</div>
            ) : filteredCollections.length === 0 ? (
              <div className="p-8 text-xs text-slate-500 text-center">No active bridges found.</div>
            ) : (
              filteredCollections.map((col) => {
                const isSelected = col.id === activeCollectionId;
                const initials = col.name.substring(0, 2).toUpperCase();

                return (
                  <div
                    key={col.id}
                    onClick={() => handleSelectCollection(col.id)}
                    className={`p-3.5 flex items-center justify-between gap-3 cursor-pointer rounded-xl transition-all border ${
                      isSelected
                        ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                        : "bg-foreground/[0.01] hover:bg-foreground/[0.03] dark:bg-white/[0.01] dark:hover:bg-white/[0.03] border-foreground/[0.04] dark:border-white/5 hover:border-foreground/10 dark:hover:border-white/10"
                    }`}
                  >
                    {/* Avatar Tile Icon */}
                    <div className="h-9 w-9 rounded-xl overflow-hidden shrink-0 flex items-center justify-center border border-foreground/10 dark:border-white/5">
                      {col.other_member_avatar ? (
                        <img src={col.other_member_avatar} alt="Avatar" className="h-full w-full object-cover" />
                      ) : (
                        <div className={`h-full w-full flex items-center justify-center text-xs font-black tracking-widest ${
                          isSelected ? "bg-amber-500 text-slate-950" : "bg-foreground/[0.04] dark:bg-slate-900 text-slate-400"
                        }`}>
                          {initials}
                        </div>
                      )}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className={`font-bold text-xs truncate ${isSelected ? "text-amber-600 dark:text-amber-400" : "text-foreground"}`}>{col.name}</span>
                        {col.requester_access_role === "pending" && (
                          <span className="bg-amber-500/15 text-amber-400 border border-amber-500/25 text-[8px] font-bold uppercase rounded px-1">
                            Pending
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-500 truncate mt-1">
                        {col.description || "No description provided."}
                      </p>
                      <Link
                        href={`${collectionsBasePath}/${col.id}?section=documents`}
                        onClick={(event) => event.stopPropagation()}
                        className="mt-1 inline-flex text-[9px] font-black uppercase tracking-wider text-amber-500 hover:text-amber-400"
                      >
                        Manage Collection
                      </Link>
                    </div>

                    <div className="flex flex-col items-end shrink-0 text-[10px] text-slate-500 gap-1.5">
                      <span>{new Date(col.created_at).toLocaleDateString([], { month: "short", day: "numeric" })}</span>
                      <div className="flex items-center gap-1.5">
                        {unreadCounts[col.id] > 0 && (
                          <span className="bg-emerald-600 text-white font-extrabold text-[8px] h-4.5 min-w-[1.125rem] px-1 rounded-full flex items-center justify-center animate-pulse">
                            {unreadCounts[col.id]}
                          </span>
                        )}
                        <div className="flex items-center gap-1 font-bold">
                          <Users size={11} className="text-slate-600" />
                          <span>{col.member_count}</span>
                        </div>
                      </div>
                      <button
                        type="button"
                        aria-label={col.requester_access_role === "owner" ? "Delete Collection" : "Leave Collection"}
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleLeaveOrDelete(col);
                        }}
                        className="text-[9px] font-black uppercase tracking-wider text-red-400 hover:text-red-300"
                      >
                        {col.requester_access_role === "owner" ? "Delete" : "Leave"}
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Active Chat Pane (Right Column) */}
        <div className={`flex-1 h-full relative overflow-hidden bg-foreground/[0.005] ${
          !activeCollectionId
            ? isSidebarCollapsed
              ? "flex"
              : "hidden md:flex"
            : "flex"
        }`}>
          <AnimatePresence mode="wait">
            {activeCollectionId ? (
              <motion.div
                key={`chat-${activeCollectionId}`}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                className="w-full h-full flex flex-col min-h-0 bg-transparent relative overflow-hidden"
              >
                <CollectionDetailClient
                  key={activeCollectionId}
                  collectionIdProp={activeCollectionId}
                  onCollectionDeleted={() => {
                    setActiveCollectionId(null);
                    router.push(collectionsBasePath);
                  }}
                  activeDrawer={activeDrawer}
                  setActiveDrawer={setActiveDrawer}
                />
              </motion.div>
            ) : (
              /* Standby Screen (Premium Watermark Landing UX) */
              <motion.div
                key="standby"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                className="flex-1 flex flex-col items-center justify-center text-center p-8 bg-slate-950/[0.01] relative overflow-hidden select-none"
              >
                {/* Giant conversation icon watermark backdrop */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-amber-500/[0.015] pointer-events-none select-none">
                  <MessageSquare size={380} className="stroke-[1px]" />
                </div>
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(245,158,11,0.015),transparent_70%)] pointer-events-none" />

                <div className="relative z-10 flex flex-col items-center">
                  <div className="h-16 w-16 bg-amber-500/[0.03] text-amber-500/60 border border-amber-500/10 rounded-[1.4rem] flex items-center justify-center mb-5">
                    <MessageSquare size={26} />
                  </div>

                  <h3 className="text-sm font-black tracking-widest text-foreground/40 uppercase">AverQel Connect</h3>

                  <p className="text-[11px] text-slate-500 mt-2.5 max-w-xs leading-relaxed">
                    Select a bridge channel tile on the left to view shared documents, manage members, and chat in isolated end-to-end synchronized environments.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

      </div>

      {/* New Connection Modal Flow */}
      {showCreate && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4 backdrop-blur-md">
          <div className="w-full max-w-md rounded-[1.8rem] border border-white/5 p-6 space-y-4 shadow-none bg-slate-900 relative">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-amber-500 to-emerald-500" />
            <div className="flex items-center justify-between border-b border-white/5 pb-3">
              <h2 className="text-xs font-black tracking-widest uppercase text-slate-300">New Connection Bridge</h2>
              <button onClick={() => setShowCreate(false)} className="text-slate-500 hover:text-white transition">✕</button>
            </div>

            {/* Modal Tabs */}
            <div className="flex bg-slate-950/60 p-1 rounded-xl border border-slate-800">
              <button
                onClick={() => setCreateMode("direct")}
                className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider rounded-lg transition ${
                  createMode === "direct" ? "bg-amber-500 text-slate-950 font-black" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                1:1 Connection
              </button>
              <button
                onClick={() => setCreateMode("group")}
                className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider rounded-lg transition ${
                  createMode === "group" ? "bg-amber-500 text-slate-950 font-black" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Group Chat
              </button>
            </div>

            {createMode === "direct" ? (
              <div className="space-y-4">
                <p className="text-[11px] text-slate-500 leading-normal">
                  Enter another user&apos;s permanent **Collection ID** below to establish a direct 1:1 chat bridge. Once they approve, the connection becomes active.
                </p>
                 <div className="space-y-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">Connection Name (Optional)</label>
                  <input
                    type="text"
                    value={directName}
                    onChange={(e) => setDirectName(e.target.value)}
                    placeholder="E.g., Chat with John (defaults to Direct Chat)"
                    className="w-full bg-slate-950 border border-white/5 rounded-xl px-4 py-3 text-xs text-white outline-none focus:border-amber-500/30 transition"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">Target Connection ID</label>
                  <input
                    type="text"
                    value={directCode}
                    onChange={(e) => setDirectCode(e.target.value.toUpperCase())}
                    placeholder="E.g., Z7X9Y2W1"
                    className="w-full bg-slate-950 border border-white/5 rounded-xl px-4 py-3 text-xs text-white outline-none focus:border-amber-500/30 transition"
                  />
                </div>
                <div className="flex justify-end gap-2.5 pt-2">
                  <button
                    onClick={() => setShowCreate(false)}
                    className="bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 px-4 py-2.5 rounded-xl text-xs font-bold transition border border-white/5"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleCreateDirectChat}
                    className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2.5 rounded-xl text-xs font-bold transition active:scale-95 border border-emerald-500/20"
                  >
                    Send Request
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-[11px] text-slate-500 leading-normal">
                  Create a shared group bridge room. Input the Group Name, details, and multiple Connection IDs to invite them together.
                </p>
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">Group Name</label>
                    <input
                      type="text"
                      value={groupName}
                      onChange={(e) => setGroupName(e.target.value)}
                      placeholder="Collection name (e.g., Dev Team)"
                      className="w-full bg-slate-950 border border-white/5 rounded-xl px-4 py-3 text-xs text-white outline-none focus:border-amber-500/30 transition"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">Description (Optional)</label>
                    <input
                      type="text"
                      value={groupDesc}
                      onChange={(e) => setGroupDesc(e.target.value)}
                      placeholder="Description (e.g., Shared workspace for development docs)"
                      className="w-full bg-slate-950 border border-white/5 rounded-xl px-4 py-3 text-xs text-white outline-none focus:border-amber-500/30 transition"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">Invite Connection IDs (Comma Separated)</label>
                    <textarea
                      value={groupCodes}
                      onChange={(e) => setGroupCodes(e.target.value)}
                      placeholder="Z7X9Y2W1, X8Y9Z0W1"
                      className="w-full bg-slate-950 border border-white/5 rounded-xl px-4 py-3 text-xs text-white outline-none focus:border-amber-500/30 transition h-20 resize-none"
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-2.5 pt-2">
                  <button
                    onClick={() => setShowCreate(false)}
                    className="bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 px-4 py-2.5 rounded-xl text-xs font-bold transition border border-white/5"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleCreateGroupChat}
                    className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2.5 rounded-xl text-xs font-bold transition active:scale-95 border border-emerald-500/20"
                  >
                    Create Group
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Profile Settings Modal */}
      {showProfileSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-slate-900 border border-white/10 rounded-2xl p-6 shadow-2xl space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-extrabold uppercase tracking-widest text-slate-100">Profile Settings</h3>
              <button
                onClick={() => setShowProfileSettings(false)}
                className="text-slate-400 hover:text-white transition cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-4">
              {/* Account Details */}
              <div className="p-3 bg-white/[0.02] border border-white/5 rounded-xl space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-500 font-bold uppercase tracking-wider text-[9px]">Email Address</span>
                  <span className="text-slate-200 font-semibold">{userProfile?.email}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-bold uppercase tracking-wider text-[9px]">My Connection Code</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-amber-500 font-mono font-bold tracking-wider">{userProfile?.collection_code}</span>
                    <button
                      onClick={() => {
                        if (userProfile?.collection_code) {
                          navigator.clipboard.writeText(userProfile.collection_code);
                          toast.success("Copied connection code!");
                        }
                      }}
                      className="text-slate-400 hover:text-white transition p-0.5"
                    >
                      <Copy size={11} />
                    </button>
                  </div>
                </div>
              </div>

              {/* Avatar Live Preview */}
              <div className="flex flex-col items-center justify-center space-y-3 pt-2">
                <div className="relative w-28 h-28 rounded-full overflow-hidden border-2 border-amber-500/50 bg-slate-950 flex items-center justify-center shadow-lg">
                  <img
                    src={previewAvatar || DEFAULT_AVATAR_SVG}
                    alt="Preview"
                    style={{ transform: `scale(${zoom})` }}
                    className="w-full h-full object-cover transition-transform duration-100"
                  />
                </div>

                {/* Crop/Zoom Slider */}
                {previewAvatar && !previewAvatar.includes("svg+xml") && (
                  <div className="w-full max-w-[200px] space-y-1.5">
                    <div className="flex justify-between text-[9px] text-slate-500 font-bold uppercase tracking-wider">
                      <span>Adjust Size</span>
                      <span className="text-amber-500">{Math.round(zoom * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min="1"
                      max="3"
                      step="0.05"
                      value={zoom}
                      onChange={(e) => setZoom(parseFloat(e.target.value))}
                      className="w-full h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
                    />
                  </div>
                )}
              </div>

              {/* Preset Avatar Picker */}
              <div className="space-y-2">
                <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest block">Choose Preset Avatar</label>
                <div className="flex gap-3 justify-center flex-wrap max-w-[280px] mx-auto">
                  {[
                    DEFAULT_AVATAR_SVG,
                    `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="bg1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%231e1b4b"/><stop offset="100%" stop-color="%23311042"/></linearGradient><linearGradient id="vis" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="%23f59e0b"/><stop offset="100%" stop-color="%23ea580c"/></linearGradient></defs><circle cx="50" cy="50" r="50" fill="url(%23bg1)"/><circle cx="50" cy="45" r="22" fill="%23e2e8f0"/><path d="M36 45c0-10 6-18 14-18s14 8 14 18H36z" fill="%23cbd5e1"/><ellipse cx="50" cy="43" rx="16" ry="11" fill="url(%23vis)"/><ellipse cx="46" cy="38" rx="4" ry="2" fill="%23fff" opacity="0.4"/><path d="M28 72c0-8 8-14 22-14s22 6 22 14v10H28V72z" fill="%23e2e8f0"/><rect x="42" y="58" width="16" height="6" rx="2" fill="%2394a3b8"/></svg>`,
                    `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="bg2" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%2306b6d4"/><stop offset="100%" stop-color="%230891b2"/></linearGradient></defs><circle cx="50" cy="50" r="50" fill="url(%23bg2)"/><rect x="30" y="32" width="40" height="30" rx="6" fill="%231e293b"/><rect x="34" y="36" width="32" height="22" rx="4" fill="%230f172a"/><circle cx="42" cy="47" r="4" fill="%2322c55e"/><circle cx="58" cy="47" r="4" fill="%2322c55e"/><path d="M46 54h8" stroke="%2322c55e" stroke-width="2" stroke-linecap="round"/><rect x="48" y="24" width="4" height="8" fill="%23475569"/><circle cx="50" cy="22" r="3" fill="%23ef4444"/><path d="M25 75c0-10 10-15 25-15s25 5 25 15v8H25v-8z" fill="%23334155"/><rect x="44" y="60" width="12" height="6" fill="%23475569"/></svg>`,
                    `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="bg3" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%23ea580c"/><stop offset="100%" stop-color="%23facc15"/></linearGradient></defs><circle cx="50" cy="50" r="50" fill="url(%23bg3)"/><path d="M50 24L34 44h32L50 24z" fill="%231e1b4b"/><path d="M34 44l16 32 16-32H34z" fill="%232e1065"/><path d="M34 44l-6 10h12l-6-10z" fill="%234438ca"/><path d="M66 44l6 10H60l6-10z" fill="%234438ca"/><path d="M42 38l8 12 8-12H42z" fill="%23facc15"/><circle cx="45" cy="46" r="2" fill="%23fff"/><circle cx="55" cy="46" r="2" fill="%23fff"/></svg>`,
                    `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="bg4" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%23b91c1c"/><stop offset="100%" stop-color="%23f97316"/></linearGradient></defs><circle cx="50" cy="50" r="50" fill="url(%23bg4)"/><path d="M50 20L32 45h36L50 20z" fill="%23fef08a"/><path d="M50 80L32 45h36L50 80z" fill="%23ca8a04"/><path d="M22 45c10-5 20-5 28 0-8 5-18 5-28 0z" fill="%23facc15"/><path d="M78 45c-10-5-20-5-28 0 8 5 18 5 28 0z" fill="%23facc15"/><path d="M46 36l4 9 4-9-4 2-4-2z" fill="%231e293b"/></svg>`,
                    `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="bg5" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%234c1d95"/><stop offset="100%" stop-color="%232563eb"/></linearGradient></defs><circle cx="50" cy="50" r="50" fill="url(%23bg5)"/><path d="M50 22l24 10v22c0 15-10 27-24 32-14-5-24-17-24-32V32l24-10z" fill="%2310b981"/><path d="M50 28l18 8v16c0 11-8 21-18 25-10-4-18-14-18-25V36l18-8z" fill="%23047857"/><path d="M45 42l4 4 8-8" stroke="%23fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`,
                    `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="bg6" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="%23ec4899"/><stop offset="100%" stop-color="%238b5cf6"/></linearGradient></defs><circle cx="50" cy="50" r="50" fill="url(%23bg6)"/><circle cx="50" cy="46" r="24" fill="%23f59e0b"/><path d="M26 46h48v2H26zM26 50h48v2H26zM26 55h48v2H26zM26 61h48v2H26zM26 68h48v2H26z" fill="url(%23bg6)"/><path d="M15 75l10-15h50l10 15H15z" fill="%231e1b4b"/><path d="M20 75L35 60M35 75L45 60M50 75L50 60M65 75L55 60M80 75L65 60" stroke="%2306b6d4" stroke-width="1.5"/></svg>`
                  ].map((preset, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setPreviewAvatar(preset);
                        setZoom(1);
                      }}
                      className={`w-10 h-10 rounded-full overflow-hidden border-2 transition active:scale-95 ${
                        previewAvatar === preset ? "border-amber-500 scale-105" : "border-white/5 hover:border-white/20"
                      }`}
                    >
                      <img src={preset} alt="Preset avatar" className="w-full h-full object-cover" />
                    </button>
                  ))}
                </div>
              </div>

              {/* Upload Custom DM Photo */}
              <div className="space-y-2">
                <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest block">Upload Personal DM Photo</label>
                <div className="flex items-center justify-center w-full">
                  <label className="flex flex-col items-center justify-center w-full h-20 border border-dashed border-white/10 rounded-xl cursor-pointer hover:bg-white/[0.02] hover:border-white/20 transition">
                    <div className="flex flex-col items-center justify-center pt-3 pb-3">
                      <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Choose File</p>
                      <p className="text-[9px] text-slate-500 mt-1">PNG, JPG or WEBP (Max 2MB)</p>
                    </div>
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleFileChange}
                      className="hidden"
                    />
                  </label>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2.5 pt-2">
              <button
                onClick={() => setShowProfileSettings(false)}
                className="bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 px-4 py-2.5 rounded-xl text-xs font-bold transition border border-white/5 cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveProfile}
                className="bg-amber-500 hover:bg-amber-400 text-slate-950 px-4 py-2.5 rounded-xl text-xs font-black transition active:scale-95 cursor-pointer"
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
