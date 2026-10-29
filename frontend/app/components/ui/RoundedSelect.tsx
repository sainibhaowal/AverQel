"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";

export interface RoundedSelectOption {
  value: string;
  label: string;
  description?: string;
}

interface RoundedSelectProps {
  label: string;
  value?: string;
  defaultValue?: string;
  options: RoundedSelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  id?: string;
  className?: string;
  triggerClassName?: string;
  menuClassName?: string;
  optionClassName?: string;
  matchTriggerWidth?: boolean;
  showSelectionCheck?: boolean;
  menuMaxHeight?: number;
  estimatedOptionHeight?: number;
}

export default function RoundedSelect({
  label,
  value,
  defaultValue,
  options,
  onChange,
  disabled = false,
  id,
  className = "",
  triggerClassName = "",
  menuClassName = "",
  optionClassName = "",
  matchTriggerWidth = false,
  showSelectionCheck = false,
  menuMaxHeight = 280,
  estimatedOptionHeight = 36,
}: RoundedSelectProps) {
  const [open, setOpen] = useState(false);
  const [uncontrolledValue, setUncontrolledValue] = useState(
    () => defaultValue ?? value ?? options[0]?.value ?? "",
  );
  const [position, setPosition] = useState<{
    top: number;
    left: number;
    width: number;
    maxHeight: number;
    transformOrigin: "top center" | "bottom center";
  } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const generatedId = useId();
  const listboxId = `${generatedId}-listbox`;
  const selectedValue = value ?? uncontrolledValue;
  const selected = options.find((option) => option.value === selectedValue) ?? options[0];
  const activeValue = selected?.value ?? selectedValue;
  const reduceMotion = useReducedMotion();
  const typeahead = useRef("");
  const typeaheadTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) return;
    const updatePosition = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const viewportWidth = Math.max(1, window.innerWidth - 16);
      const width = matchTriggerWidth
        ? Math.min(Math.max(rect.width, 164), viewportWidth)
        : Math.min(Math.max(rect.width, 164), 320, viewportWidth);
      const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
      const below = window.innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const naturalHeight = Math.min(
        menuMaxHeight,
        Math.max(48, options.length * estimatedOptionHeight + 8),
      );
      const opensAbove = below < naturalHeight && above > below;
      const maxHeight = Math.max(64, Math.min(menuMaxHeight, opensAbove ? above : below));
      setPosition({
        top: opensAbove ? Math.max(8, rect.top - maxHeight - 6) : rect.bottom + 6,
        left,
        width,
        maxHeight,
        transformOrigin: opensAbove ? "bottom center" : "top center",
      });
    };
    const closeOutside = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        !rootRef.current?.contains(event.target) &&
        !menuRef.current?.contains(event.target)
      ) {
        setOpen(false);
      }
    };
    const closeEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    updatePosition();
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    document.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeEscape);
      document.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [estimatedOptionHeight, matchTriggerWidth, menuMaxHeight, open, options.length]);

  useEffect(
    () => () => {
      if (typeaheadTimer.current) clearTimeout(typeaheadTimer.current);
    },
    [],
  );

  const moveFocus = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>("[role=option]") ?? [],
    );
    if (
      event.key.length === 1 &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey &&
      items.length > 0
    ) {
      event.preventDefault();
      const key = event.key.toLowerCase();
      const repeatedKey = typeahead.current && [...typeahead.current].every((char) => char === key);
      typeahead.current = repeatedKey ? key : `${typeahead.current}${key}`;
      if (typeaheadTimer.current) clearTimeout(typeaheadTimer.current);
      typeaheadTimer.current = setTimeout(() => {
        typeahead.current = "";
        typeaheadTimer.current = null;
      }, 700);
      const current = items.indexOf(document.activeElement as HTMLButtonElement);
      const startIndex = current < 0 ? 0 : (current + 1) % items.length;
      const orderedItems = [...items.slice(startIndex), ...items.slice(0, startIndex)];
      orderedItems
        .find((item) => item.textContent?.trim().toLowerCase().startsWith(typeahead.current))
        ?.focus();
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const current = items.indexOf(document.activeElement as HTMLButtonElement);
    if (items.length === 0) return;
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? items.length - 1
          : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  };

  return (
    <div className={`relative ${className}`} ref={rootRef}>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        role="combobox"
        aria-label={label}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        aria-expanded={open}
        disabled={disabled || options.length === 0}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (!open && ["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
            event.preventDefault();
            setOpen(true);
          }
        }}
        className={`border-border bg-background text-foreground hover:bg-surface-1 focus-visible:outline-primary inline-flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left text-xs transition-colors focus-visible:outline focus-visible:outline-2 disabled:cursor-not-allowed disabled:opacity-50 ${triggerClassName}`}
      >
        <span className="min-w-0 truncate">{selected?.label ?? label}</span>
        <ChevronDown
          size={14}
          aria-hidden="true"
          className={`shrink-0 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {open && position && (
              <motion.div
                ref={menuRef}
                id={listboxId}
                role="listbox"
                aria-label={label}
                initial={reduceMotion ? false : { opacity: 0, y: -5, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -3, scale: 0.98 }}
                transition={reduceMotion ? { duration: 0 } : { duration: 0.14, ease: "easeOut" }}
                className={`averqel-rounded-select-menu border-border bg-background text-foreground overflow-y-auto rounded-2xl border p-1.5 shadow-xl ${menuClassName}`}
                style={{
                  position: "fixed",
                  top: position.top,
                  left: position.left,
                  width: position.width,
                  maxHeight: position.maxHeight,
                  zIndex: 1400,
                  transformOrigin: position.transformOrigin,
                }}
              >
                {options.map((option, index) => (
                  <button
                    key={`${option.value}:${index}`}
                    type="button"
                    role="option"
                    aria-selected={option.value === activeValue}
                    autoFocus={option.value === activeValue}
                    onKeyDown={moveFocus}
                    onClick={() => {
                      if (value === undefined) setUncontrolledValue(option.value);
                      onChange(option.value);
                      setOpen(false);
                      triggerRef.current?.focus();
                    }}
                    className={`focus-visible:outline-primary flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left text-xs transition-colors duration-100 focus-visible:outline focus-visible:outline-2 ${option.value === activeValue ? "bg-primary/12 text-primary font-semibold" : "text-foreground hover:bg-surface-1 focus-visible:bg-surface-1"} ${optionClassName}`}
                  >
                    {option.description ? (
                      <span className="flex min-w-0 flex-col gap-0.5">
                        <span className="truncate leading-5">{option.label}</span>
                        <span className="truncate text-xs font-normal text-muted-foreground">
                          {option.description}
                        </span>
                      </span>
                    ) : (
                      <span className="min-w-0 truncate">{option.label}</span>
                    )}
                    {showSelectionCheck && option.value === activeValue && (
                      <Check size={16} aria-hidden="true" className="shrink-0 text-primary" />
                    )}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>,
          document.body,
        )}
    </div>
  );
}
