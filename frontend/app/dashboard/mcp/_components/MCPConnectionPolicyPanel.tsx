import { useEffect, useState } from "react";

import { updateMCPPolicy, type MCPConnectionPolicy, type MCPRiskLabel, type MCPToolMode } from "@/lib/mcp-api";

const RISK_OPTIONS: MCPRiskLabel[] = ["read", "write", "delete", "external_message"];
const MODES: MCPToolMode[] = ["always_allow", "needs_approval", "blocked"];

type EditablePolicy = Pick<MCPConnectionPolicy, "allowed_tools" | "denied_tools" | "read_only" | "risk_ceiling" | "approval_rules" | "tool_modes" | "default_enabled" | "deepspace_overrides" | "conversation_overrides">;

export default function MCPConnectionPolicyPanel({ serverId, policy, onSaved }: { serverId: string; policy: MCPConnectionPolicy; onSaved?: (policy: MCPConnectionPolicy) => void }) {
  const [draft, setDraft] = useState<EditablePolicy>(toEditable(policy));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => setDraft(toEditable(policy)), [policy]);

  const save = async () => {
    setSaving(true); setMessage(null);
    try {
      const saved = await updateMCPPolicy(serverId, draft);
      onSaved?.(saved);
      setMessage("Policy saved.");
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "Unable to save policy."); }
    finally { setSaving(false); }
  };

  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-lg font-semibold text-white">Connection policy</h2><p className="mt-1 text-sm text-white/55">These settings are scoped to your account and this MCP connection.</p></div><button type="button" onClick={() => void save()} disabled={saving} className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-900 disabled:opacity-50">{saving ? "Saving…" : "Save policy"}</button></div>
      {message && <p className="mt-3 text-sm text-emerald-200" role="status">{message}</p>}
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="flex items-start gap-3 rounded-xl border border-white/10 p-3"><input type="checkbox" checked={draft.default_enabled} onChange={(event) => setDraft({ ...draft, default_enabled: event.target.checked })} className="mt-1" /><span><span className="block text-sm text-white">Enable across DeepSpace</span><span className="mt-1 block text-xs text-white/45">Connected accounts are available automatically in every conversation while enabled.</span></span></label>
        <label className="flex items-start gap-3 rounded-xl border border-white/10 p-3"><input type="checkbox" checked={draft.read_only} onChange={(event) => setDraft({ ...draft, read_only: event.target.checked })} className="mt-1" /><span><span className="block text-sm text-white">Read-only mode</span><span className="mt-1 block text-xs text-white/45">Blocks write, delete, and external-message tools.</span></span></label>
      </div>
      <label className="mt-4 block text-sm text-white">Maximum risk level<select value={draft.risk_ceiling} onChange={(event) => setDraft({ ...draft, risk_ceiling: event.target.value as MCPRiskLabel })} className="mt-2 w-full rounded-lg border border-white/10 bg-[#111512] px-3 py-2 text-sm text-white sm:max-w-sm">{RISK_OPTIONS.map((risk) => <option key={risk} value={risk}>{risk.replaceAll("_", " ")}</option>)}</select></label>
      <div className="mt-5"><h3 className="text-sm font-semibold text-white">High-risk approval defaults</h3><p className="mt-1 text-xs text-white/45">Platform safety still requires confirmation for remote side effects, even when a tool is set to always allow.</p><div className="mt-3 grid gap-3 sm:grid-cols-3">{RISK_OPTIONS.filter((risk) => risk !== "read").map((risk) => <label key={risk} className="text-xs text-white/60">{risk.replaceAll("_", " ")}<select value={draft.approval_rules[risk] || "needs_approval"} onChange={(event) => setDraft({ ...draft, approval_rules: { ...draft.approval_rules, [risk]: event.target.value as MCPToolMode } })} className="mt-1 w-full rounded-lg border border-white/10 bg-[#111512] px-2 py-2 text-xs text-white">{MODES.map((mode) => <option key={mode} value={mode}>{mode.replaceAll("_", " ")}</option>)}</select></label>)}</div></div>
      <p className="mt-5 rounded-xl border border-white/10 bg-black/15 p-3 text-xs leading-5 text-white/50">Once this account is connected and enabled, its permitted tools are available automatically in every DeepSpace conversation. Tool access is checked again immediately before each remote call.</p>
    </section>
  );
}

function toEditable(policy: MCPConnectionPolicy): EditablePolicy { return { allowed_tools: [...policy.allowed_tools], denied_tools: [...policy.denied_tools], read_only: policy.read_only, risk_ceiling: policy.risk_ceiling, approval_rules: { ...policy.approval_rules }, tool_modes: { ...policy.tool_modes }, default_enabled: policy.default_enabled, deepspace_overrides: { ...policy.deepspace_overrides }, conversation_overrides: { ...policy.conversation_overrides } }; }
