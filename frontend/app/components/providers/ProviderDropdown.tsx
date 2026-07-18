"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface ProviderDropdownOption {
  value: string;
  label: string;
  hint?: string;
}

interface ProviderDropdownProps {
  label?: string;
  value: string;
  options: ProviderDropdownOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  name?: string;
  className?: string;
}

export default function ProviderDropdown({
  label,
  value,
  options,
  onChange,
  placeholder = "Select an option",
  disabled = false,
  name,
  className,
}: ProviderDropdownProps) {
  const [open, setOpen] = useState(false);
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});
  const rootRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const selectId = useId();

  const selectedOption = useMemo(
    () => options.find((option) => option.value === value) ?? null,
    [options, value],
  );

  function handleOpen() {
    if (disabled) return;
    if (!open && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownStyle({
        position: "fixed",
        top: rect.bottom + 4,
        left: rect.left,
        width: rect.width,
        zIndex: 9999,
      });
    }
    setOpen((c) => !c);
  }

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    function handleScroll() {
      if (open && buttonRef.current) {
        const rect = buttonRef.current.getBoundingClientRect();
        setDropdownStyle((s) => ({
          ...s,
          top: rect.bottom + 4,
          left: rect.left,
          width: rect.width,
        }));
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [open]);

  const menu = (
    <AnimatePresence>
      {open && !disabled ? (
        <motion.div
          id={`${selectId}-menu`}
          initial={{ opacity: 0, y: 6, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 4, scale: 0.98 }}
          transition={{ duration: 0.14 }}
          style={{
            ...dropdownStyle,
            maxHeight: "400px",
            overflowY: "auto",
          }}
          className="theme-panel-strong rounded-[1.25rem] border border-cyan-300/16 p-2 shadow-[0_24px_80px_-12px_rgba(0,0,0,0.6)]"
        >
          {options.length === 0 ? (
            <div className="text-muted-foreground rounded-[1rem] px-3 py-3 text-sm">
              No options available
            </div>
          ) : (
            options.map((option) => {
              const selected = option.value === value;
              return (
                <button
                  key={`${name || label}-option-${option.value}`}
                  type="button"
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className={`flex w-full items-start justify-between gap-3 rounded-[1rem] px-3 py-3 text-left transition-colors ${
                    selected
                      ? "text-accent-cyan bg-cyan-300/12"
                      : "text-foreground/80 hover:bg-muted/60 hover:text-foreground"
                  }`}
                >
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{option.label}</span>
                    {option.hint ? (
                      <span className="text-foreground/50 mt-1 block text-xs">{option.hint}</span>
                    ) : null}
                  </span>
                  {selected ? <Check size={15} className="mt-0.5 shrink-0" /> : null}
                </button>
              );
            })
          )}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );

  return (
    <div ref={rootRef} className="space-y-2">
      {label && (
        <label
          htmlFor={selectId}
          className="text-foreground/45 block text-[10px] font-semibold tracking-[0.22em] uppercase"
        >
          {label}
        </label>
      )}

      <select
        id={selectId}
        name={name}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className="sr-only"
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={`${name || label}-${option.value}`} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={`${selectId}-menu`}
        disabled={disabled}
        onClick={handleOpen}
        className={`theme-chip text-foreground flex w-full items-center justify-between gap-3 rounded-[1.15rem] px-4 py-3 text-left text-sm transition-colors outline-none hover:border-cyan-300/20 focus:border-cyan-300/35 disabled:cursor-not-allowed disabled:opacity-50 ${className || ""}`}
      >
        <span className={selectedOption ? "text-foreground" : "text-muted-foreground"}>
          {selectedOption?.label || placeholder}
        </span>
        <ChevronDown
          size={16}
          className={`text-foreground/55 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {typeof document !== "undefined" ? createPortal(menu, document.body) : null}
    </div>
  );
}
