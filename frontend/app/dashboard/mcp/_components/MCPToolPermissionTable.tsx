import { useEffect, useState } from "react";

import { updateMCPToolPolicy, type MCPTool, type MCPToolMode } from "@/lib/mcp-api";

const MODES: MCPToolMode[] = ["always_allow", "needs_approval", "blocked"];

export default function MCPToolPermissionTable({
  serverId,
  tools,
  onChanged,
}: {
  serverId: string;
  tools: MCPTool[];
  onChanged?: (tools: MCPTool[]) => void;
}) {
  const [items, setItems] = useState(tools);
  const [saving, setSaving] = useState<string | null>(null);
  useEffect(() => queueMicrotask(() => setItems(tools)), [tools]);

  const changeMode = async (tool: MCPTool, mode: MCPToolMode) => {
    const previous = items;
    const next = items.map((item) => (item.name === tool.name ? { ...item, mode } : item));
    setItems(next);
    setSaving(tool.name);
    try {
      const saved = await updateMCPToolPolicy(serverId, tool.name, mode);
      const finalItems = next.map((item) => (item.name === saved.name ? saved : item));
      setItems(finalItems);
      onChanged?.(finalItems);
    } catch {
      setItems(previous);
    } finally {
      setSaving(null);
    }
  };

  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Tool permissions</h2>
          <p className="mt-1 text-sm text-white/55">
            Individual changes override the master tool permission. Risk and connection safeguards
            can still require approval or block a tool.
          </p>
        </div>
        <span className="text-xs text-white/45">{items.length} tools</span>
      </div>
      {items.length === 0 ? (
        <p className="mt-5 text-sm text-white/50">No tools are available in the current catalog.</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[620px] text-left text-sm">
            <thead className="text-xs tracking-wide text-white/40 uppercase">
              <tr>
                <th className="pr-4 pb-3">Tool</th>
                <th className="pr-4 pb-3">Category</th>
                <th className="pr-4 pb-3">Risk</th>
                <th className="pb-3">Permission</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {items.map((tool) => (
                <tr key={tool.name}>
                  <td className="py-3 pr-4">
                    <p className="font-mono text-emerald-200">{tool.name}</p>
                    <p className="mt-1 max-w-sm text-xs text-white/45">
                      {tool.description || "No description provided."}
                    </p>
                  </td>
                  <td className="py-3 pr-4 text-white/55">{tool.category || "General"}</td>
                  <td className="py-3 pr-4">
                    <div className="flex flex-wrap gap-1">
                      {(tool.risk_labels.length ? tool.risk_labels : ["read"]).map((risk) => (
                        <span
                          key={risk}
                          className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-white/60"
                        >
                          {risk.replaceAll("_", " ")}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-3">
                    <select
                      aria-label={`Permission for ${tool.name}`}
                      value={tool.mode}
                      disabled={saving === tool.name}
                      onChange={(event) => void changeMode(tool, event.target.value as MCPToolMode)}
                      className="rounded-lg border border-white/10 bg-[#111512] px-2 py-2 text-xs text-white"
                    >
                      {MODES.map((mode) => (
                        <option key={mode} value={mode}>
                          {mode.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
