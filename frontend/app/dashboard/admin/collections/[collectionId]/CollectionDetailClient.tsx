"use client";

/* This legacy encrypted collection surface consumes versioned API payloads;
 * boundary validation is centralized in the API client. */
/* eslint-disable @typescript-eslint/no-explicit-any */
/* Encrypted media and user-selected blob URLs cannot safely use Next's remote image optimizer. */
/* eslint-disable @next/next/no-img-element */

import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import {
  FileStack,
  ShieldCheck,
  Users,
  Send,
  MessageSquare,
  X,
  Check,
  CheckCheck,
  Paperclip,
  File as FileIcon,
  Volume2,
  Lock,
  Play,
  Pause,
  Search,
} from "lucide-react";
import toast from "react-hot-toast";
const DEFAULT_AVATAR_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%23f59e0b"/><stop offset="100%" stop-color="%2310b981"/></linearGradient></defs><circle cx="50" cy="50" r="50" fill="url(%23g)"/><path d="M50 30a15 15 0 1 0 0 30 15 15 0 0 0 0-30zM50 67c-18 0-32 10-32 20v3h64v-3c0-10-14-20-32-20z" fill="%230f172a"/></svg>`;
import { fetchWithAuth } from "@/lib/api";
import { useAuth } from "@/app/context/AuthContext";
import {
  deriveKey,
  encryptMessage,
  decryptMessage,
  encryptFile,
  decryptFile,
  getSafetyNumber,
  encryptBackup,
  decryptBackup,
} from "@/lib/crypto";
import {
  initDb,
  saveLocalMessage,
  getLocalMessages,
  resetUnreadCount,
  purgeExpiredMessages,
  clearLocalMessages,
} from "@/lib/localDb";
import { AnimatePresence, motion } from "framer-motion";

interface Collection {
  id: string;
  name: string;
  description: string;
  requester_access_role?: "owner" | "member" | "pending" | null;
  member_count: number;
  other_member_email?: string | null;
  other_member_avatar?: string | null;
  connection_code?: string;
  expiry_days?: number;
  created_at: string;
  updated_at: string;
}

interface CollectionPermission {
  id: string;
  collection_id: string;
  user_id: string;
  user_email?: string | null;
  user_avatar?: string | null;
  role: string;
  created_at: string;
}

interface DocumentItem {
  document_id: string;
  filename: string;
  status: string;
  created_at: string;
}

interface DocumentListResponse {
  items: DocumentItem[];
}

function normalizeDocumentItems(payload: DocumentListResponse | DocumentItem[] | null | undefined) {
  if (Array.isArray(payload)) {
    return payload;
  }
  return Array.isArray(payload?.items) ? payload.items : [];
}

async function extractApiErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const data = (await res.json()) as {
      message?: string;
      detail?: string;
      details?: { errors?: Array<{ msg?: string }> };
    };
    const validationMessage = data.details?.errors?.[0]?.msg;
    return data.message || data.detail || validationMessage || fallback;
  } catch {
    return fallback;
  }
}

interface CollectionDetailClientProps {
  collectionIdProp?: string;
  onCollectionDeleted?: () => void;
  activeDrawer?: "documents" | "members" | null;
  setActiveDrawer?: (drawer: "documents" | "members" | null) => void;
}

export default function AdminCollectionDetailPage({
  collectionIdProp,
  onCollectionDeleted,
  activeDrawer: activeDrawerProp,
  setActiveDrawer: setActiveDrawerProp,
}: CollectionDetailClientProps = {}) {
  const { user } = useAuth();
  const params = useParams<{ collectionId: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  const collectionId = collectionIdProp || params.collectionId;
  const collectionsBasePath = pathname.startsWith("/dashboard/admin/collections")
    ? "/dashboard/admin/collections"
    : "/dashboard/collections";

  const [collection, setCollection] = useState<Collection | null>(null);
  const [collectionDocs, setCollectionDocs] = useState<DocumentItem[]>([]);
  const [allDocs, setAllDocs] = useState<DocumentItem[]>([]);
  const [permissions, setPermissions] = useState<CollectionPermission[]>([]);
  const [, setLoading] = useState(true);
  const [savingDocs, setSavingDocs] = useState(false);
  const [savingPermissions, setSavingPermissions] = useState(false);
  const [deletingCollection, setDeletingCollection] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [connectCode, setConnectCode] = useState("");

  // Drawer slider state: Fallback to local state if parent doesn't provide
  const [localDrawer, setLocalDrawer] = useState<"documents" | "members" | null>(() => {
    return searchParams.get("section") === "access" ? "members" : "documents";
  });
  const activeDrawer = activeDrawerProp !== undefined ? activeDrawerProp : localDrawer;
  const setActiveDrawer = setActiveDrawerProp || setLocalDrawer;

  // Real-time Chat States
  const [chats, setChats] = useState<any[]>([]);
  const [chatText, setChatText] = useState("");
  const [sendingChat, setSendingChat] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  // E2EE Key State
  const [cryptoKey, setCryptoKey] = useState<CryptoKey | null>(null);

  // Presence and Typing States
  const [membersPresence, setMembersPresence] = useState<
    Record<string, { is_online: boolean; last_seen: string | null }>
  >({});
  const [otherUserTyping, setOtherUserTyping] = useState<boolean>(false);
  const typingTimerRef = useRef<number | null>(null);
  const isTypingRef = useRef<boolean>(false);
  const lastTypingSentRef = useRef<number>(0);

  // New Premium UX States
  const [showShieldModal, setShowShieldModal] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [searchQueryText, setSearchQueryText] = useState("");
  const [showSearchBar, setShowSearchBar] = useState(false);
  const [wsStatus, setWsStatus] = useState<"connecting" | "online" | "offline">("connecting");
  const [safetyNumber, setSafetyNumber] = useState<string>("");
  const [isExportingBackup, setIsExportingBackup] = useState(false);
  const [isImportingBackup, setIsImportingBackup] = useState(false);
  const [activePreviewFile, setActivePreviewFile] = useState<{
    url: string;
    filename: string;
    mimeType: string;
  } | null>(null);
  const [previewTextContent, setPreviewTextContent] = useState<string | null>(null);
  const [loadingText, setLoadingText] = useState(false);
  const [activeMessageMenuId, setActiveMessageMenuId] = useState<string | null>(null);
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);

  // WebSockets Persistent connection Ref
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectDelayRef = useRef<number>(1000); // Start at 1s
  const processedMessageIdsRef = useRef<Set<string>>(new Set());

  const scrollChatToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // Load text file content dynamically for in-app code/text previews
  useEffect(() => {
    if (!activePreviewFile) {
      setPreviewTextContent(null);
      return;
    }
    const { url, filename, mimeType } = activePreviewFile;
    const isTextReadable =
      mimeType.startsWith("text/") ||
      mimeType === "application/json" ||
      mimeType === "application/javascript" ||
      mimeType === "application/typescript" ||
      mimeType === "text/javascript" ||
      filename.endsWith(".jsx") ||
      filename.endsWith(".tsx") ||
      filename.endsWith(".ts") ||
      filename.endsWith(".js") ||
      filename.endsWith(".py") ||
      filename.endsWith(".json") ||
      filename.endsWith(".css") ||
      filename.endsWith(".html") ||
      filename.endsWith(".log") ||
      filename.endsWith(".txt") ||
      filename.endsWith(".md");

    if (isTextReadable) {
      setLoadingText(true);
      fetch(url)
        .then((r) => r.text())
        .then((txt) => {
          setPreviewTextContent(txt);
          setLoadingText(false);
        })
        .catch(() => {
          setPreviewTextContent("Error loading preview content.");
          setLoadingText(false);
        });
    }
  }, [activePreviewFile]);

  // Derive E2EE symmetric key when collection loads
  useEffect(() => {
    if (collection?.id && collection?.connection_code) {
      deriveKey(collection.id, collection.connection_code)
        .then(async (key) => {
          setCryptoKey(key);
          console.log("Derived E2EE key for collection successfully.");
          const num = await getSafetyNumber(collection.id, collection.connection_code!);
          setSafetyNumber(num);
        })
        .catch((err) => console.error("Key derivation failed:", err));
    }
  }, [collection?.id, collection?.connection_code]);

  useEffect(() => {
    if (collectionId && cryptoKey) {
      const performPurgeAndSync = async () => {
        if (collection?.expiry_days && collection.expiry_days > 0) {
          await purgeExpiredMessages(collectionId, collection.expiry_days);
        }

        // 1. Instantly load offline messages from local IndexedDB
        const localMsgs = await getLocalMessages(collectionId);
        setChats(localMsgs);
        processedMessageIdsRef.current.clear();
        localMsgs.forEach((m) => processedMessageIdsRef.current.add(m.id));
        setTimeout(scrollChatToBottom, 100);

        // 2. Sync history from server using the derived key
        try {
          const chatsRes = await fetchWithAuth(`/collections/${collectionId}/chats`);
          if (chatsRes.ok) {
            const chatsData = await chatsRes.json();
            await resetUnreadCount(collectionId);

            const decryptedChats = [];
            for (const msg of chatsData) {
              processedMessageIdsRef.current.add(msg.id);
              let decryptedText = msg.message;
              try {
                // If it is E2EE, decrypt it
                decryptedText = await decryptMessage(msg.message, cryptoKey);
              } catch (decErr) {
                // Keep msg.message if already decrypted, or log warning
                console.warn("Failed to decrypt message:", decErr);
              }
              const decryptedMsg = { ...msg, message: decryptedText };
              await saveLocalMessage(decryptedMsg);
              decryptedChats.push(decryptedMsg);
            }
            setChats(decryptedChats);
            setTimeout(scrollChatToBottom, 50);
          }
        } catch (syncErr) {
          console.error("Failed to sync chat history from server:", syncErr);
        }
      };
      void performPurgeAndSync();
    }
  }, [collectionId, cryptoKey, collection?.expiry_days]);

  // Handle typing state input change trigger
  const handleTypingActivity = () => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
    const now = Date.now();
    if (!isTypingRef.current || now - lastTypingSentRef.current > 1500) {
      isTypingRef.current = true;
      lastTypingSentRef.current = now;
      socketRef.current.send(JSON.stringify({ action: "typing", is_typing: true }));
    }

    if (typingTimerRef.current) window.clearTimeout(typingTimerRef.current);
    typingTimerRef.current = window.setTimeout(() => {
      isTypingRef.current = false;
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ action: "typing", is_typing: false }));
      }
    }, 2000);
  };

  const connectWebSocket = useCallback(() => {
    if (!collectionId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const token = window.localStorage.getItem("averqel_token");
    const tenantId = window.localStorage.getItem("averqel_tenant_id");
    const params = new URLSearchParams();
    if (token) params.set("token", token);
    if (tenantId) params.set("tenant_id", tenantId);
    const wsUrl = `${protocol}//${host}/api/v1/collections/${collectionId}/ws?${params.toString()}`;

    console.log(`Connecting to Collection WebSocket: ${wsUrl}`);
    setWsStatus("connecting");
    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      console.log("WebSocket connected successfully to collection room");
      setWsStatus("online");
      reconnectDelayRef.current = 1000;
      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      socket.send(JSON.stringify({ action: "read" }));
    };

    socket.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);
        // Normalize: backend sends {type, data}, frontend expects {type, payload}
        if (!data.payload && data.data) data.payload = data.data;
        console.log("WebSocket message received:", data);

        if (data.type === "new_message" && data.payload) {
          const msg = data.payload;

          if (processedMessageIdsRef.current.has(msg.id)) return;
          processedMessageIdsRef.current.add(msg.id);

          let decryptedText = msg.message;
          if (cryptoKey) {
            decryptedText = await decryptMessage(msg.message, cryptoKey);
          }

          const decryptedMsg = {
            ...msg,
            message: decryptedText,
          };

          await saveLocalMessage(decryptedMsg);

          setChats((current) => {
            if (current.some((m) => m.id === msg.id)) return current;
            return [...current, decryptedMsg];
          });
          setTimeout(scrollChatToBottom, 50);

          if (msg.user_id !== user?.id) {
            socket.send(JSON.stringify({ action: "delivered", message_id: msg.id }));
            socket.send(JSON.stringify({ action: "read" }));
          }
        } else if (data.type === "message_delivered") {
          const { message_id, status } = data.payload;
          setChats((current) =>
            current.map((m) => {
              if (m.id === message_id) {
                if (m.status === "read") return m; // Prevent E2EE downgrade race condition
                const updated = { ...m, status };
                saveLocalMessage(updated).catch(console.error);
                return updated;
              }
              return m;
            }),
          );
        } else if (data.type === "messages_read") {
          const { reader_id, status } = data.payload;
          if (reader_id !== user?.id) {
            setChats((current) =>
              current.map((m) => {
                if (m.user_id === user?.id && m.status !== "read") {
                  const updated = { ...m, status };
                  saveLocalMessage(updated).catch(console.error);
                  return updated;
                }
                return m;
              }),
            );
          }
        } else if (data.type === "message_reacted") {
          const { message_id, reactions } = data.payload;
          setChats((current) =>
            current.map((m) => {
              if (m.id === message_id) {
                const updated = { ...m, reactions };
                saveLocalMessage(updated).catch(console.error);
                return updated;
              }
              return m;
            }),
          );
        } else if (data.type === "user_typing") {
          const { user_id, is_typing } = data.payload;
          if (user_id !== user?.id) {
            setOtherUserTyping(is_typing);
          }
        } else if (data.type === "presence_change") {
          const { user_id, is_online, last_seen } = data.payload;
          setMembersPresence((prev) => ({
            ...prev,
            [user_id]: { is_online, last_seen },
          }));
        } else if (data.type === "document_sync") {
          void loadCollectionData(false);
        } else if (data.type === "expiry_updated") {
          const { expiry_days } = data.payload;
          setCollection((prev) => {
            if (!prev) return prev;
            return { ...prev, expiry_days };
          });
          if (expiry_days > 0 && collectionId) {
            purgeExpiredMessages(collectionId, expiry_days).then(() => {
              getLocalMessages(collectionId).then((msgs) => {
                setChats(msgs);
                processedMessageIdsRef.current.clear();
                msgs.forEach((m) => processedMessageIdsRef.current.add(m.id));
              });
            });
          }
        } else if (data.type === "chat_cleared") {
          setChats([]);
          processedMessageIdsRef.current.clear();
          if (collectionId) {
            clearLocalMessages(collectionId).catch(console.error);
          }
          toast.success("Chat history cleared by admin.");
        } else if (data.type === "message_deleted") {
          const { message_id, message } = data.payload;
          setChats((current) =>
            current.map((m) =>
              m.id === message_id
                ? {
                    ...m,
                    message: message || "This message was deleted",
                    is_media: false,
                    media_mime_type: null,
                    reactions: "{}",
                  }
                : m,
            ),
          );
          // Update IndexedDB locally
          if (collectionId) {
            initDb()
              .then((db) => {
                const tx = db.transaction("chats", "readwrite");
                const store = tx.objectStore("chats");
                const request = store.get(message_id);
                request.onsuccess = () => {
                  const existing = request.result;
                  if (existing) {
                    existing.message = message || "This message was deleted";
                    existing.is_media = false;
                    existing.media_mime_type = null;
                    existing.reactions = "{}";
                    store.put(existing);
                  }
                };
              })
              .catch(console.error);
          }
        }
      } catch (err) {
        console.error("Failed to parse WebSocket event frame:", err);
      }
    };

    socket.onclose = (event) => {
      console.warn(
        `WebSocket closed. Code=${event.code}, Reason=${event.reason}. Scheduling reconnect...`,
      );
      setWsStatus("offline");
      socketRef.current = null;
      if (event.code === 4004) {
        onCollectionDeleted?.();
        return;
      }
      if (reconnectTimeoutRef.current) return;

      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 2, 30000);

      reconnectTimeoutRef.current = window.setTimeout(() => {
        reconnectTimeoutRef.current = null;
        connectWebSocket();
      }, delay);
    };

    socket.onerror = (err) => {
      console.error("WebSocket encountered an error:", err);
      socket.close();
    };
    // Reconnection deliberately follows the current socket lifecycle; loading collection state inside
    // this callback would create a declaration-order cycle with the data loader below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectionId, cryptoKey, user?.id]);

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (socketRef.current) {
        console.log("Closing active collection WebSocket connection");
        socketRef.current.onclose = null;
        socketRef.current.close();
        socketRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (typingTimerRef.current) {
        window.clearTimeout(typingTimerRef.current);
        typingTimerRef.current = null;
      }
    };
  }, [collectionId, connectWebSocket]);

  const loadCollectionData = async (showLoadingOverlay = true) => {
    if (!collectionId) return;
    if (showLoadingOverlay) {
      setLoading(true);
    }
    setErrorMessage(null);

    try {
      const [collRes, profileRes, colDocsRes, permissionsRes, allDocsRes, presenceRes] =
        await Promise.all([
          fetchWithAuth(`/collections/${collectionId}`),
          // Keep the established profile request in this compatibility batch. Some deployments use it
          // to refresh the authenticated profile while opening a collection.
          fetchWithAuth("/auth/profile"),
          fetchWithAuth(`/collections/${collectionId}/documents`),
          fetchWithAuth(`/collections/${collectionId}/permissions`),
          fetchWithAuth("/documents"),
          fetchWithAuth(`/collections/${collectionId}/presence`),
        ]);

      if (!collRes.ok) {
        if (collRes.status === 404 || collRes.status === 403) {
          onCollectionDeleted?.();
          return;
        }
        throw new Error(
          await extractApiErrorMessage(collRes, "Failed to load collection details."),
        );
      }

      const collData = (await collRes.json()) as Collection;
      setCollection(collData);
      void profileRes;

      if (colDocsRes.ok) {
        const colDocsData = await colDocsRes.json();
        setCollectionDocs(normalizeDocumentItems(colDocsData));
      }

      if (allDocsRes.ok) {
        const allDocsData = await allDocsRes.json();
        setAllDocs(normalizeDocumentItems(allDocsData));
      }

      if (permissionsRes.ok) {
        const permissionsData = (await permissionsRes.json()) as CollectionPermission[];
        setPermissions(permissionsData);
      }

      if (presenceRes?.ok) {
        const presenceData = await presenceRes.json();
        const nextPresence: Record<string, any> = {};
        (Array.isArray(presenceData) ? presenceData : []).forEach((p: any) => {
          nextPresence[p.user_id] = { is_online: p.is_online, last_seen: p.last_seen };
        });
        setMembersPresence(nextPresence);
      }
    } catch (error) {
      console.error(error);
      setErrorMessage(error instanceof Error ? error.message : "Failed to load collection.");
    } finally {
      if (showLoadingOverlay) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void loadCollectionData();
    // The loader is recreated on render; collectionId is the intentional reload boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectionId]);

  const availableDocs = useMemo(() => {
    const activeIds = new Set(collectionDocs.map((d) => d.document_id));
    return allDocs.filter((d) => !activeIds.has(d.document_id));
  }, [allDocs, collectionDocs]);

  const ownedDocumentIds = useMemo(() => {
    return new Set(collectionDocs.map((d) => d.document_id));
  }, [collectionDocs]);

  const isOwner = collection?.requester_access_role === "owner";
  const isPending = collection?.requester_access_role === "pending";
  const isConnectedMember = collection?.requester_access_role === "member";

  const filteredChats = useMemo(() => {
    if (!searchQueryText.trim()) return chats;
    const query = searchQueryText.toLowerCase().trim();
    return chats.filter((c) => {
      if (c.is_media) {
        // Try parsing file name in media messages to support searching media file names too!
        try {
          const metadata = JSON.parse(c.message);
          return metadata.filename?.toLowerCase().includes(query);
        } catch {
          return false;
        }
      }
      return c.message?.toLowerCase().includes(query);
    });
  }, [chats, searchQueryText]);

  function escapeRegExp(string: string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function highlightText(text: string, search: string) {
    if (!search.trim()) return <span>{text}</span>;
    const regex = new RegExp(`(${escapeRegExp(search)})`, "gi");
    const parts = text.split(regex);
    return (
      <span>
        {parts.map((part, i) =>
          regex.test(part) ? (
            <mark key={i} className="text-foreground rounded bg-amber-500/35 px-0.5 font-black">
              {part}
            </mark>
          ) : (
            part
          ),
        )}
      </span>
    );
  }

  const handleSendReaction = (messageId: string, emoji: string) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(
        JSON.stringify({
          action: "react",
          message_id: messageId,
          reaction: emoji,
        }),
      );
    } else {
      toast.error("WebSocket offline, reaction failed.");
    }
  };

  const handleClearChatHistory = async () => {
    if (
      !window.confirm(
        "Are you absolutely sure you want to permanently clear the entire chat history for everyone? This action is irreversible and deletes all messages and media attachments.",
      )
    ) {
      return;
    }

    try {
      const res = await fetchWithAuth(`/collections/${collectionId}/chats/clear`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to clear chat history");

      // Locally clear IndexedDB and local state
      setChats([]);
      processedMessageIdsRef.current.clear();
      await clearLocalMessages(collectionId);

      toast.success("Chat history cleared successfully.");
    } catch (err) {
      console.error(err);
      toast.error("Failed to clear chat history.");
    }
  };

  const handleDeleteMessage = (messageId: string) => {
    if (!window.confirm("Delete this message for everyone?")) return;
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(
        JSON.stringify({
          action: "delete",
          message_id: messageId,
        }),
      );
    } else {
      toast.error("WebSocket offline, deletion failed.");
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files);
      const oversized = files.find((f) => f.size > 26 * 1024 * 1024);
      if (oversized) {
        toast.error(`File "${oversized.name}" exceeds the 26MB size limit.`);
        return;
      }
      setStagedFiles((prev) => [...prev, ...files]);
      toast.success(`${files.length} file(s) staged.`);
    }
  };

  const handleAddDocuments = async () => {
    if (selectedDocumentIds.length === 0) return;
    setSavingDocs(true);
    try {
      const res = await fetchWithAuth(`/collections/${collectionId}/documents`, {
        method: "POST",
        body: JSON.stringify({ document_ids: selectedDocumentIds }),
      });
      if (!res.ok) {
        throw new Error(await extractApiErrorMessage(res, "Failed to add documents."));
      }
      setSelectedDocumentIds([]);
      toast.success("Documents successfully added to the bridge.");
      await loadCollectionData();
    } catch (error) {
      console.error(error);
      const message = error instanceof Error ? error.message : "Failed to add documents.";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setSavingDocs(false);
    }
  };

  const handleRemoveDocument = async (documentId: string) => {
    if (!window.confirm("Remove this document from the shared collection?")) return;
    setSavingDocs(true);
    try {
      const res = await fetchWithAuth(`/collections/${collectionId}/documents`, {
        method: "DELETE",
        body: JSON.stringify({ document_ids: [documentId] }),
      });
      if (!res.ok) {
        throw new Error(await extractApiErrorMessage(res, "Failed to remove document."));
      }
      toast.success("Document removed from the bridge.");
      await loadCollectionData();
    } catch (error) {
      console.error(error);
      const message = error instanceof Error ? error.message : "Failed to remove document.";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setSavingDocs(false);
    }
  };

  const handleSendRequest = async () => {
    const normalizedCode = connectCode.trim().toUpperCase();
    if (!normalizedCode) return;
    setSavingPermissions(true);
    try {
      const res = await fetchWithAuth(`/collections/${collectionId}/permissions`, {
        method: "POST",
        body: JSON.stringify({ connection_code: normalizedCode }),
      });
      if (!res.ok) {
        throw new Error(await extractApiErrorMessage(res, "Failed to send request."));
      }
      setConnectCode("");
      toast.success("Connection request sent.");
      await loadCollectionData();
    } catch (error) {
      console.error(error);
      const message = error instanceof Error ? error.message : "Failed to send connection request.";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setSavingPermissions(false);
    }
  };

  const handleUpdateExpiry = async (days: number) => {
    if (!collectionId) return;
    try {
      const res = await fetchWithAuth(`/collections/${collectionId}/expiry`, {
        method: "PUT",
        body: JSON.stringify({ expiry_days: days }),
      });
      if (!res.ok) throw new Error("Failed to update self-destruct timer.");
      const updated = await res.json();
      setCollection((prev) => (prev ? { ...prev, expiry_days: updated.expiry_days } : null));
      toast.success(
        `Self-destruct timer updated to ${days === 0 ? "No Expiry" : days === 1 ? "1 Day" : `${days} Days`}`,
      );
    } catch (err: any) {
      toast.error(err.message || "Failed to update self-destruct setting.");
    }
  };

  const handleExportBackup = async () => {
    if (!chats.length) {
      toast.error("No messages to back up.");
      return;
    }
    const password = window.prompt("Enter a strong security password to encrypt your chat backup:");
    if (!password) return;

    setIsExportingBackup(true);
    try {
      const rawJson = JSON.stringify(chats);
      const backupData = await encryptBackup(rawJson, password);

      const blob = new Blob([JSON.stringify(backupData, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `averqel_backup_${collection?.name || "chat"}_${Date.now()}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success("Encrypted chat backup file exported successfully!");
    } catch (err) {
      console.error(err);
      toast.error("Failed to generate encrypted backup.");
    } finally {
      setIsExportingBackup(false);
    }
  };

  const handleImportBackup = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = async (e: any) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async (evt) => {
        try {
          const backupObj = JSON.parse(evt.target?.result as string);
          if (!backupObj.ciphertext || !backupObj.salt || !backupObj.iv) {
            toast.error("Invalid backup file format. Missing metadata.");
            return;
          }
          const password = window.prompt(
            "Enter the security password used to encrypt this backup:",
          );
          if (!password) return;

          setIsImportingBackup(true);
          const decryptedJson = await decryptBackup(
            backupObj.ciphertext,
            backupObj.salt,
            backupObj.iv,
            password,
          );
          const restoredChats = JSON.parse(decryptedJson);
          if (!Array.isArray(restoredChats)) {
            throw new Error("Restored payload is not a valid chat list.");
          }

          for (const msg of restoredChats) {
            await saveLocalMessage(msg);
          }

          const freshChats = await getLocalMessages(collectionId);
          setChats(freshChats);
          processedMessageIdsRef.current.clear();
          freshChats.forEach((m) => processedMessageIdsRef.current.add(m.id));

          toast.success(`Successfully imported ${restoredChats.length} messages from backup!`);
        } catch (err) {
          console.error(err);
          toast.error("Incorrect password or corrupted backup file.");
        } finally {
          setIsImportingBackup(false);
        }
      };
      reader.readAsText(file);
    };
    input.click();
  };

  // This owner-only action remains available to the parent collection control surface.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleDeleteCollection = async () => {
    if (!window.confirm("Are you sure you want to delete this collection for all members?")) return;
    setDeletingCollection(true);
    try {
      const res = await fetchWithAuth(`/collections/${collectionId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        throw new Error(await extractApiErrorMessage(res, "Failed to delete collection."));
      }
      toast.success("Collection successfully deleted.");
      if (onCollectionDeleted) {
        onCollectionDeleted();
      } else {
        window.history.pushState(null, "", window.location.pathname);
      }
    } catch (error) {
      console.error(error);
      const message = error instanceof Error ? error.message : "Failed to delete collection.";
      setErrorMessage(message);
      toast.error(message);
      setDeletingCollection(false);
    }
  };

  const handleLeaveCollection = async () => {
    if (!window.confirm("Leave this collection bridge?")) return;
    setDeletingCollection(true);
    try {
      const res = await fetchWithAuth(`/collections/${collectionId}/permissions`, {
        method: "DELETE",
        body: JSON.stringify({ user_ids: [] }),
      });
      if (!res.ok) {
        throw new Error(await extractApiErrorMessage(res, "Failed to leave collection."));
      }
      toast.success("Successfully left the collection.");
      if (onCollectionDeleted) {
        onCollectionDeleted();
      } else {
        router.push(collectionsBasePath);
      }
    } catch (error) {
      console.error(error);
      const message = error instanceof Error ? error.message : "Failed to leave collection.";
      setErrorMessage(message);
      toast.error(message);
      setDeletingCollection(false);
    }
  };

  const handleInvitationResponse = async (action: "approve" | "deny") => {
    setSavingPermissions(true);
    try {
      const res = await fetchWithAuth(`/collections/${collectionId}/invitations/respond`, {
        method: "POST",
        body: JSON.stringify({ action }),
      });
      if (!res.ok) throw new Error("Failed to respond to invitation.");
      toast.success(action === "approve" ? "Collection bridge connected." : "Invitation denied.");
      if (action === "approve") {
        await loadCollectionData();
      } else {
        if (onCollectionDeleted) {
          onCollectionDeleted();
        } else {
          window.history.pushState(null, "", window.location.pathname);
        }
      }
    } catch (error) {
      console.error(error);
      setErrorMessage("Failed to respond to invitation.");
      toast.error("Failed to respond to invitation.");
    } finally {
      setSavingPermissions(false);
    }
  };

  const handleRemoveMember = async (userId: string, email: string | null | undefined) => {
    if (!window.confirm(`Remove ${email || "this member"} from the collection?`)) return;
    setSavingPermissions(true);
    try {
      const res = await fetchWithAuth(`/collections/${collectionId}/permissions`, {
        method: "DELETE",
        body: JSON.stringify({ user_ids: [userId] }),
      });
      if (!res.ok) {
        throw new Error(await extractApiErrorMessage(res, "Failed to remove member."));
      }
      toast.success("Member removed.");
      await loadCollectionData();
    } catch (error) {
      console.error(error);
      const message = error instanceof Error ? error.message : "Failed to remove member.";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setSavingPermissions(false);
    }
  };

  const handleSendChat = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (sendingChat) return;

    const trimmedText = chatText.trim();
    const hasText = trimmedText.length > 0;
    const hasFiles = stagedFiles.length > 0;

    if (!hasText && !hasFiles) return;

    setSendingChat(true);
    const toastId = toast.loading(
      hasFiles ? `Encrypting and sending ${stagedFiles.length} file(s)...` : "Sending message...",
    );

    try {
      if (hasFiles) {
        for (let i = 0; i < stagedFiles.length; i++) {
          const file = stagedFiles[i];
          const { encryptedBlob, iv } = await encryptFile(file, cryptoKey!);

          const formData = new FormData();
          formData.append("file", encryptedBlob, file.name);

          const uploadRes = await fetchWithAuth(`/collections/${collectionId}/chats/media`, {
            method: "POST",
            body: formData,
          });

          if (!uploadRes.ok) throw new Error(`Upload failed for file: ${file.name}`);
          const uploadData = await uploadRes.json();

          const fileMetadata = {
            media_id: uploadData.media_id,
            filename: file.name,
            mime_type: file.type,
            iv: iv,
            caption: i === 0 && hasText ? trimmedText : undefined,
          };

          const encryptedPayload = await encryptMessage(JSON.stringify(fileMetadata), cryptoKey!);

          if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
            socketRef.current.send(
              JSON.stringify({
                action: "post_message",
                content: encryptedPayload,
                is_media: true,
                media_mime_type: file.type,
              }),
            );
          } else {
            const res = await fetchWithAuth(`/collections/${collectionId}/chats`, {
              method: "POST",
              body: JSON.stringify({
                message: encryptedPayload,
                is_media: true,
                media_mime_type: file.type,
              }),
            });
            if (res.ok) {
              const newMsg = await res.json();
              const decryptedMsg = { ...newMsg, message: JSON.stringify(fileMetadata) };
              await saveLocalMessage(decryptedMsg);
              setChats((current) => [...current, decryptedMsg]);
            }
          }
        }
        setStagedFiles([]);
        setChatText("");
        toast.success("Files sent securely.", { id: toastId });
      } else {
        // Text-only E2EE message
        let payloadMessage = trimmedText;
        if (cryptoKey) {
          payloadMessage = await encryptMessage(trimmedText, cryptoKey);
        }

        if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.send(
            JSON.stringify({
              action: "post_message",
              content: payloadMessage,
              is_media: false,
            }),
          );
          setChatText("");
        } else {
          const res = await fetchWithAuth(`/collections/${collectionId}/chats`, {
            method: "POST",
            body: JSON.stringify({ message: payloadMessage, is_media: false }),
          });
          if (res.ok) {
            const newMsg = await res.json();
            const decryptedMsg = { ...newMsg, message: trimmedText };
            await saveLocalMessage(decryptedMsg);
            setChats((current) => {
              if (current.some((m) => m.id === newMsg.id)) return current;
              return [...current, decryptedMsg];
            });
            setChatText("");
          }
        }
        toast.success("Message sent securely.", { id: toastId });
      }
      setTimeout(scrollChatToBottom, 100);
    } catch (err) {
      console.error(err);
      toast.error("Failed to sendsecure message.", { id: toastId });
    } finally {
      setSendingChat(false);
    }
  };

  const handleStageMedia = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files);
      const oversized = files.find((f) => f.size > 26 * 1024 * 1024);
      if (oversized) {
        toast.error(`File "${oversized.name}" exceeds the 26MB size limit.`);
        e.target.value = "";
        return;
      }
      setStagedFiles((prev) => [...prev, ...files]);
      e.target.value = "";
    }
  };

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col overflow-hidden bg-transparent">
      {/* Drag & Drop listeners attached to timeline outer block */}
      <div
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className="relative flex min-h-0 flex-1 flex-col"
      >
        {/* Error banner */}
        {errorMessage && (
          <div className="shrink-0 border-b border-red-500/20 bg-red-500/10 px-5 py-3 text-xs text-red-400">
            {errorMessage}
          </div>
        )}

        {/* Direct detail-route controls. The embedded collection view supplies these from its parent. */}
        <div className="border-foreground/10 bg-foreground/[0.01] flex shrink-0 items-center justify-between gap-3 border-b px-5 py-2.5 dark:border-white/5">
          <div className="flex min-w-0 items-center gap-2">
            <Link
              href={`${collectionsBasePath}/${collectionId}?section=documents`}
              className={`rounded-lg border px-3 py-2 text-[10px] font-black tracking-wider uppercase transition ${
                activeDrawer === "documents"
                  ? "border-amber-500 bg-amber-500 text-slate-950"
                  : "border-foreground/10 bg-foreground/5 hover:text-foreground text-slate-500"
              }`}
              onClick={() => setActiveDrawer("documents")}
            >
              Shared Documents
            </Link>
            <Link
              href={`${collectionsBasePath}/${collectionId}?section=access`}
              className={`rounded-lg border px-3 py-2 text-[10px] font-black tracking-wider uppercase transition ${
                activeDrawer === "members"
                  ? "border-amber-500 bg-amber-500 text-slate-950"
                  : "border-foreground/10 bg-foreground/5 hover:text-foreground text-slate-500"
              }`}
              onClick={() => setActiveDrawer("members")}
            >
              Bridge Members
            </Link>
          </div>
          {isConnectedMember && (
            <button
              type="button"
              aria-label="Leave collection"
              onClick={() => void handleLeaveCollection()}
              disabled={deletingCollection}
              className="rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-[10px] font-black tracking-wider text-red-400 uppercase transition hover:bg-red-500/10 disabled:opacity-50"
            >
              Leave Collection
            </button>
          )}
        </div>

        {/* Presence and Typing Indicator Subheader */}
        <div className="bg-foreground/[0.02] border-foreground/10 flex shrink-0 items-center justify-between border-b px-5 py-2.5 text-xs dark:border-white/5">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowShieldModal(true)}
              className="flex cursor-pointer items-center gap-1.5 transition hover:scale-[1.02]"
            >
              <ShieldCheck size={14} className="animate-pulse text-emerald-500" />
              <span className="hover:text-foreground text-[9px] font-extrabold tracking-widest text-slate-500 uppercase">
                E2EE SECURE CHANNEL
              </span>
            </button>
          </div>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => setShowSearchBar(!showSearchBar)}
              className="hover:text-foreground cursor-pointer text-slate-500 transition"
            >
              <Search size={14} />
            </button>
            <div className="flex items-center gap-2">
              {/* WS status chip */}
              {wsStatus === "online" ? (
                <span className="flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-extrabold tracking-wider text-emerald-500 uppercase">
                  <span className="h-1 w-1 animate-ping rounded-full bg-emerald-500" />
                  Live Sync
                </span>
              ) : wsStatus === "connecting" ? (
                <span className="flex animate-pulse items-center gap-1 rounded-full border border-blue-500/20 bg-blue-500/10 px-2 py-0.5 text-[9px] font-extrabold tracking-wider text-blue-400 uppercase">
                  <span className="h-1 w-1 rounded-full bg-blue-400" />
                  Syncing...
                </span>
              ) : (
                <span className="flex items-center gap-1 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[9px] font-extrabold tracking-wider text-amber-500 uppercase">
                  <span className="h-1 w-1 rounded-full bg-amber-500" />
                  Local Cache Only
                </span>
              )}
              {otherUserTyping ? (
                <span className="animate-pulse text-[10px] font-extrabold tracking-wider text-emerald-500 uppercase">
                  typing...
                </span>
              ) : (
                (() => {
                  const otherMember = permissions.find((p) => p.user_id !== user?.id);
                  if (otherMember && otherMember.user_id) {
                    const presence = membersPresence[otherMember.user_id];
                    if (presence?.is_online) {
                      return (
                        <span className="text-[10px] font-extrabold tracking-wider text-emerald-500 uppercase">
                          online
                        </span>
                      );
                    } else if (presence?.last_seen) {
                      const lastSeenTime = new Date(presence.last_seen).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      });
                      return (
                        <span className="text-slate-550 text-[10px] font-semibold tracking-wider uppercase">
                          last seen {lastSeenTime}
                        </span>
                      );
                    }
                  }
                  return (
                    <span className="text-slate-550 text-[10px] font-semibold tracking-wider uppercase">
                      secured offline
                    </span>
                  );
                })()
              )}
            </div>
          </div>
        </div>

        {/* Search Bar Input Panel */}
        {showSearchBar && (
          <div className="bg-foreground/[0.01] border-foreground/10 flex shrink-0 items-center gap-2 border-b px-5 py-2.5 dark:border-white/5">
            <Search size={13} className="text-slate-550" />
            <input
              type="text"
              value={searchQueryText}
              onChange={(e) => setSearchQueryText(e.target.value)}
              placeholder="Search chat history..."
              className="text-foreground flex-1 border-none bg-transparent text-xs placeholder-slate-500 outline-none"
              autoFocus
            />
            {searchQueryText && (
              <button
                type="button"
                onClick={() => setSearchQueryText("")}
                className="hover:text-foreground cursor-pointer text-[10px] font-bold text-slate-500"
              >
                Clear
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setShowSearchBar(false);
                setSearchQueryText("");
              }}
              className="text-slate-550 hover:text-foreground ml-2 cursor-pointer text-xs font-extrabold"
            >
              Cancel
            </button>
          </div>
        )}

        {/* Drag and Drop File Encryption Overlay */}
        {isDragging && (
          <div className="bg-background/80 absolute inset-0 z-40 m-4 flex animate-pulse flex-col items-center justify-center rounded-2xl border-4 border-dashed border-emerald-500/50 p-6 text-center backdrop-blur-md">
            <span className="mb-3 text-4xl">☁️</span>
            <p className="text-xs font-black tracking-wider text-emerald-500 uppercase">
              Drop file to encrypt & send
            </p>
            <p className="mt-1 max-w-xs text-[10px] leading-relaxed text-slate-500">
              Your file will be encrypted on your device using AES-GCM 256 before transit.
            </p>
          </div>
        )}

        {/* Scrollable messages timeline */}
        <div className="bg-foreground/[0.005] flex-1 space-y-4 overflow-y-auto p-5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {/* Invitation banner if pending */}
          {isPending && (
            <div className="bg-background/80 border-foreground/10 mx-auto mt-6 flex max-w-md flex-col items-center justify-center space-y-4 rounded-[1.6rem] border p-5 text-center shadow-none backdrop-blur-md dark:border-white/5">
              <span className="text-xl">📨</span>
              <div className="space-y-1">
                <h4 className="text-foreground/80 text-xs font-black tracking-widest uppercase">
                  Join Shared Bridge Connection?
                </h4>
                <p className="text-[11px] leading-relaxed text-slate-500">
                  You have been invited to connect in this bridge workspace. Approve to view shared
                  documents and start exchanging live messages.
                </p>
              </div>
              <div className="flex w-full items-center gap-3">
                <button
                  onClick={() => void handleInvitationResponse("deny")}
                  disabled={savingPermissions}
                  className="text-red-455 flex-1 cursor-pointer rounded-xl border border-red-500/25 bg-red-500/10 py-2.5 text-xs font-bold transition hover:bg-red-500/20 hover:text-red-400 disabled:opacity-60"
                >
                  Deny
                </button>
                <button
                  onClick={() => void handleInvitationResponse("approve")}
                  disabled={savingPermissions}
                  className="flex-1 cursor-pointer rounded-xl border border-emerald-500/20 bg-emerald-600 py-2.5 text-xs font-bold text-white shadow-none transition hover:bg-emerald-500 disabled:opacity-60"
                >
                  Approve
                </button>
              </div>
            </div>
          )}

          {filteredChats.length > 0
            ? filteredChats.map((msg) => {
                const isSelf = msg.user_id === user?.id;
                const date = new Date(msg.created_at);
                const formattedTime = date.toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                });
                const isMsgDeleted = msg.message === "This message was deleted";
                return (
                  <div
                    key={msg.id}
                    className={`group relative flex max-w-[80%] flex-col sm:max-w-[65%] ${isSelf ? "ml-auto items-end" : "mr-auto items-start"}`}
                    onContextMenu={(e) => {
                      if (isMsgDeleted) return;
                      e.preventDefault();
                      setActiveMessageMenuId(activeMessageMenuId === msg.id ? null : msg.id);
                    }}
                  >
                    {/* Options Dropdown Menu */}
                    {activeMessageMenuId === msg.id && !isMsgDeleted && (
                      <>
                        <div
                          className="fixed inset-0 z-20 cursor-default"
                          onClick={() => setActiveMessageMenuId(null)}
                        />
                        <div
                          className={`absolute z-30 min-w-[7.5rem] rounded-xl border border-white/10 bg-slate-900 py-1 text-[9px] font-bold tracking-wider text-slate-400 uppercase shadow-xl ${isSelf ? "top-8 right-2" : "top-8 left-2"}`}
                        >
                          {!msg.is_media && (
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText(msg.message);
                                setActiveMessageMenuId(null);
                                toast.success("Copied message.");
                              }}
                              className="w-full cursor-pointer px-3 py-2 text-left transition hover:bg-white/5 hover:text-white"
                            >
                              Copy
                            </button>
                          )}
                          {(isSelf || isOwner) && (
                            <button
                              type="button"
                              onClick={() => {
                                handleDeleteMessage(msg.id);
                                setActiveMessageMenuId(null);
                              }}
                              className="w-full cursor-pointer px-3 py-2 text-left text-red-500 transition hover:bg-red-500/10 hover:text-red-400"
                            >
                              Delete
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => setActiveMessageMenuId(null)}
                            className="w-full cursor-pointer px-3 py-2 text-left transition hover:bg-white/5"
                          >
                            Cancel
                          </button>
                        </div>
                      </>
                    )}

                    {/* Floating Reactions Bar */}
                    {!isMsgDeleted && (
                      <div className="bg-background/95 border-foreground/10 absolute -top-7 z-15 hidden items-center gap-1 rounded-full border px-2 py-1 shadow-lg backdrop-blur group-hover:flex dark:border-white/5">
                        {["👍", "❤️", "😂", "😮", "😢", "🙏"].map((emoji) => (
                          <button
                            key={emoji}
                            type="button"
                            onClick={() => handleSendReaction(msg.id, emoji)}
                            className="cursor-pointer p-0.5 text-xs transition hover:scale-130 active:scale-95"
                          >
                            {emoji}
                          </button>
                        ))}
                      </div>
                    )}

                    <div className="mb-1 flex items-center gap-1.5 px-1">
                      <img
                        src={
                          msg.user_avatar ||
                          permissions.find((p) => p.user_id === msg.user_id)?.user_avatar ||
                          DEFAULT_AVATAR_SVG
                        }
                        alt="avatar"
                        className="border-foreground/10 h-4 w-4 shrink-0 rounded-full border object-cover select-none"
                      />
                      <span className="text-[9px] font-bold tracking-wider text-slate-500">
                        {isSelf ? "You" : msg.user_email ? msg.user_email.split("@")[0] : "Partner"}
                      </span>
                    </div>
                    <div
                      className={`flex w-full items-center gap-2 ${isSelf ? "flex-row-reverse" : "flex-row"}`}
                    >
                      <div
                        className={`rounded-[1.2rem] border px-4 py-2.5 text-xs leading-relaxed font-semibold transition-all ${
                          isSelf
                            ? "text-foreground rounded-tr-none border-emerald-500/20 bg-emerald-500/10 dark:bg-emerald-800/15 dark:text-emerald-100"
                            : "bg-foreground/5 border-foreground/5 text-foreground rounded-tl-none dark:border-white/5 dark:bg-slate-900 dark:text-slate-200"
                        }`}
                      >
                        {isMsgDeleted ? (
                          <p className="flex items-center gap-1.5 font-normal text-slate-500 italic select-none dark:text-slate-400">
                            <span className="text-xs">🚫</span> This message was deleted
                          </p>
                        ) : msg.is_media ? (
                          <SecureMediaRenderer
                            collectionId={collectionId}
                            msg={msg}
                            cryptoKey={cryptoKey}
                            onPreview={(url, filename, mimeType) =>
                              setActivePreviewFile({ url, filename, mimeType })
                            }
                          />
                        ) : (
                          <p className="white-space-pre-wrap break-words">
                            {highlightText(msg.message, searchQueryText)}
                          </p>
                        )}
                        <div className="mt-1.5 flex items-center justify-end gap-1">
                          <span
                            className={`block text-[8px] font-bold ${isSelf ? "text-emerald-500/70" : "text-slate-500"}`}
                          >
                            {formattedTime}
                          </span>
                          {isSelf && !isMsgDeleted && (
                            <span className="ml-1 inline-flex items-center">
                              {msg.status === "read" ? (
                                <CheckCheck size={11} className="text-emerald-500" />
                              ) : msg.status === "delivered" ? (
                                <CheckCheck size={11} className="text-slate-500" />
                              ) : (
                                <Check size={11} className="text-slate-500" />
                              )}
                            </span>
                          )}
                        </div>
                      </div>
                      {/* Tiny Options Button */}
                      {!isMsgDeleted && (
                        <button
                          type="button"
                          onClick={() =>
                            setActiveMessageMenuId(activeMessageMenuId === msg.id ? null : msg.id)
                          }
                          className="bg-foreground/5 border-foreground/10 hover:text-foreground hover:bg-foreground/10 flex h-6 w-6 shrink-0 cursor-pointer items-center justify-center rounded-full border text-xs font-black text-slate-500 opacity-0 transition select-none group-hover:opacity-100"
                        >
                          ⋮
                        </button>
                      )}
                    </div>

                    {/* Render Reaction Badges */}
                    {(() => {
                      if (!msg.reactions) return null;
                      let reactionsObj: Record<string, string> = {};
                      try {
                        reactionsObj =
                          typeof msg.reactions === "string"
                            ? JSON.parse(msg.reactions)
                            : msg.reactions;
                      } catch {}

                      const emojisList = Object.values(reactionsObj);
                      if (emojisList.length === 0) return null;

                      const counts: Record<string, number> = {};
                      emojisList.forEach((e) => {
                        counts[e] = (counts[e] || 0) + 1;
                      });

                      return (
                        <div className="mt-1 flex items-center gap-1 px-1">
                          {Object.entries(counts).map(([emoji, count]) => (
                            <div
                              key={emoji}
                              className="bg-foreground/5 border-foreground/5 flex items-center gap-0.5 rounded-full border px-1.5 py-0.5 text-[9px] font-bold shadow-none dark:border-white/5 dark:bg-slate-900"
                            >
                              <span>{emoji}</span>
                              {count > 1 && (
                                <span className="ml-0.5 text-[8px] text-slate-500">{count}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      );
                    })()}
                  </div>
                );
              })
            : !isPending && (
                <div className="flex h-full flex-col items-center justify-center p-6 text-center text-slate-500">
                  <MessageSquare size={36} className="mb-2 animate-pulse text-slate-400" />
                  <p className="text-xs font-bold tracking-wider text-slate-400 uppercase">
                    Secure Live Chat Channel
                  </p>
                  <p className="mt-1.5 max-w-[15rem] text-[10px] leading-relaxed text-slate-500">
                    Start sending messages here. All chats and sync operations are delivered in real
                    time.
                  </p>
                </div>
              )}
          <div ref={chatEndRef} />
        </div>

        {/* 3. Typing Composer Form */}
        {!isPending && (
          <div className="border-foreground/10 bg-foreground/[0.01] flex shrink-0 flex-col border-t dark:border-white/5">
            {/* Staged Files Preview Row */}
            {stagedFiles.length > 0 && (
              <div className="border-foreground/5 flex max-h-[7rem] items-center gap-3 overflow-x-auto border-b bg-slate-950/20 px-4 py-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {stagedFiles.map((file, idx) => {
                  const isStagedImg = file.type.startsWith("image/");
                  return (
                    <div
                      key={idx}
                      className="bg-foreground/5 border-foreground/10 group relative flex max-w-[12rem] shrink-0 items-center gap-2 rounded-2xl border px-3 py-2 dark:border-white/5"
                    >
                      {isStagedImg ? (
                        <img
                          src={URL.createObjectURL(file)}
                          alt="preview"
                          className="h-8 w-8 shrink-0 rounded-lg border border-white/10 object-cover"
                        />
                      ) : (
                        <div className="text-amber-550 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-amber-500/25 bg-amber-500/10">
                          <FileIcon size={14} />
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="text-foreground truncate text-[10px] leading-snug font-bold">
                          {file.name}
                        </p>
                        <p className="mt-0.5 text-[8px] font-bold tracking-widest text-slate-500 uppercase">
                          {(file.size / (1024 * 1024)).toFixed(2)} MB
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setStagedFiles((prev) => prev.filter((_, i) => i !== idx))}
                        className="absolute -top-1.5 -right-1.5 flex h-5 w-5 cursor-pointer items-center justify-center rounded-full border border-white/10 bg-slate-900 text-[9px] font-bold text-slate-400 shadow-lg transition hover:text-white"
                      >
                        <X size={10} />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Input Form */}
            <form onSubmit={handleSendChat} className="flex items-center gap-2 p-4">
              <label className="border-foreground/10 bg-foreground/5 hover:bg-foreground/10 hover:text-foreground flex h-10 w-10 flex-shrink-0 cursor-pointer items-center justify-center rounded-xl border text-slate-500 transition">
                <Paperclip size={15} />
                <input type="file" multiple onChange={handleStageMedia} className="hidden" />
              </label>
              <input
                type="text"
                value={chatText}
                onChange={(e) => {
                  setChatText(e.target.value);
                  handleTypingActivity();
                }}
                placeholder={
                  stagedFiles.length > 0 ? "Add caption to files..." : "Type a message..."
                }
                className="bg-background/80 border-foreground/10 text-foreground flex-1 rounded-xl border px-4 py-3 text-xs placeholder-slate-500 transition outline-none focus:border-amber-500/30 dark:border-white/5"
              />
              <button
                type="submit"
                disabled={sendingChat || (!chatText.trim() && stagedFiles.length === 0)}
                className="flex h-10 w-10 flex-shrink-0 cursor-pointer items-center justify-center rounded-xl bg-amber-500 font-bold text-slate-950 shadow-none transition-all hover:scale-[1.02] hover:brightness-115 active:scale-95 disabled:opacity-50"
              >
                <Send size={14} />
              </button>
            </form>
          </div>
        )}

        {/* Drawer 1: Shared Documents Slider (R-to-L) */}
        <div
          className={`bg-background/95 border-foreground/10 absolute inset-y-0 right-0 z-20 flex w-full transform flex-col border-l shadow-none backdrop-blur-md transition-transform duration-300 sm:w-[26rem] dark:border-white/5 ${
            activeDrawer === "documents" ? "translate-x-0" : "translate-x-full"
          }`}
        >
          {/* Drawer Header */}
          <div className="border-foreground/10 bg-foreground/[0.01] flex shrink-0 items-center justify-between border-b px-5 py-4 dark:border-white/5">
            <div className="flex items-center gap-2.5">
              <FileStack size={16} className="text-amber-500" />
              <h3 className="text-foreground/90 text-xs font-black tracking-wider uppercase">
                Shared Documents
              </h3>
            </div>
            <button
              onClick={() => setActiveDrawer(null)}
              className="hover:text-foreground cursor-pointer p-1 text-slate-500 transition duration-200 hover:rotate-90"
            >
              <X size={16} />
            </button>
          </div>

          {/* Drawer Content */}
          <div className="bg-foreground/[0.003] flex-1 space-y-6 overflow-y-auto p-5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {/* 1. Add Documents Uploader Form */}
            <div className="space-y-3.5">
              <h4 className="text-slate-550 px-1 text-[9px] font-bold tracking-widest uppercase dark:text-slate-500">
                Available to add
              </h4>
              <div className="max-h-[16rem] space-y-2 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {availableDocs.length > 0 ? (
                  availableDocs.map((doc) => {
                    const isSelected = selectedDocumentIds.includes(doc.document_id);
                    const ext = doc.filename.split(".").pop()?.toUpperCase() || "DOC";
                    return (
                      <label
                        key={doc.document_id}
                        className={`flex cursor-pointer items-center justify-between gap-3 rounded-xl border p-3 transition-all duration-200 ${
                          isSelected
                            ? "border-amber-500/30 bg-amber-500/[0.06] shadow-[0_0_12px_rgba(245,158,11,0.05)]"
                            : "bg-foreground/[0.015] border-foreground/5 hover:bg-foreground/[0.03] hover:border-foreground/10 dark:border-white/5"
                        }`}
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <div
                            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[8px] font-black ${
                              isSelected
                                ? "border border-amber-500/30 bg-amber-500/20 text-amber-500"
                                : "bg-foreground/5 border-foreground/10 border text-slate-400"
                            }`}
                          >
                            {ext}
                          </div>
                          <div className="min-w-0">
                            <p
                              className={`truncate text-xs font-semibold transition-colors ${isSelected ? "text-amber-500" : "text-foreground"}`}
                            >
                              {doc.filename}
                            </p>
                            <p className="text-slate-550 mt-0.5 text-[8px] font-bold tracking-widest uppercase dark:text-slate-500">
                              {doc.status}
                            </p>
                          </div>
                        </div>
                        <div className="relative flex shrink-0 items-center justify-center">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={(e) =>
                              setSelectedDocumentIds((current) =>
                                e.target.checked
                                  ? [...current, doc.document_id]
                                  : current.filter((id) => id !== doc.document_id),
                              )
                            }
                            className="hidden"
                          />
                          <div
                            className={`flex h-5 w-5 items-center justify-center rounded-lg border transition-all ${
                              isSelected
                                ? "scale-105 border-amber-500 bg-amber-500 text-slate-950"
                                : "border-foreground/20 bg-background/50 dark:border-white/20"
                            }`}
                          >
                            {isSelected && <Check size={11} className="stroke-[3]" />}
                          </div>
                        </div>
                      </label>
                    );
                  })
                ) : (
                  <div className="border-foreground/10 bg-foreground/[0.005] rounded-xl border border-dashed p-6 text-center dark:border-white/5">
                    <p className="text-slate-550 text-[10px] font-bold tracking-wider uppercase">
                      All documents added
                    </p>
                    <p className="mt-1 text-[9px] text-slate-500">
                      No additional docs available to connect.
                    </p>
                  </div>
                )}
              </div>
              {availableDocs.length > 0 && (
                <button
                  type="button"
                  disabled={savingDocs || selectedDocumentIds.length === 0}
                  onClick={() => void handleAddDocuments()}
                  className="w-full cursor-pointer rounded-xl border border-emerald-500/20 bg-gradient-to-r from-emerald-600 to-teal-600 py-3 text-xs font-black tracking-wider text-white uppercase shadow-none transition-all hover:brightness-110 active:scale-98 disabled:pointer-events-none disabled:opacity-50"
                >
                  {savingDocs ? "Adding..." : "Add Selected Documents"}
                </button>
              )}
            </div>

            {/* 2. Bridge Inventory */}
            <div className="space-y-3.5">
              <h4 className="text-slate-550 px-1 text-[9px] font-bold tracking-widest uppercase dark:text-slate-500">
                Bridge Inventory
              </h4>
              <div className="space-y-2">
                {collectionDocs.length > 0 ? (
                  collectionDocs.map((doc) => {
                    const ext = doc.filename.split(".").pop()?.toUpperCase() || "DOC";
                    return (
                      <div
                        key={doc.document_id}
                        className="bg-foreground/[0.01] border-foreground/5 hover:border-foreground/10 flex items-center justify-between gap-3 rounded-xl border p-3 transition-all duration-200 dark:border-white/5 dark:bg-slate-950/20 dark:hover:border-white/10"
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <div className="bg-foreground/5 border-foreground/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border text-[8px] font-black text-slate-400">
                            {ext}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="text-foreground truncate text-xs font-semibold">
                              {doc.filename}
                            </p>
                            <p className="text-slate-550 mt-0.5 text-[8px] font-bold tracking-widest uppercase dark:text-slate-500">
                              {doc.status}
                            </p>
                          </div>
                        </div>
                        {ownedDocumentIds.has(doc.document_id) && isConnectedMember ? (
                          <button
                            type="button"
                            disabled={savingDocs}
                            onClick={() => void handleRemoveDocument(doc.document_id)}
                            aria-label={`Remove document ${doc.filename}`}
                            className="flex-shrink-0 cursor-pointer rounded-lg border border-red-500/20 bg-red-500/10 px-2.5 py-1.5 text-[9px] font-bold tracking-wider text-red-400 uppercase transition hover:bg-red-500/20"
                          >
                            Remove
                          </button>
                        ) : (
                          <span className="text-slate-550 border-foreground/10 bg-background flex-shrink-0 rounded-lg border px-2.5 py-1.5 text-[8px] font-black tracking-widest uppercase dark:border-white/5 dark:bg-slate-900">
                            Shared
                          </span>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <div className="border-foreground/10 bg-foreground/[0.005] flex flex-col items-center justify-center rounded-xl border border-dashed p-8 text-center dark:border-white/5">
                    <span className="mb-1.5 animate-pulse text-lg text-slate-500">📂</span>
                    <p className="text-slate-550 text-[10px] font-bold tracking-wider uppercase">
                      No documents shared
                    </p>
                    <p className="mt-1 max-w-[13rem] text-[9px] text-slate-500">
                      Select from available files above to populate the bridge inventory.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Drawer 2: Bridge Members Slider (R-to-L) */}
        <div
          className={`bg-background/95 border-foreground/10 absolute inset-y-0 right-0 z-20 flex w-full transform flex-col border-l shadow-none backdrop-blur-md transition-transform duration-300 sm:w-[26rem] dark:border-white/5 ${
            activeDrawer === "members" ? "translate-x-0" : "translate-x-full"
          }`}
        >
          {/* Drawer Header */}
          <div className="border-foreground/10 flex shrink-0 items-center justify-between border-b px-5 py-4 dark:border-white/5">
            <div className="flex items-center gap-2">
              <Users size={16} className="text-amber-500" />
              <h3 className="text-foreground/80 text-xs font-black tracking-wider uppercase">
                Bridge Members
              </h3>
            </div>
            <button
              onClick={() => setActiveDrawer(null)}
              className="hover:text-foreground p-1 text-slate-500 transition"
            >
              <X size={16} />
            </button>
          </div>

          {/* Drawer Content */}
          <div className="flex-1 space-y-6 overflow-y-auto p-5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {/* 1. Send Access Invitation Request */}
            {isOwner && collection && collection.member_count < 10 && (
              <div className="space-y-3">
                <h4 className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">
                  Invite Member
                </h4>
                <div className="bg-foreground/[0.02] border-foreground/10 space-y-3 rounded-xl border p-4 dark:border-white/5 dark:bg-slate-950/45">
                  <p className="text-slate-550 text-[11px] leading-relaxed dark:text-slate-400">
                    Input a connection code below to invite a user into this shared workspace
                    channel.
                  </p>
                  <div className="flex items-center gap-2">
                    <input
                      value={connectCode}
                      onChange={(e) => setConnectCode(e.target.value.toUpperCase())}
                      placeholder="Connection ID"
                      className="bg-background border-foreground/10 text-foreground flex-1 rounded-xl border px-3 py-2.5 text-xs uppercase transition outline-none focus:border-amber-500/30 dark:border-white/5"
                    />
                    <button
                      type="button"
                      disabled={savingPermissions || !connectCode.trim()}
                      onClick={() => void handleSendRequest()}
                      className="cursor-pointer rounded-xl bg-amber-500 px-4 py-2.5 text-xs font-bold text-slate-950 shadow-none transition-all hover:brightness-110 active:scale-95 disabled:opacity-50"
                    >
                      Invite
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* 2. Member Topology list */}
            <div className="space-y-3">
              <h4 className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">
                Members Topology
              </h4>
              <div className="space-y-2">
                {permissions.map((perm) => {
                  const isUserSelf = perm.user_id === user?.id;
                  return (
                    <div
                      key={perm.id}
                      className="bg-foreground/[0.02] border-foreground/10 flex items-center justify-between gap-3 rounded-xl border p-3 dark:border-white/5 dark:bg-slate-950/40"
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        <img
                          src={perm.user_avatar || DEFAULT_AVATAR_SVG}
                          alt="avatar"
                          className="border-foreground/10 h-8 w-8 shrink-0 rounded-full border object-cover select-none"
                        />
                        <div className="min-w-0">
                          <p className="text-foreground truncate text-xs font-semibold">
                            {perm.user_email || perm.user_id}
                          </p>
                          <p className="mt-0.5 text-[9px] tracking-widest text-slate-500 uppercase">
                            {perm.role}
                          </p>
                        </div>
                      </div>

                      {isUserSelf ? (
                        <span className="border-foreground/10 bg-background rounded-lg border px-2.5 py-1.5 text-[9px] font-bold tracking-wider text-slate-500 uppercase dark:border-white/5 dark:bg-slate-900">
                          You
                        </span>
                      ) : perm.role === "pending" ? (
                        <span className="animate-pulse rounded-lg border border-amber-500/10 bg-amber-500/5 px-2.5 py-1.5 text-[9px] font-bold tracking-wider text-amber-500 uppercase">
                          Waiting
                        </span>
                      ) : isOwner ? (
                        <button
                          type="button"
                          disabled={savingPermissions}
                          onClick={() => void handleRemoveMember(perm.user_id, perm.user_email)}
                          className="cursor-pointer rounded-lg border border-red-500/20 bg-red-500/10 px-2.5 py-1.5 text-[10px] font-bold text-red-400 transition hover:bg-red-500/20"
                        >
                          Remove
                        </button>
                      ) : (
                        <span className="rounded-lg border border-emerald-500/10 bg-emerald-500/5 px-2.5 py-1.5 text-[9px] font-bold tracking-wider text-emerald-500 uppercase">
                          Connected
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 3. Expiry Settings (Self-Destruct) */}
            {isOwner && (
              <div className="border-foreground/10 space-y-3 border-t pt-2 dark:border-white/5">
                <h4 className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">
                  Self-Destruct Timer
                </h4>
                <div className="bg-foreground/[0.02] border-foreground/10 space-y-3 rounded-xl border p-4 dark:border-white/5 dark:bg-slate-950/45">
                  <p className="text-slate-550 text-[11px] leading-relaxed dark:text-slate-400">
                    Set message retention length. Expired messages are permanently wiped from all
                    client caches and database server records automatically.
                  </p>
                  <select
                    value={collection?.expiry_days || 0}
                    onChange={(e) => void handleUpdateExpiry(Number(e.target.value))}
                    className="w-full cursor-pointer rounded-xl border border-white/5 bg-slate-950 px-4 py-3 text-xs text-white transition outline-none focus:border-amber-500/30"
                  >
                    <option value={0}>∞ No Expiry (Default)</option>
                    <option value={1}>⏱ 1 Day</option>
                    <option value={7}>⏱ 7 Days</option>
                    <option value={30}>⏱ 30 Days</option>
                  </select>
                </div>
              </div>
            )}

            {/* 4. Encrypted Chat Backups */}
            <div className="border-foreground/10 space-y-3 border-t pt-2 dark:border-white/5">
              <h4 className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">
                Local E2EE Backups
              </h4>
              <div className="bg-foreground/[0.02] border-foreground/10 space-y-3 rounded-xl border p-4 dark:border-white/5 dark:bg-slate-950/45">
                <p className="text-slate-555 text-[11px] leading-relaxed dark:text-slate-400">
                  Export your decrypted local client database to a password-protected JSON backup,
                  or import a saved backup to restore your chat logs.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={handleExportBackup}
                    disabled={isExportingBackup}
                    className="bg-foreground/5 hover:bg-foreground/10 text-foreground border-foreground/10 w-full cursor-pointer rounded-xl border py-2.5 text-center text-[11px] font-bold shadow-none transition active:scale-95 dark:border-white/5"
                  >
                    {isExportingBackup ? "Exporting..." : "Export Backup"}
                  </button>
                  <button
                    type="button"
                    onClick={handleImportBackup}
                    disabled={isImportingBackup}
                    className="bg-foreground/5 hover:bg-foreground/10 text-foreground border-foreground/10 w-full cursor-pointer rounded-xl border py-2.5 text-center text-[11px] font-bold shadow-none transition active:scale-95 dark:border-white/5"
                  >
                    {isImportingBackup ? "Importing..." : "Import Backup"}
                  </button>
                </div>
              </div>
            </div>

            {/* 5. Danger Zone */}
            {isOwner && (
              <div className="space-y-3 border-t border-red-500/20 pt-2">
                <h4 className="text-[10px] font-bold tracking-widest text-red-500 uppercase">
                  Danger Zone
                </h4>
                <div className="space-y-3 rounded-xl border border-red-500/15 bg-red-500/5 p-4">
                  <p className="text-[11px] leading-relaxed text-red-400">
                    Permanently clear all E2EE messages, shared documents metadata, and decrypted
                    caches.
                  </p>
                  <button
                    type="button"
                    onClick={handleClearChatHistory}
                    className="w-full cursor-pointer rounded-xl border border-red-500/20 bg-red-600 py-3 text-center text-xs font-bold text-white transition hover:bg-red-500 active:scale-95"
                  >
                    Clear Chat History
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* E2EE Shield Details Modal */}
      <AnimatePresence>
        {showShieldModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowShieldModal(false)}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          >
            <motion.div
              initial={{ scale: 0.9, y: 15, opacity: 0 }}
              animate={{ scale: 1, y: 0, opacity: 1 }}
              exit={{ scale: 0.9, y: 15, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 350 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-background/95 border-foreground/10 relative w-full max-w-md overflow-hidden rounded-[1.8rem] border p-6 shadow-none backdrop-blur-md dark:border-white/5"
            >
              <div className="absolute top-0 right-0 left-0 h-1 bg-gradient-to-r from-emerald-500 via-teal-500 to-emerald-600" />
              <div className="flex flex-col items-center space-y-4 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-full border border-emerald-500/20 bg-emerald-500/10 text-emerald-500">
                  <ShieldCheck size={28} className="animate-pulse" />
                </div>
                <div className="space-y-1.5">
                  <h3 className="text-foreground text-center text-sm font-black tracking-widest uppercase">
                    Zero-Knowledge E2EE Bridge
                  </h3>
                  <p className="text-slate-550 text-center text-[11px] font-medium dark:text-slate-400">
                    Fully Secure End-to-End Cryptography Activated
                  </p>
                </div>

                <div className="bg-foreground/[0.02] border-foreground/5 w-full space-y-3 rounded-2xl border p-4 text-left text-[11px] leading-relaxed text-slate-500 dark:border-white/5">
                  <div className="flex items-start gap-2.5">
                    <span className="mt-0.5 text-xs text-emerald-500">🔑</span>
                    <p>
                      <strong className="text-foreground">PBKDF2 Key Derivation:</strong> Symmetric
                      keys are derived locally on your device using a combination of the collection
                      ID and connection keys.
                    </p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="mt-0.5 text-xs text-emerald-500">🔒</span>
                    <p>
                      <strong className="text-foreground">AES-GCM-256 Encryption:</strong> All
                      message texts and files are encrypted client-side using random 12-byte IVs
                      before transit.
                    </p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="mt-0.5 text-xs text-emerald-500">☁️</span>
                    <p>
                      <strong className="text-foreground">Zero Server Readability:</strong> The
                      central server storage only stores encrypted base64 ciphertexts. Your privacy
                      is 100% math-guaranteed.
                    </p>
                  </div>
                  {safetyNumber && (
                    <div className="border-foreground/5 mt-1 space-y-1.5 border-t pt-3 dark:border-white/5">
                      <p className="text-slate-555 text-[10px] font-bold tracking-wider uppercase dark:text-slate-400">
                        Safety Number Fingerprint:
                      </p>
                      <div className="bg-foreground/5 border-foreground/5 rounded-xl border px-3 py-2.5 text-center font-mono text-[10px] font-bold tracking-widest text-emerald-500 select-all dark:border-white/5 dark:bg-black/40">
                        {safetyNumber}
                      </div>
                      <p className="text-center text-[9px] leading-normal text-slate-500">
                        Compare this number with your peer to verify that no third party is
                        intercepting your communication.
                      </p>
                    </div>
                  )}
                </div>

                <button
                  onClick={() => setShowShieldModal(false)}
                  className="w-full cursor-pointer rounded-xl border border-emerald-500/10 bg-emerald-600 py-3 text-xs font-bold text-white transition hover:bg-emerald-500 active:scale-[0.98]"
                >
                  Understand & Close
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* E2EE Document & Media Preview Modal */}
      <AnimatePresence>
        {activePreviewFile && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setActivePreviewFile(null)}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md"
          >
            <motion.div
              initial={{ scale: 0.9, y: 20, opacity: 0 }}
              animate={{ scale: 1, y: 0, opacity: 1 }}
              exit={{ scale: 0.9, y: 20, opacity: 0 }}
              transition={{ type: "spring", damping: 28, stiffness: 300 }}
              onClick={(e) => e.stopPropagation()}
              className="relative flex h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-[1.8rem] border border-white/10 bg-slate-900/95 shadow-2xl backdrop-blur-xl"
            >
              {/* Top Bar */}
              <div className="flex shrink-0 items-center justify-between border-b border-white/10 bg-slate-950/20 px-6 py-4">
                <div className="min-w-0">
                  <h3 className="text-xs font-black tracking-widest text-slate-400 uppercase">
                    Secure File Preview
                  </h3>
                  <p className="mt-0.5 truncate text-[11px] font-bold text-white">
                    {activePreviewFile.filename}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <a
                    href={activePreviewFile.url}
                    download={activePreviewFile.filename}
                    className="flex cursor-pointer items-center gap-2 rounded-xl bg-emerald-600 px-3 py-1.5 text-[10px] font-bold tracking-wider text-white uppercase transition hover:bg-emerald-500"
                  >
                    Download
                  </a>
                  <button
                    onClick={() => setActivePreviewFile(null)}
                    className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg border border-white/10 bg-white/5 text-slate-400 transition hover:text-white"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>

              {/* Preview Viewport */}
              <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-slate-950/40 p-6">
                {(() => {
                  const { url, mimeType } = activePreviewFile;
                  const isImg = mimeType.startsWith("image/") || mimeType === "image/svg+xml";
                  const isAud = mimeType.startsWith("audio/");
                  const isPdf = mimeType === "application/pdf";

                  if (isImg) {
                    return (
                      <div className="flex max-h-full max-w-full items-center justify-center overflow-hidden rounded-xl border border-white/5">
                        <img
                          src={url}
                          alt={activePreviewFile.filename}
                          className="max-h-[60vh] max-w-full object-contain"
                        />
                      </div>
                    );
                  }

                  if (isAud) {
                    return (
                      <div className="flex w-full max-w-md flex-col items-center gap-4 rounded-2xl border border-white/10 bg-slate-900 p-6 text-center">
                        <div className="text-emerald-450 flex h-16 w-16 items-center justify-center rounded-full border border-emerald-500/25 bg-emerald-500/10">
                          <Volume2 size={32} className="animate-pulse" />
                        </div>
                        <div className="w-full">
                          <p className="text-[11px] font-black tracking-widest text-slate-400 uppercase">
                            Audio Playback
                          </p>
                          <p className="mt-1 truncate text-xs font-bold text-white">
                            {activePreviewFile.filename}
                          </p>
                        </div>
                        <audio controls src={url} className="mt-2 w-full" />
                      </div>
                    );
                  }

                  if (isPdf) {
                    return (
                      <iframe
                        src={url}
                        className="h-full w-full rounded-xl border border-white/10 bg-slate-900"
                      />
                    );
                  }

                  if (loadingText) {
                    return (
                      <div className="flex flex-col items-center gap-3">
                        <Paperclip size={24} className="animate-spin text-amber-500" />
                        <span className="text-[10px] font-bold tracking-wider text-slate-500 uppercase">
                          Decrypting File Data...
                        </span>
                      </div>
                    );
                  }

                  if (previewTextContent !== null) {
                    return (
                      <div className="text-slate-350 flex h-full w-full flex-col overflow-hidden rounded-xl border border-white/10 bg-slate-950 p-4 font-mono text-[10px]">
                        <pre className="flex-1 overflow-auto p-2 leading-relaxed whitespace-pre select-text">
                          {previewTextContent}
                        </pre>
                      </div>
                    );
                  }

                  // Generic document preview card
                  return (
                    <div className="flex w-full max-w-sm flex-col items-center space-y-4 rounded-3xl border border-white/10 bg-slate-900 p-6 text-center">
                      <div className="flex h-16 w-16 items-center justify-center rounded-full border border-amber-500/20 bg-amber-500/10 text-amber-500">
                        <FileIcon size={32} />
                      </div>
                      <div>
                        <h4 className="text-xs font-black tracking-wider text-slate-400 uppercase">
                          Secure Document Attachment
                        </h4>
                        <p className="text-slate-550 mt-1 text-[10px]">
                          This format is secure and cannot be rendered natively inside the browser
                          preview window.
                        </p>
                      </div>
                      <div className="w-full space-y-1 rounded-2xl border border-white/5 bg-slate-950/50 p-3 text-left">
                        <div className="flex justify-between text-[9px] font-bold">
                          <span className="text-slate-500 uppercase">Filename:</span>
                          <span className="text-slate-350 max-w-[12rem] truncate">
                            {activePreviewFile.filename}
                          </span>
                        </div>
                        <div className="flex justify-between text-[9px] font-bold">
                          <span className="text-slate-500 uppercase">Mime-type:</span>
                          <span className="text-slate-350">
                            {mimeType || "application/octet-stream"}
                          </span>
                        </div>
                      </div>
                      <a
                        href={url}
                        download={activePreviewFile.filename}
                        className="block w-full cursor-pointer rounded-xl bg-emerald-600 py-3 text-center text-xs font-bold text-white transition hover:bg-emerald-500"
                      >
                        Download Document
                      </a>
                    </div>
                  );
                })()}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SecureMediaRenderer({
  collectionId,
  msg,
  cryptoKey,
  onPreview,
}: {
  collectionId: string;
  msg: any;
  cryptoKey: CryptoKey | null;
  onPreview: (url: string, filename: string, mimeType: string) => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [decryptedFilename, setDecryptedFilename] = useState("Secure File");
  const [decryptedCaption, setDecryptedCaption] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    if (!cryptoKey || !msg.message) return;

    let objectUrl: string | null = null;
    const loadMedia = async () => {
      try {
        let decryptedText = msg.message;
        if (decryptedText.includes("ciphertext") && cryptoKey) {
          decryptedText = await decryptMessage(decryptedText, cryptoKey);
        }
        const metadata = JSON.parse(decryptedText);
        const { media_id, filename, mime_type, iv, caption } = metadata;

        if (isMounted) {
          setDecryptedFilename(filename);
          if (caption) {
            setDecryptedCaption(caption);
          }
        }

        const res = await fetchWithAuth(
          `/collections/${collectionId}/chats/media/${media_id}/${filename}`,
        );
        if (!res.ok) throw new Error("Fetch media failed");
        const buffer = await res.arrayBuffer();

        const decryptedBlob = await decryptFile(buffer, iv, mime_type, cryptoKey);
        const url = URL.createObjectURL(decryptedBlob);
        if (!isMounted) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        if (isMounted) {
          setBlobUrl(url);
          setLoading(false);
        }
      } catch (err) {
        console.error("Failed to decrypt/load media:", err);
        if (isMounted) {
          setError(true);
          setLoading(false);
        }
      }
    };

    void loadMedia();
    return () => {
      isMounted = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [collectionId, msg.message, cryptoKey]);

  if (loading) {
    return (
      <div className="bg-foreground/5 flex animate-pulse items-center gap-2 rounded-xl p-2">
        <Paperclip size={14} className="animate-spin text-amber-500" />
        <span className="text-[10px] text-slate-500">Decrypting media...</span>
      </div>
    );
  }

  if (error || !blobUrl) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 p-2">
        <Lock size={14} className="text-red-400" />
        <span className="text-[10px] text-red-400">Decryption failed</span>
      </div>
    );
  }

  const isImage =
    msg.media_mime_type?.startsWith("image/") || msg.media_mime_type === "image/svg+xml";
  const isAudio = msg.media_mime_type?.startsWith("audio/");

  if (isImage) {
    return (
      <div className="flex flex-col gap-1.5">
        <div
          onClick={() => onPreview(blobUrl, decryptedFilename, msg.media_mime_type || "image/png")}
          className="border-foreground/5 group relative cursor-pointer overflow-hidden rounded-lg border transition hover:opacity-90"
        >
          <img
            src={blobUrl}
            alt="Secure upload"
            className="max-h-[12rem] max-w-full object-cover"
          />
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition group-hover:opacity-100">
            <span className="text-[10px] font-bold tracking-wider text-white uppercase">
              Preview Image
            </span>
          </div>
        </div>
        {decryptedCaption && (
          <p className="text-foreground/90 text-[11px] leading-relaxed font-normal break-words whitespace-pre-wrap select-text">
            {decryptedCaption}
          </p>
        )}
      </div>
    );
  }

  if (isAudio) {
    return (
      <div className="flex flex-col gap-1.5">
        <div className="py-1">
          <WaveformAudioPlayer
            src={blobUrl}
            onPreviewClick={() =>
              onPreview(blobUrl, decryptedFilename, msg.media_mime_type || "audio/mp3")
            }
          />
        </div>
        {decryptedCaption && (
          <p className="text-foreground/90 text-[11px] leading-relaxed font-normal break-words whitespace-pre-wrap select-text">
            {decryptedCaption}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div
        onClick={() =>
          onPreview(blobUrl, decryptedFilename, msg.media_mime_type || "application/octet-stream")
        }
        className="bg-foreground/5 border-foreground/5 hover:bg-foreground/10 flex cursor-pointer items-center justify-between gap-2.5 rounded-xl border p-2.5 transition"
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <FileIcon size={16} className="shrink-0 text-amber-500" />
          <div className="min-w-0">
            <p className="text-foreground truncate text-[11px] font-semibold">
              {decryptedFilename}
            </p>
            <p className="mt-0.5 text-[9px] tracking-widest text-slate-500 uppercase">
              Secure Document
            </p>
          </div>
        </div>
        <span className="shrink-0 rounded-md bg-amber-500/10 px-2 py-0.5 text-[9px] font-bold text-amber-500 uppercase">
          Preview
        </span>
      </div>
      {decryptedCaption && (
        <p className="text-foreground/90 text-[11px] leading-relaxed font-normal break-words whitespace-pre-wrap select-text">
          {decryptedCaption}
        </p>
      )}
    </div>
  );
}

function WaveformAudioPlayer({ src, onPreviewClick }: { src: string; onPreviewClick: () => void }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const animationRef = useRef<number | null>(null);

  const peaks = useMemo(() => {
    return Array.from({ length: 40 }, (_, index) => 0.25 + ((index * 17) % 75) / 100);
  }, []);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch(console.error);
    }
  };

  const onTimeUpdate = () => {
    if (!audioRef.current) return;
    setCurrentTime(audioRef.current.currentTime);
  };

  const onLoadedMetadata = () => {
    if (!audioRef.current) return;
    setDuration(audioRef.current.duration);
  };

  const onAudioEnded = () => {
    setIsPlaying(false);
    setCurrentTime(0);
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const progress = duration > 0 ? currentTime / duration : 0;
      const barWidth = canvas.width / peaks.length;

      peaks.forEach((peak, i) => {
        const x = i * barWidth;
        const isPlayed = i / peaks.length <= progress;

        let scale = 1;
        if (isPlaying && Math.abs(i / peaks.length - progress) < 0.1) {
          scale = 1 + Math.sin(Date.now() * 0.015) * 0.2;
        }

        const barHeight = canvas.height * peak * scale * 0.8;
        const y = (canvas.height - barHeight) / 2;

        ctx.fillStyle = isPlayed ? "rgba(16, 185, 129, 0.95)" : "rgba(148, 163, 184, 0.3)";
        ctx.beginPath();
        ctx.roundRect(x + 1, y, barWidth - 2, barHeight, 2);
        ctx.fill();
      });

      if (isPlaying) {
        animationRef.current = requestAnimationFrame(draw);
      } else {
        peaks.forEach((peak, i) => {
          const x = i * barWidth;
          const isPlayed = i / peaks.length <= progress;
          const barHeight = canvas.height * peak * 0.8;
          const y = (canvas.height - barHeight) / 2;
          ctx.fillStyle = isPlayed ? "rgba(16, 185, 129, 0.95)" : "rgba(148, 163, 184, 0.3)";
          ctx.beginPath();
          ctx.roundRect(x + 1, y, barWidth - 2, barHeight, 2);
          ctx.fill();
        });
      }
    };

    draw();

    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [currentTime, duration, isPlaying, peaks]);

  return (
    <div className="bg-foreground/[0.03] border-foreground/5 flex max-w-[18rem] min-w-[15rem] items-center gap-3 rounded-2xl border p-3 dark:border-white/5 dark:bg-slate-950/40">
      <audio
        ref={audioRef}
        src={src}
        onTimeUpdate={onTimeUpdate}
        onLoadedMetadata={onLoadedMetadata}
        onEnded={onAudioEnded}
        className="hidden"
      />
      <div className="flex shrink-0 flex-col gap-2">
        <button
          type="button"
          onClick={togglePlay}
          className="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full bg-emerald-500 text-slate-950 transition hover:bg-emerald-400 active:scale-95"
        >
          {isPlaying ? (
            <Pause size={12} className="fill-current text-slate-950" />
          ) : (
            <Play size={12} className="ml-0.5 fill-current text-slate-950" />
          )}
        </button>
        <button
          type="button"
          onClick={onPreviewClick}
          className="bg-foreground/5 border-foreground/10 text-foreground hover:bg-foreground/10 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full border text-[9px] font-black transition active:scale-95"
        >
          Open
        </button>
      </div>
      <div className="min-w-0 flex-1">
        <canvas ref={canvasRef} width={160} height={36} className="block h-9 w-full" />
        <div className="mt-1 flex items-center justify-between px-1 text-[8px] font-bold tracking-wider text-slate-500 uppercase">
          <span>{formatTime(currentTime)}</span>
          <span>{formatTime(duration)}</span>
        </div>
      </div>
    </div>
  );
}

function formatTime(secs: number): string {
  if (isNaN(secs)) return "0:00";
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}
