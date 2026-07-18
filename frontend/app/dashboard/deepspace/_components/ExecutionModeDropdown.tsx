"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown, ShieldCheck, Unlock } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

type ExecutionMode = "auto_review" | "full_access";

interface ExecutionModeDropdownProps {
  value: ExecutionMode;
  onChange: (mode: ExecutionMode) => void;
  compact?: boolean;
  className?: string;
}

const MODE_META: Record<
  ExecutionMode,
  {
    label: string;
    description: string;
    icon: typeof ShieldCheck;
    triggerClass: string;
    iconClass: string;
  }
> = {
  auto_review: {
    label: "Auto-review",
    description: "Runs safe actions, asks only when risk is real.",
    icon: ShieldCheck,
    triggerClass: "text-sky-700 hover:text-sky-800 dark:text-sky-400 dark:hover:text-sky-300",
    iconClass: "text-sky-600 dark:text-sky-400",
  },
  full_access: {
    label: "Full access",
    description: "Runs autonomously with internal guardrails still active.",
    icon: Unlock,
    triggerClass:
      "text-amber-700 hover:text-amber-800 dark:text-amber-300 dark:hover:text-amber-200",
    iconClass: "text-amber-600 dark:text-amber-300",
  },
};

export default function ExecutionModeDropdown({
  value,
  onChange,
  compact = false,
  className,
}: ExecutionModeDropdownProps) {
  const [open, setOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<{
    top: number;
    left: number;
    above: boolean;
    width: number;
  } | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const active = MODE_META[value];
  const ActiveIcon = active.icon;

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current) return;
      const target = event.target as Node | null;
      if (target && rootRef.current.contains(target)) return;
      if (target && menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    window.addEventListener("mousedown", handlePointerDown);
    return () => window.removeEventListener("mousedown", handlePointerDown);
  }, []);

  useEffect(() => {
    if (!open) return;

    const updateMenuPosition = () => {
      const trigger = rootRef.current;
      if (!trigger) return;

      const rect = trigger.getBoundingClientRect();
      const width = Math.min(260, window.innerWidth - 16);
      const left = Math.max(8, Math.min(window.innerWidth - width - 8, rect.left));
      const estimatedHeight = 126;
      const above = rect.bottom + 8 + estimatedHeight > window.innerHeight;
      const top = above ? rect.top - 8 : rect.bottom + 8;

      setMenuPosition({ top, left, above, width });
    };

    updateMenuPosition();
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);
    return () => {
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className={
          className ||
          `inline-flex items-center gap-1.5 rounded-[0.5rem] border border-slate-300/80 bg-white/92 px-3 py-2 text-sm font-medium shadow-[0_10px_24px_rgba(15,23,42,0.08)] backdrop-blur-md transition dark:border-white/10 dark:bg-[#2e3027]/90 dark:shadow-[0_8px_24px_rgba(0,0,0,0.24)] ${active.triggerClass} ${
            compact ? "text-xs" : ""
          }`
        }
      >
        <ActiveIcon size={compact ? 13 : 14} className={active.iconClass} />
        <span>{active.label}</span>
        <ChevronDown
          size={compact ? 13 : 14}
          className={`transition ${open ? "rotate-180" : ""}`}
        />
      </button>

      {typeof document !== "undefined" && (
        createPortal(
          <AnimatePresence>
            {open && menuPosition && (
              <motion.div
                ref={menuRef}
                role="menu"
                initial={{ opacity: 0, scale: 0.95, y: menuPosition.above ? 8 : -8 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: menuPosition.above ? 8 : -8 }}
                transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                className="fixed z-[260] overflow-hidden rounded-2xl border border-slate-300/80 bg-white/96 p-1 shadow-[0_20px_45px_rgba(15,23,42,0.14)] backdrop-blur-xl dark:border-white/10 dark:bg-[#2f312a]/96 dark:shadow-[0_18px_48px_rgba(0,0,0,0.38)]"
                style={{
                  left: menuPosition.left,
                  width: menuPosition.width,
                  ...(menuPosition.above
                    ? { bottom: window.innerHeight - menuPosition.top, top: "auto" }
                    : { top: menuPosition.top }),
                }}
              >
                {(Object.keys(MODE_META) as ExecutionMode[]).map((mode) => {
                  const meta = MODE_META[mode];
                  const Icon = meta.icon;
                  const selected = mode === value;
                  return (
                    <button
                      key={mode}
                      type="button"
                      role="menuitemradio"
                      aria-checked={selected}
                      onClick={() => {
                        onChange(mode);
                        setOpen(false);
                      }}
                      className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                        selected
                          ? "bg-slate-100/95 dark:bg-white/8"
                          : "hover:bg-slate-100/80 dark:hover:bg-white/6"
                      }`}
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        <Icon size={14} className={meta.iconClass} />
                        <div className="min-w-0">
                          <div className={`text-sm font-medium ${meta.triggerClass}`}>
                            {meta.label}
                          </div>
                          <div className="text-foreground/52 text-[11px] leading-relaxed dark:text-white/45">
                            {meta.description}
                          </div>
                        </div>
                      </div>
                      {selected ? (
                        <Check size={14} className="text-foreground/70 dark:text-white/75" />
                      ) : null}
                    </button>
                  );
                })}
              </motion.div>
            )}
          </AnimatePresence>,
          document.body,
        )
      )}
    </div>
  );
}
