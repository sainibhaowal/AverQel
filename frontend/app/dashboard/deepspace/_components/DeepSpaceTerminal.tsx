"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  Terminal as TerminalIcon,
  Play,
  Square,
  Trash2,
  Clock,
  CheckCircle2,
  XCircle,
  ArrowUpRight,
  Plus,
  MoreHorizontal,
  ChevronDown,
  Columns2,
  Bot,
  X,
  AlertTriangle,
  Info,
  ExternalLink,
  Keyboard,
  ListFilter,
  RefreshCw
} from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";
import { isTauriEnvironment } from "@/lib/tauri";
import toast from "react-hot-toast";

/**
 * Execute a shell command on the local PC using the Tauri shell plugin.
 * Returns { output, exit_code, cwd }.
 */
async function localShellExecute(
  command: string,
  cwd: string
): Promise<{ output: string; exit_code: number; cwd: string }> {
  try {
    // Tauri v2 shell plugin: dynamic import to avoid SSR issues
    const { Command } = await import("@tauri-apps/plugin-shell");
    // Run command via bash -c so pipes, env vars etc work
    const cmd = Command.create("bash", ["-c", command], { cwd });
    const result = await cmd.execute();
    const output = (result.stdout || "") + (result.stderr ? `\n${result.stderr}` : "");
    return { output, exit_code: result.code ?? 0, cwd };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return { output: `Error executing command locally: ${msg}`, exit_code: 1, cwd };
  }
}

interface DeepSpaceTerminalProps {
  activeFolderPath?: string;
  activeFilePath?: string;
  onClose?: () => void;
  onRefreshWorkspace?: () => void;
}

interface CommandLog {
  id: string;
  command: string;
  timestamp: string;
  status: "running" | "finished" | "killed" | "failed";
  exitCode?: number;
}

interface PhaseState {
  potential_energy: number;
  kinetic_energy: number;
  total_energy: number;
  entropy: number;
  coordinate_q: number;
  coordinate_p: number;
}

interface SplitPane {
  id: string;
  name: string;
  type: "user" | "averqel";
  pid?: number;
  commandLine?: string;
  activeVenv?: string;
  cwd: string;
  outputLines: Array<{ text: string; stream: "stdout" | "stderr" | "system" }>;
  isConnected: boolean;
  isRunning: boolean;
  inputVal: string;
  prediction: string;
  probability: number;
  phaseState?: PhaseState;
  commandHistory: CommandLog[];
  enteredCommands: string[];
  historyIndex: number;
}

interface TerminalGroup {
  id: string;
  panes: SplitPane[];
}

export default function DeepSpaceTerminal({
  activeFolderPath,
  activeFilePath,
  onClose,
  onRefreshWorkspace
}: DeepSpaceTerminalProps) {

  const [groups, setGroups] = useState<TerminalGroup[]>(() => [
    {
      id: "group-averqel",
      panes: [
        {
          id: "averqel",
          name: "AverQel",
          type: "averqel",
          cwd: "/workspace",
          outputLines: [
            { text: "AverQel DeepSpace Live Agent Console v2.0", stream: "system" },
            { text: "Connected and listening to agentic workflows... 1:1 synced.\n", stream: "system" }
          ],
          isConnected: false,
          isRunning: false,
          inputVal: "",
          prediction: "",
          probability: 0.0,
          commandHistory: [],
          enteredCommands: [],
          historyIndex: -1
        }
      ]
    },
    {
      id: "group-default",
      panes: [
        {
          id: "default",
          name: "bash",
          type: "user",
          cwd: "/workspace",
          outputLines: [
            { text: "AverQel DeepSpace Terminal Sandbox v2.0", stream: "system" },
            { text: "Connected to host environment.\n", stream: "system" }
          ],
          isConnected: false,
          isRunning: false,
          inputVal: "",
          prediction: "",
          probability: 0.0,
          commandHistory: [],
          enteredCommands: [],
          historyIndex: -1
        }
      ]
    }
  ]);

  const [activeGroupId, setActiveGroupId] = useState<string>("group-default");
  const [focusedPaneId, setFocusedPaneId] = useState<string>("default");
  const [activeTab, setActiveTab] = useState<"terminal" | "history">("terminal");
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [showActionMenu, setShowActionMenu] = useState(false);
  const [showPidPopoverId, setShowPidPopoverId] = useState<string | null>(null);

  const socketsRef = useRef<Record<string, WebSocket>>({});
  const inputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const scrollContainersRef = useRef<Record<string, HTMLDivElement | null>>({});
  const terminalIdRef = useRef(0);

  const activeGroup = groups.find((g) => g.id === activeGroupId) || groups[0];
  const focusedPane = activeGroup.panes.find((p) => p.id === focusedPaneId) || activeGroup.panes[0];

  const appendOutput = useCallback((paneId: string, text: string, stream: "stdout" | "stderr" | "system") => {
    setGroups((prev) =>
      prev.map((g) => ({
        ...g,
        panes: g.panes.map((p) => {
          if (p.id !== paneId) return p;
          return {
            ...p,
            outputLines: [...p.outputLines, { text, stream }]
          };
        })
      }))
    );
  }, []);

  const updatePane = useCallback((paneId: string, fields: Partial<SplitPane>) => {
    setGroups((prev) =>
      prev.map((g) => ({
        ...g,
        panes: g.panes.map((p) => (p.id === paneId ? { ...p, ...fields } : p))
      }))
    );
  }, []);

  const connectPane = useCallback((paneId: string) => {
    if (socketsRef.current[paneId]) {
      try {
        socketsRef.current[paneId].close();
      } catch (e) {}
    }

    const token = localStorage.getItem("averqel_token") || "";
    const tenantId = localStorage.getItem("averqel_tenant_id") || "";
    const apiBase = getApiBaseUrl().replace(/\/+$/, "");

    let wsUrl = "";
    try {
      const url = new URL(`${apiBase}/workspace/terminal/ws`, window.location.origin);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      url.searchParams.set("token", token);
      url.searchParams.set("session_id", paneId);
      if (tenantId) {
        url.searchParams.set("tenant_id", tenantId);
      }
      wsUrl = url.toString();
    } catch (e) {
      console.error("Failed to build WS url", e);
      return;
    }

    const ws = new WebSocket(wsUrl);
    socketsRef.current[paneId] = ws;

    ws.onopen = () => {
      updatePane(paneId, { isConnected: true });
      // If running inside Tauri desktop, announce ourselves so the VPS
      // backend routes all shell commands to this local PC instead of
      // its own sandbox container.
      if (isTauriEnvironment()) {
        ws.send(JSON.stringify({ event: "client_register", client: "tauri" }));
      }
      if (activeFolderPath) {
        ws.send(JSON.stringify({ action: "cd", path: activeFolderPath }));
      }
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const { event: evType, data } = payload;

        // ── Local PC execution via Tauri ──────────────────────────────────
        // The VPS backend sends an rpc_request with method "shell.execute"
        // when it wants to run a command on the user's local machine.
        if (evType === "rpc_request" && payload.method === "shell.execute") {
          const { id: rpcId, params } = payload;
          const cmd = String(params?.command ?? "");
          const cwd = String(params?.cwd ?? ".");
          localShellExecute(cmd, cwd).then((result) => {
            ws.send(JSON.stringify({
              event: "rpc_response",
              id: rpcId,
              result,
            }));
          });
          return;
        }

        // ── Acknowledgement that we are registered as local client ────────
        if (evType === "client_registered") {
          appendOutput(paneId, "[AverQel] Local PC terminal active — commands run on your machine.\n", "system");
          return;
        }

        if (evType === "connected") {
          updatePane(paneId, {
            cwd: data.cwd || "/workspace",
            pid: data.pid,
            commandLine: data.command_line,
            name: data.session_name || "bash",
            activeVenv: data.active_venv || undefined
          });
        } else if (evType === "output") {
          appendOutput(paneId, data.text, data.stream || "stdout");
        } else if (evType === "prediction") {
          updatePane(paneId, {
            prediction: data.prediction || "",
            probability: data.probability || 0.0,
            phaseState: data.phase_state
          });
        } else if (evType === "status") {
          if (data.status === "running") {
            updatePane(paneId, { isRunning: true, prediction: "", probability: 0.0 });
            setGroups((prev) =>
              prev.map((g) => ({
                ...g,
                panes: g.panes.map((p) => {
                  if (p.id !== paneId) return p;
                  const exists = p.commandHistory.some((h) => h.command === data.command);
                  if (exists) return p;
                  const newHistory: CommandLog = {
                    id: `${Date.now()}-${Math.random()}`,
                    command: data.command,
                    timestamp: new Date().toLocaleTimeString(),
                    status: "running"
                  };
                  return {
                    ...p,
                    commandHistory: [newHistory, ...p.commandHistory]
                  };
                })
              }))
            );
          } else if (data.status === "finished") {
            updatePane(paneId, {
              isRunning: false,
              cwd: data.cwd || "/workspace",
              activeVenv: data.active_venv || undefined
            });
            if (onRefreshWorkspace) onRefreshWorkspace();
            setGroups((prev) =>
              prev.map((g) => ({
                ...g,
                panes: g.panes.map((p) => {
                  if (p.id !== paneId) return p;
                  return {
                    ...p,
                    commandHistory: p.commandHistory.map((h) =>
                      h.status === "running"
                        ? {
                            ...h,
                            status: data.exit_code === 0 ? "finished" : "failed",
                            exitCode: data.exit_code
                          }
                        : h
                    )
                  };
                })
              }))
            );
          } else if (data.status === "killed") {
            updatePane(paneId, { isRunning: false });
            setGroups((prev) =>
              prev.map((g) => ({
                ...g,
                panes: g.panes.map((p) => {
                  if (p.id !== paneId) return p;
                  return {
                    ...p,
                    commandHistory: p.commandHistory.map((h) =>
                      h.status === "running" ? { ...h, status: "killed" } : h
                    )
                  };
                })
              }))
            );
          }
        }
      } catch (err) {
        console.error("Failed to parse socket message", err);
      }
    };

    ws.onerror = () => {
      appendOutput(paneId, "\nConnection error occurred.", "stderr");
    };

    ws.onclose = () => {
      updatePane(paneId, { isConnected: false, isRunning: false });
      appendOutput(paneId, "\nTerminal disconnected.", "system");
    };
  }, [activeFolderPath, appendOutput, updatePane, onRefreshWorkspace]);

  useEffect(() => {
    groups.forEach((g) => {
      g.panes.forEach((p) => {
        connectPane(p.id);
      });
    });

    return () => {
      Object.values(socketsRef.current).forEach((ws) => {
        try {
          ws.close();
        } catch (e) {}
      });
      socketsRef.current = {};
    };
  }, []);

  useEffect(() => {
    if (activeFolderPath) {
      Object.entries(socketsRef.current).forEach(([pid, ws]) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: "cd", path: activeFolderPath }));
        }
      });
    }
  }, [activeFolderPath]);

  useEffect(() => {
    activeGroup.panes.forEach((p) => {
      const container = scrollContainersRef.current[p.id];
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    });
  }, [activeGroup.panes]);

  const handleRunCommand = (cmdText: string) => {
    const ws = socketsRef.current[focusedPaneId];
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      toast.error("Focused terminal session is not connected");
      return;
    }
    const cleanCmd = cmdText.trim();
    if (!cleanCmd) return;

    const activePane = activeGroup.panes.find((p) => p.id === focusedPaneId);
    if (activePane) {
      const venvPrefix = activePane.activeVenv ? `(${activePane.activeVenv}) ` : "";
      const echoLine = `${venvPrefix}ravi@averqel:${activePane.cwd.replace("/workspace", "~")}$ ${cleanCmd}`;
      appendOutput(focusedPaneId, echoLine + "\n", "stdout");
    }

    ws.send(JSON.stringify({ action: "execute", command: cleanCmd }));

    setGroups((prev) =>
      prev.map((g) => ({
        ...g,
        panes: g.panes.map((p) => {
          if (p.id !== focusedPaneId) return p;
          const next = p.enteredCommands.filter((c) => c !== cleanCmd);
          return {
            ...p,
            enteredCommands: [...next, cleanCmd],
            historyIndex: -1,
            inputVal: "",
            prediction: "",
            probability: 0.0
          };
        })
      }))
    );
  };

  const handleKillCommand = (paneId: string) => {
    const ws = socketsRef.current[paneId];
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: "kill" }));
    }
  };

  const handleCreateTerminalTab = (type: "user" | "averqel" = "user") => {
    terminalIdRef.current += 1;
    const newPaneId = `pane-${terminalIdRef.current}`;
    const newGroupId = `group-${terminalIdRef.current}`;
    const newGroup: TerminalGroup = {
      id: newGroupId,
      panes: [
        {
          id: newPaneId,
          name: type === "averqel" ? "AverQel" : "bash",
          type,
          cwd: focusedPane.cwd,
          outputLines: [
            { text: `New ${type === "averqel" ? "AverQel" : "bash"} session initialized.\n`, stream: "system" }
          ],
          isConnected: false,
          isRunning: false,
          inputVal: "",
          prediction: "",
          probability: 0.0,
          commandHistory: [],
          enteredCommands: [],
          historyIndex: -1
        }
      ]
    };

    setGroups((prev) => [...prev, newGroup]);
    setActiveGroupId(newGroupId);
    setFocusedPaneId(newPaneId);
    connectPane(newPaneId);
    toast.success(`Created new ${type === "averqel" ? "AverQel" : "bash"} tab`);
  };

  const handleSplitTerminalPane = (paneId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();

    const parentGroup = groups.find((g) => g.panes.some((p) => p.id === paneId));
    if (!parentGroup) return;

    const sourcePane = parentGroup.panes.find((p) => p.id === paneId)!;
    terminalIdRef.current += 1;
    const newPaneId = `pane-${terminalIdRef.current}`;
    const newPane: SplitPane = {
      id: newPaneId,
      name: sourcePane.type === "averqel" ? "AverQel" : "bash",
      type: sourcePane.type,
      cwd: sourcePane.cwd,
      outputLines: [
        { text: `Split shell session initialized.\n`, stream: "system" }
      ],
      isConnected: false,
      isRunning: false,
      inputVal: "",
      prediction: "",
      probability: 0.0,
      commandHistory: [],
      enteredCommands: [],
      historyIndex: -1
    };

    setGroups((prev) =>
      prev.map((g) => {
        if (g.id !== parentGroup.id) return g;
        return {
          ...g,
          panes: [...g.panes, newPane]
        };
      })
    );

    setActiveGroupId(parentGroup.id);
    setFocusedPaneId(newPaneId);
    connectPane(newPaneId);
    toast.success("Split terminal side-by-side");
  };

  const handleDeleteTerminalPane = (paneId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();

    const parentGroup = groups.find((g) => g.panes.some((p) => p.id === paneId));
    if (!parentGroup) return;

    const ws = socketsRef.current[paneId];
    if (ws) {
      try {
        ws.close();
      } catch (err) {}
      delete socketsRef.current[paneId];
    }

    const totalPanes = groups.reduce((acc, g) => acc + g.panes.length, 0);
    if (totalPanes <= 1) {
      toast.error("Cannot close the last terminal session");
      return;
    }

    if (parentGroup.panes.length > 1) {
      setGroups((prev) =>
        prev.map((g) => {
          if (g.id !== parentGroup.id) return g;
          return {
            ...g,
            panes: g.panes.filter((p) => p.id !== paneId)
          };
        })
      );
      if (focusedPaneId === paneId) {
        const remaining = parentGroup.panes.filter((p) => p.id !== paneId);
        setFocusedPaneId(remaining[remaining.length - 1].id);
      }
    } else {
      setGroups((prev) => prev.filter((g) => g.id !== parentGroup.id));
      const remainingGroups = groups.filter((g) => g.id !== parentGroup.id);
      const targetGroup = remainingGroups[remainingGroups.length - 1];
      setActiveGroupId(targetGroup.id);
      setFocusedPaneId(targetGroup.panes[targetGroup.panes.length - 1].id);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, paneId: string) => {
    const p = activeGroup.panes.find((p) => p.id === paneId)!;

    if ((e.key === "Tab" || e.key === "ArrowRight") && p.prediction) {
      e.preventDefault();
      const completed = p.inputVal + p.prediction;
      updatePane(paneId, {
        inputVal: completed,
        prediction: ""
      });
      const ws = socketsRef.current[paneId];
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "typing", input: completed, cwd: p.cwd }));
      }
      return;
    }

    if (e.key === "Enter") {
      handleRunCommand(p.inputVal);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (p.enteredCommands.length === 0) return;
      const nextIdx = p.historyIndex === -1 ? p.enteredCommands.length - 1 : p.historyIndex - 1;
      if (nextIdx >= 0) {
        updatePane(paneId, {
          historyIndex: nextIdx,
          inputVal: p.enteredCommands[nextIdx],
          prediction: "",
          probability: 0.0
        });
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIdx = p.historyIndex === -1 ? -1 : p.historyIndex + 1;
      if (nextIdx >= 0 && nextIdx < p.enteredCommands.length) {
        updatePane(paneId, {
          historyIndex: nextIdx,
          inputVal: p.enteredCommands[nextIdx],
          prediction: "",
          probability: 0.0
        });
      } else {
        updatePane(paneId, {
          historyIndex: -1,
          inputVal: "",
          prediction: "",
          probability: 0.0
        });
      }
    }
  };

  const handleInputChange = (paneId: string, value: string) => {
    updatePane(paneId, { inputVal: value });

    const ws = socketsRef.current[paneId];
    const p = activeGroup.panes.find((pane) => pane.id === paneId);
    if (ws && ws.readyState === WebSocket.OPEN && p) {
      ws.send(JSON.stringify({
        action: "typing",
        input: value,
        cwd: p.cwd
      }));
    }
  };

  const handleRunActiveFile = () => {
    if (!activeFilePath) {
      toast.error("No active file open in the editor");
      return;
    }
    const ext = activeFilePath.split(".").pop();
    let runnerCmd = "";
    if (ext === "py") {
      runnerCmd = `python3 "${activeFilePath}"`;
    } else if (["js", "ts", "jsx", "tsx"].includes(ext || "")) {
      runnerCmd = `node "${activeFilePath}"`;
    } else if (ext === "sh") {
      runnerCmd = `bash "${activeFilePath}"`;
    } else {
      runnerCmd = `cat "${activeFilePath}"`;
    }
    handleRunCommand(runnerCmd);
    setShowActionMenu(false);
    toast.success(`Running active file: ${activeFilePath.split("/").pop()}`);
  };

  const handleRunSelectedText = () => {
    const selected = window.getSelection()?.toString().trim();
    if (!selected) {
      toast.error("No text selected in workspace to run");
      return;
    }
    handleRunCommand(selected);
    setShowActionMenu(false);
    toast.success("Running selected text in focused terminal");
  };

  const handleClearTerminal = () => {
    updatePane(focusedPaneId, { outputLines: [] });
    setShowActionMenu(false);
  };

  return (
    <div className="flex h-full w-full flex-col bg-[#050508]/85 backdrop-blur-md border border-white/10 rounded-xl overflow-hidden font-mono text-xs select-none shadow-[0_12px_40px_rgba(0,0,0,0.65)] relative">

      {/* Header controls toolbar */}
      <div className="flex h-10 items-center justify-between border-b border-white/10 bg-gradient-to-r from-black/60 to-[#0b0b0e]/70 px-3 select-none flex-shrink-0">

        {/* Tab switcher */}
        <div className="flex items-center gap-1.5 bg-black/45 p-1 rounded-full border border-white/5">
          <button
            onClick={() => setActiveTab("terminal")}
            className={`flex h-6.5 items-center gap-1.5 px-3.5 rounded-full text-[9.5px] font-bold tracking-wider uppercase transition-all duration-300 ${
              activeTab === "terminal"
                ? "bg-primary/15 border border-primary/35 text-primary shadow-[0_2px_8px_rgba(var(--color-primary-rgb),0.15)]"
                : "border border-transparent text-foreground/45 hover:text-foreground/75 hover:bg-white/5"
            }`}
          >
            <TerminalIcon size={11} className={activeTab === "terminal" ? "text-primary" : "text-foreground/40"} />
            <span>Terminal</span>
            {groups.some((g) => g.panes.some((p) => p.isRunning)) && (
              <span className="flex h-1.5 w-1.5 rounded-full bg-emerald-450 animate-pulse shadow-[0_0_6px_rgba(16,185,129,0.7)]" />
            )}
          </button>

          <button
            onClick={() => setActiveTab("history")}
            className={`flex h-6.5 items-center gap-1.5 px-3.5 rounded-full text-[9.5px] font-bold tracking-wider uppercase transition-all duration-300 ${
              activeTab === "history"
                ? "bg-primary/15 border border-primary/35 text-primary shadow-[0_2px_8px_rgba(var(--color-primary-rgb),0.15)]"
                : "border border-transparent text-foreground/45 hover:text-foreground/75 hover:bg-white/5"
            }`}
          >
            <Clock size={11} className={activeTab === "history" ? "text-primary" : "text-foreground/40"} />
            <span>History</span>
          </button>
        </div>

        {/* Global Toolbar buttons */}
        <div className="flex items-center gap-3">

          {/* Active CWD info */}
          <div className="hidden sm:flex items-center gap-2 rounded-full border border-white/5 bg-white/[0.02] px-2.5 py-0.5 text-[8.5px] font-bold uppercase tracking-wider text-foreground/45">
            <span className={`h-1.5 w-1.5 rounded-full ${focusedPane.isConnected ? "bg-emerald-450 animate-pulse shadow-[0_0_4px_rgba(16,185,129,0.7)]" : "bg-red-450 shadow-[0_0_4px_rgba(239,68,68,0.7)]"}`} />
            <span className="truncate max-w-[120px] font-mono">{focusedPane.cwd.split("/").pop() || "root"}</span>
          </div>

          <div className="h-4 w-px bg-white/10" />

          {/* Action buttons */}
          <div className="flex items-center gap-1.5">
            {focusedPane.isRunning ? (
              <button
                onClick={() => handleKillCommand(focusedPaneId)}
                title="Cancel running command (Ctrl+C)"
                className="flex h-6 items-center gap-1.5 rounded-full border border-red-500/35 bg-gradient-to-r from-red-500/20 to-red-650/10 px-3 py-0.5 text-[8.5px] font-bold tracking-wider text-red-450 uppercase hover:from-red-500/30 hover:to-red-500/15 transition-all shadow-sm"
              >
                <Square size={9} fill="currentColor" className="text-red-400" />
                <span>Kill</span>
              </button>
            ) : (
              <button
                disabled={!focusedPane.inputVal.trim()}
                onClick={() => handleRunCommand(focusedPane.inputVal)}
                title="Run entered command"
                className="flex h-6 items-center gap-1.5 rounded-full border border-primary/35 bg-gradient-to-r from-primary/20 to-primary/10 px-3 py-0.5 text-[8.5px] font-bold tracking-wider text-primary uppercase hover:from-primary/30 hover:to-primary/15 transition-all shadow-sm disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <Play size={9} fill="currentColor" className="text-primary" />
                <span>Run</span>
              </button>
            )}

            {/* Plus New Terminal Dropdown */}
            <div className="relative">
              <button
                onClick={() => setShowAddMenu(!showAddMenu)}
                title="Add new terminal session"
                className="flex items-center gap-0.5 p-1 text-foreground/45 hover:text-foreground/80 hover:bg-white/5 rounded-lg border border-transparent hover:border-white/5 transition"
              >
                <Plus size={13} />
                <ChevronDown size={10} />
              </button>
              {showAddMenu && (
                <div className="absolute right-0 top-full mt-2.5 z-[1000] w-48 rounded-xl border border-white/10 bg-[#07070a]/95 backdrop-blur-md p-1.5 shadow-2xl animate-in fade-in slide-in-from-top-1 duration-150">
                  <button
                    onClick={() => {
                      handleCreateTerminalTab("user");
                      setShowAddMenu(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-foreground/75 hover:bg-white/5 hover:text-primary transition"
                  >
                    <TerminalIcon size={12} />
                    <span>New Terminal</span>
                  </button>
                  <button
                    onClick={() => {
                      handleSplitTerminalPane(focusedPaneId);
                      setShowAddMenu(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-foreground/75 hover:bg-white/5 hover:text-primary transition"
                  >
                    <Columns2 size={12} />
                    <span>Split Terminal</span>
                  </button>
                </div>
              )}
            </div>

            {/* Three-Dot Menu Options */}
            <div className="relative">
              <button
                onClick={() => setShowActionMenu(!showActionMenu)}
                title="Terminal Actions"
                className="p-1 text-foreground/45 hover:text-foreground/80 hover:bg-white/5 rounded-lg border border-transparent hover:border-white/5 transition"
              >
                <MoreHorizontal size={13} />
              </button>
              {showActionMenu && (
                <div className="absolute right-0 top-full mt-2.5 z-[1000] w-56 rounded-xl border border-white/10 bg-[#07070a]/95 backdrop-blur-md p-1.5 shadow-2xl animate-in fade-in slide-in-from-top-1 duration-150">

                  <button
                    onClick={handleRunActiveFile}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-foreground/75 hover:bg-white/5 hover:text-primary transition"
                  >
                    <Play size={12} className="text-primary/70" />
                    <span>Run Active File</span>
                  </button>

                  <button
                    onClick={handleRunSelectedText}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-foreground/75 hover:bg-white/5 hover:text-primary transition"
                  >
                    <Keyboard size={12} className="text-primary/70" />
                    <span>Run Selected Text</span>
                  </button>

                  <button
                    onClick={handleClearTerminal}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-foreground/75 hover:bg-white/5 hover:text-primary transition"
                  >
                    <Trash2 size={12} className="text-red-400/70" />
                    <span>Clear Terminal</span>
                  </button>

                  <div className="my-1 border-t border-white/5" />

                  <button
                    onClick={() => {
                      appendOutput(focusedPaneId, "\nDictation feature integration pending...\n", "system");
                      setShowActionMenu(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-foreground/30 cursor-not-allowed"
                  >
                    <span>Start Dictation</span>
                  </button>

                  <button
                    onClick={() => {
                      if (activeFolderPath) {
                        appendOutput(focusedPaneId, `\nRecent directories:\n- ${activeFolderPath}\n- /home/ravi\n- /workspace\n`, "system");
                      }
                      setShowActionMenu(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-foreground/75 hover:bg-white/5 hover:text-primary transition"
                  >
                    <ListFilter size={12} />
                    <span>Go to Recent Directory...</span>
                  </button>
                </div>
              )}
            </div>

            {onClose && (
              <button
                onClick={onClose}
                title="Close terminal panel"
                className="text-foreground/45 hover:text-foreground/80 hover:bg-white/10 p-1.5 rounded-lg border border-transparent hover:border-white/5 transition"
              >
                <X size={12} />
              </button>
            )}
          </div>

        </div>
      </div>

      {/* Main split display area */}
      <div className="flex-1 flex min-h-0 overflow-hidden relative">

        {/* PID details popover overlay */}
        {showPidPopoverId && (
          <div className="absolute top-3 right-32 z-[999] w-72 rounded-xl border border-white/10 bg-[#08080a]/95 backdrop-blur-md p-4 shadow-2xl select-text animate-in fade-in scale-in duration-150">
            <div className="flex justify-between items-start mb-2.5">
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-primary">Process Info</h4>
              <button
                onClick={() => setShowPidPopoverId(null)}
                className="text-foreground/40 hover:text-foreground p-0.5 rounded"
              >
                <X size={12} />
              </button>
            </div>
            <div className="space-y-2 text-[10px]">
              <div>
                <span className="text-foreground/35 block uppercase font-black">Process Name</span>
                <span className="font-semibold text-foreground/80">bash</span>
              </div>
              <div>
                <span className="text-foreground/35 block uppercase font-black">Process ID (PID)</span>
                <span className="font-mono text-foreground font-bold">
                  {groups.flatMap((g) => g.panes).find((p) => p.id === showPidPopoverId)?.pid || "Unknown"}
                </span>
              </div>
              <div>
                <span className="text-foreground/35 block uppercase font-black">Command Line</span>
                <span className="font-mono text-foreground/60 break-all leading-normal select-all bg-black/40 border border-white/5 p-1 rounded">
                  {groups.flatMap((g) => g.panes).find((p) => p.id === showPidPopoverId)?.commandLine || "bash"}
                </span>
              </div>
              <div>
                <span className="text-foreground/35 block uppercase font-black">Shell Integration</span>
                <span className="font-semibold text-emerald-450">Rich</span>
              </div>

              <div className="pt-2 border-t border-white/5 flex gap-3 text-[9px] font-bold uppercase text-primary tracking-wider">
                <button onClick={() => toast.success("Environment analysis updated")} className="hover:underline flex items-center gap-1">
                  <span>Env Contributions</span>
                  <ExternalLink size={8} />
                </button>
                <button onClick={() => toast.success("Process diagnostics generated")} className="hover:underline">
                  <span>Details</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Left Side: Active terminal splits rendered side-by-side as elegant card elements */}
        <div className="flex-1 flex flex-row divide-x divide-white/5 min-w-0 bg-[#050507]/20 h-full overflow-x-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-white/10 hover:[&::-webkit-scrollbar-thumb]:bg-white/20 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-track]:bg-transparent">
          {activeTab === "terminal" ? (
            activeGroup.panes.map((pane) => {
              const isFocused = pane.id === focusedPaneId;
              return (
                <div
                  key={pane.id}
                  onClick={() => {
                    setFocusedPaneId(pane.id);
                    setTimeout(() => inputRefs.current[pane.id]?.focus(), 25);
                  }}
                  className={`flex-1 min-w-[200px] flex flex-col h-full transition relative cursor-text p-2 ${
                    isFocused ? "opacity-100" : "opacity-45 hover:opacity-75"
                  }`}
                >
                  <div className={`flex-1 flex flex-col h-full rounded-xl border transition-all duration-300 overflow-hidden bg-black/40 ${
                    isFocused
                      ? "border-primary/30 ring-1 ring-primary/10 shadow-[inset_0_1px_8px_rgba(var(--color-primary-rgb),0.1)]"
                      : "border-white/5 shadow-inner"
                  }`}>

                    {/* Header line of the active card */}
                    <div className={`flex h-7 items-center justify-between border-b border-white/5 px-3 py-1 select-none flex-shrink-0 bg-gradient-to-r ${
                      isFocused ? "from-primary/5 to-transparent" : "from-white/[0.01] to-transparent"
                    }`}>
                      <div className="flex items-center gap-1.5">
                        <span className={`text-[9px] font-black uppercase tracking-wider ${isFocused ? "text-primary" : "text-foreground/45"}`}>
                          {pane.name} {pane.isRunning && "●"}
                        </span>
                        {pane.probability > 0 && (
                          <span className="text-[7.5px] bg-primary/15 border border-primary/20 text-primary px-1.5 py-0.2 rounded font-black tracking-widest uppercase">
                            V-STATE {Math.round(pane.probability * 100)}%
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={(e) => handleSplitTerminalPane(pane.id, e)}
                          title="Split terminal side-by-side"
                          className="text-foreground/30 hover:text-foreground transition p-0.5 rounded hover:bg-white/5"
                        >
                          <Columns2 size={9.5} />
                        </button>
                        <button
                          onClick={(e) => handleDeleteTerminalPane(pane.id, e)}
                          title="Close pane"
                          className="text-foreground/30 hover:text-red-400 transition p-0.5 rounded hover:bg-white/5"
                        >
                          <X size={9.5} />
                        </button>
                      </div>
                    </div>

                    {/* Output and inline input panel */}
                    <div
                      ref={(el) => {
                        scrollContainersRef.current[pane.id] = el;
                      }}
                      className="flex-1 min-h-0 overflow-y-auto p-3 select-text font-mono text-[11px] leading-relaxed relative [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-white/5 hover:[&::-webkit-scrollbar-thumb]:bg-white/15 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-track]:bg-transparent"
                    >
                      {/* outputs */}
                      {pane.outputLines.map((line, idx) => {
                        let textClass = "text-foreground/80";
                        if (line.stream === "stderr") {
                          textClass = "text-red-400/90 font-medium";
                        } else if (line.stream === "system") {
                          textClass = "text-cyan-400 font-semibold italic";
                        }
                        return (
                          <div key={idx} className={`${textClass} whitespace-pre-wrap break-all`}>
                            {line.text}
                          </div>
                        );
                      })}

                      {/* Hidden text listener */}
                      <input
                        ref={(el) => {
                          inputRefs.current[pane.id] = el;
                        }}
                        type="text"
                        value={pane.inputVal}
                        onChange={(e) => handleInputChange(pane.id, e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, pane.id)}
                        onFocus={() => setFocusedPaneId(pane.id)}
                        disabled={!pane.isConnected || pane.isRunning}
                        className="absolute opacity-0 pointer-events-none w-0 h-0 border-none outline-none"
                      />

                      {/* Terminal inline input line */}
                      {pane.isConnected && (
                        <div className="flex flex-wrap items-center mt-1 select-none text-[11px] leading-relaxed">
                          {pane.type === "averqel" && (
                            <div className="mr-1.5 flex items-center gap-1 rounded bg-primary/20 px-1.5 py-0.2 text-[8px] font-black uppercase text-primary tracking-widest border border-primary/25 animate-pulse shadow-sm">
                              <Bot size={9} />
                              <span>Agent</span>
                            </div>
                          )}
                          {pane.activeVenv && (
                            <span className="text-amber-400 font-bold mr-1.5 bg-amber-400/10 border border-amber-400/15 px-1.5 rounded-full text-[8.5px] leading-none py-0.5">({pane.activeVenv})</span>
                          )}
                          <span className="text-emerald-450 font-bold">ravi@averqel</span>
                          <span className="text-foreground/40 font-bold">:</span>
                          <span className="text-primary font-bold">{pane.cwd.replace("/workspace", "~")}</span>
                          <span className="text-foreground font-bold mr-1.5">$</span>

                          <span className="text-foreground font-mono whitespace-pre break-all flex items-center min-h-[14px]">
                            {pane.inputVal}
                            {pane.prediction && (
                              <span className="text-foreground/30 italic whitespace-pre pointer-events-none select-none">
                                {pane.prediction}
                              </span>
                            )}
                            <span className="inline-block w-1.5 h-3.5 bg-foreground/80 ml-0.5 animate-pulse vertical-middle shadow-[0_0_4px_rgba(255,255,255,0.7)]" />
                          </span>
                        </div>
                      )}
                    </div>

                  </div>
                </div>
              );
            })
          ) : (
            <div className="flex-1 min-h-0 overflow-y-auto p-4 select-text bg-[#030305]/45 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-white/5 hover:[&::-webkit-scrollbar-thumb]:bg-white/15 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-track]:bg-transparent">
              <span className="text-[9px] font-bold uppercase tracking-widest text-foreground/20 block mb-3.5">
                Task Execution History Log
              </span>
              {focusedPane.commandHistory.length === 0 ? (
                <div className="text-foreground/35 text-[10px] py-8 text-center italic">
                  No commands executed in this session.
                </div>
              ) : (
                <div className="space-y-1.5">
                  {focusedPane.commandHistory.map((h) => (
                    <div key={h.id} className="py-2.5 flex items-center justify-between text-[11px] bg-white/[0.01] hover:bg-white/[0.03] border border-white/5 px-3.5 rounded-xl transition shadow-sm">
                      <div className="flex flex-col gap-1 min-w-0 flex-1 mr-4">
                        <span className="font-mono text-foreground/90 select-all font-bold truncate leading-none">{h.command}</span>
                        <span className="text-[8.5px] text-foreground/30 leading-none">{h.timestamp}</span>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {h.status === "running" && (
                          <span className="flex items-center gap-1 text-emerald-450 text-[9.5px] font-bold uppercase">
                            <Clock size={10} className="animate-pulse" />
                            <span>Running</span>
                          </span>
                        )}
                        {h.status === "finished" && (
                          <span className="flex items-center gap-1 text-emerald-450 text-[9.5px] font-bold uppercase">
                            <CheckCircle2 size={10} />
                            <span>Success</span>
                          </span>
                        )}
                        {h.status === "failed" && (
                          <span className="flex items-center gap-1 text-red-450 text-[9.5px] font-bold uppercase">
                            <XCircle size={10} />
                            <span>Error ({h.exitCode})</span>
                          </span>
                        )}
                        {h.status === "killed" && (
                          <span className="flex items-center gap-1 text-amber-500 text-[9.5px] font-bold uppercase">
                            <Square size={10} />
                            <span>Killed</span>
                          </span>
                        )}
                        <button
                          onClick={() => {
                            updatePane(focusedPaneId, { inputVal: h.command });
                            setActiveTab("terminal");
                            setTimeout(() => inputRefs.current[focusedPaneId]?.focus(), 50);
                          }}
                          title="Copy command to input"
                          className="p-1 hover:bg-white/5 rounded-lg text-foreground/30 hover:text-primary transition"
                        >
                          <ArrowUpRight size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Side Tab lists panel */}
        <div className="w-[145px] border-l border-white/10 bg-[#07070a]/75 flex flex-col flex-shrink-0 select-none overflow-hidden h-full">

          <div className="flex-1 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:bg-white/5 hover:[&::-webkit-scrollbar-thumb]:bg-white/15 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-track]:bg-transparent">
            <div className="p-2 border-b border-white/5 bg-white/[0.01]">
              <span className="text-[7.5px] font-black tracking-widest text-foreground/30 uppercase">Sessions</span>
            </div>
            <div className="p-1 space-y-0.5">
              {groups.map((g) => {
                const isGroupActive = g.id === activeGroupId;

                return g.panes.map((p, idx) => {
                  const isPaneFocused = p.id === focusedPaneId;
                  const totalPanes = g.panes.length;

                  let branchPrefix = "";
                  if (totalPanes > 1) {
                    if (idx === 0) {
                      branchPrefix = "┌ ";
                    } else if (idx === totalPanes - 1) {
                      branchPrefix = "└ ";
                    } else {
                      branchPrefix = "├ ";
                    }
                  }

                  return (
                    <div
                      key={p.id}
                      onClick={() => {
                        setActiveGroupId(g.id);
                        setFocusedPaneId(p.id);
                        setTimeout(() => inputRefs.current[p.id]?.focus(), 50);
                      }}
                      className={`group relative flex items-center justify-between px-2 py-1 rounded-lg cursor-pointer transition-all border ${
                        isPaneFocused
                          ? "bg-white/[0.04] text-foreground border-white/10 shadow-sm"
                          : isGroupActive
                          ? "text-foreground/75 border-transparent hover:bg-white/[0.02] hover:text-foreground/90"
                          : "text-foreground/45 border-transparent hover:bg-white/[0.02] hover:text-foreground/80"
                      }`}
                    >
                      <div className="flex items-center min-w-0">
                        {branchPrefix && (
                          <span className="text-foreground/25 font-bold mr-1.5 text-[11px] leading-none whitespace-pre">
                            {branchPrefix}
                          </span>
                        )}

                        <div className="flex items-center gap-1.5 truncate">
                          {p.type === "averqel" ? (
                            <Bot size={10} className={isPaneFocused ? "text-primary animate-pulse" : "text-foreground/40"} />
                          ) : (
                            <TerminalIcon size={10} className={p.isRunning ? "text-emerald-450 animate-pulse" : (isPaneFocused ? "text-primary" : "text-foreground/40")} />
                          )}
                          <span className={`text-[9.5px] font-bold truncate leading-none uppercase tracking-wide ${isPaneFocused ? "text-primary" : ""}`}>
                            {p.name}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-0.5">
                        {isPaneFocused && p.pid && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setShowPidPopoverId(showPidPopoverId === p.id ? null : p.id);
                            }}
                            className="text-foreground/30 hover:text-primary transition p-0.5"
                            title="View Process details"
                          >
                            <Info size={9.5} />
                          </button>
                        )}

                        <button
                          onClick={(e) => handleSplitTerminalPane(p.id, e)}
                          className="opacity-0 group-hover:opacity-100 text-foreground/30 hover:text-foreground p-0.5 transition"
                          title="Split Terminal"
                        >
                          <Columns2 size={9.5} />
                        </button>

                        <button
                          onClick={(e) => handleDeleteTerminalPane(p.id, e)}
                          className="opacity-0 group-hover:opacity-100 text-foreground/30 hover:text-red-400 p-0.5 transition"
                          title="Close Session"
                        >
                          <Trash2 size={9.5} />
                        </button>
                      </div>
                    </div>
                  );
                });
              })}
            </div>
          </div>

          {/* Vector-State Phase Space trajectory Visualizer widget */}
          <div className="border-t border-white/10 bg-black/45 p-2.5 flex flex-col gap-2 flex-shrink-0 select-none">
            <div className="flex items-center justify-between">
              <span className="text-[7.5px] font-black tracking-widest text-primary uppercase">V-STATE PHASE MONITOR</span>
              <span className="text-[8px] font-mono text-emerald-450 animate-pulse flex items-center gap-0.5">
                <span className="h-1 w-1 rounded-full bg-emerald-450 animate-ping" />
                <span>LIVE</span>
              </span>
            </div>

            {/* SVG Plot */}
            <div className="relative w-full h-[65px] bg-[#020203] rounded-lg border border-white/5 overflow-hidden flex items-center justify-center">
              {/* Radial gradient background to represent center state energy */}
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(var(--color-primary-rgb),0.05)_0%,transparent_75%)]" />
              <svg width="100%" height="100%" viewBox="0 0 100 100" className="absolute inset-0 z-10">
                {/* Grid Lines */}
                <line x1="0" y1="50" x2="100" y2="50" stroke="rgba(255,255,255,0.03)" strokeWidth="0.75" />
                <line x1="50" y1="0" x2="50" y2="100" stroke="rgba(255,255,255,0.03)" strokeWidth="0.75" />
                <circle cx="50" cy="50" r="25" fill="none" stroke="rgba(255,255,255,0.02)" strokeWidth="1" strokeDasharray="1.5,1.5" />
                <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.01)" strokeWidth="1" />

                {/* Plot vector path */}
                {(() => {
                  const q = focusedPane.phaseState?.coordinate_q || 0;
                  const p = focusedPane.phaseState?.coordinate_p || 0;
                  const targetX = 50 + q * 8;
                  const targetY = 50 - p * 8;
                  return (
                    <>
                      <line x1="50" y1="50" x2={targetX} y2={targetY} stroke="var(--color-primary)" strokeWidth="1.25" strokeLinecap="round" strokeDasharray="1,1" />
                      <line x1="50" y1="50" x2={targetX} y2={targetY} stroke="var(--color-primary)" strokeWidth="1.25" strokeLinecap="round" className="opacity-40 filter blur-[1px]" />
                      <circle cx={targetX} cy={targetY} r="2.5" fill="var(--color-primary)" className="shadow-[0_0_8px_rgba(var(--color-primary-rgb),0.5)]" />
                      <circle cx={targetX} cy={targetY} r="5" fill="none" stroke="var(--color-primary)" strokeWidth="0.5" className="animate-ping origin-center" />
                    </>
                  );
                })()}
              </svg>
              <span className="absolute bottom-1 right-1.5 text-[6.5px] text-foreground/20 font-bold uppercase tracking-widest z-20">q (coord)</span>
              <span className="absolute top-1 left-1.5 text-[6.5px] text-foreground/20 font-bold uppercase tracking-widest z-20">p (mom)</span>
            </div>

            {/* Readouts grid */}
            <div className="grid grid-cols-2 gap-1.5 text-[8.5px] leading-tight font-mono">
              <div className="flex flex-col bg-white/[0.01] border border-white/[0.03] p-1 rounded-md">
                <span className="text-foreground/35 text-[6.5px] uppercase font-black leading-none">Entropy H(X)</span>
                <span className="text-cyan-400 font-bold mt-1 leading-none">{focusedPane.phaseState?.entropy || "1.20"} <span className="text-[7.5px] font-medium text-foreground/40">b</span></span>
              </div>
              <div className="flex flex-col bg-white/[0.01] border border-white/[0.03] p-1 rounded-md">
                <span className="text-foreground/35 text-[6.5px] uppercase font-black leading-none">Tot Energy H</span>
                <span className="text-primary font-bold mt-1 leading-none">{focusedPane.phaseState?.total_energy || "4.50"} <span className="text-[7.5px] font-medium text-foreground/40">J</span></span>
              </div>
              <div className="flex flex-col bg-white/[0.01] border border-white/[0.03] p-1 rounded-md">
                <span className="text-foreground/35 text-[6.5px] uppercase font-black leading-none">Complexity V(q)</span>
                <span className="text-foreground/80 mt-1 leading-none">{focusedPane.phaseState?.potential_energy || "2.10"}</span>
              </div>
              <div className="flex flex-col bg-white/[0.01] border border-white/[0.03] p-1 rounded-md">
                <span className="text-foreground/35 text-[6.5px] uppercase font-black leading-none">Activity T(p)</span>
                <span className="text-foreground/80 mt-1 leading-none">{focusedPane.phaseState?.kinetic_energy || "2.40"}</span>
              </div>
            </div>
          </div>

        </div>

      </div>

    </div>
  );
}
