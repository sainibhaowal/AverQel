"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Info } from "lucide-react";
import { createPortal } from "react-dom";
import { useEffect, useRef, useState, type ReactNode } from "react";

interface TooltipPosition {
  top: number;
  left: number;
  above: boolean;
}

interface AverQelTooltipProps {
  label: string;
  title: string;
  content: ReactNode;
  icon?: ReactNode;
  buttonClassName?: string;
  panelClassName?: string;
}

const TOOLTIP_MARGIN = 12;
const MAX_TOOLTIP_WIDTH = 320;

export default function AverQelTooltip({
  label,
  title,
  content,
  icon,
  buttonClassName,
  panelClassName,
}: AverQelTooltipProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<TooltipPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);

  const clearCloseTimer = () => {
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };

  const scheduleClose = () => {
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => setOpen(false), 120);
  };

  const updatePosition = () => {
    const trigger = triggerRef.current;
    if (!trigger || typeof window === "undefined") return;

    const rect = trigger.getBoundingClientRect();
    const tooltipWidth = Math.min(MAX_TOOLTIP_WIDTH, window.innerWidth - 16);
    const halfWidth = tooltipWidth / 2;
    const rawLeft = rect.left + rect.width / 2;
    const left = Math.max(halfWidth + 8, Math.min(window.innerWidth - halfWidth - 8, rawLeft));
    const above = rect.top > 240;
    const top = above ? rect.top - TOOLTIP_MARGIN : rect.bottom + TOOLTIP_MARGIN;

    setPosition({ top, left, above });
  };

  useEffect(() => {
    return () => {
      if (closeTimerRef.current) window.clearTimeout(closeTimerRef.current);
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current);
    };
  }, []);

  useEffect(() => {
    if (!open) return;

    updatePosition();

    const syncPosition = () => {
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current);
      rafRef.current = window.requestAnimationFrame(updatePosition);
    };

    window.addEventListener("resize", syncPosition);
    window.addEventListener("scroll", syncPosition, true);

    return () => {
      window.removeEventListener("resize", syncPosition);
      window.removeEventListener("scroll", syncPosition, true);
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          clearCloseTimer();
          setOpen((current) => !current);
        }}
        onPointerEnter={(event) => {
          if (event.pointerType === "mouse") {
            clearCloseTimer();
            setOpen(true);
          }
        }}
        onPointerLeave={scheduleClose}
        onFocus={() => {
          clearCloseTimer();
          setOpen(true);
        }}
        onBlur={scheduleClose}
        className={
          buttonClassName ??
          "border-foreground/10 bg-foreground/5 text-foreground/55 hover:border-primary/30 hover:bg-primary/10 hover:text-primary flex h-8 w-8 items-center justify-center rounded-full border transition-all"
        }
      >
        {icon ?? <Info size={13} className="stroke-[2.5]" />}
      </button>

      {typeof document !== "undefined" &&
        open &&
        position &&
        createPortal(
          <div
            className="pointer-events-auto fixed z-[220]"
            style={{
              top: position.top,
              left: position.left,
              width: `min(${MAX_TOOLTIP_WIDTH}px, calc(100vw - 1rem))`,
            }}
            onPointerEnter={clearCloseTimer}
            onPointerLeave={scheduleClose}
          >
            <AnimatePresence>
              <motion.div
                initial={{ opacity: 0, y: position.above ? 10 : -10, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: position.above ? 10 : -10, scale: 0.98 }}
                className={`rounded-[1.4rem] border border-white/10 bg-[rgba(10,14,11,0.98)] p-4 shadow-[0_28px_70px_rgba(0,0,0,0.55)] backdrop-blur-xl ${position.above ? "-translate-x-1/2 -translate-y-full" : "-translate-x-1/2"} ${panelClassName ?? ""}`}
              >
                <p className="text-foreground text-[10px] font-black tracking-[0.24em] uppercase">
                  {title}
                </p>
                <div className="mt-3 space-y-3">{content}</div>
              </motion.div>
            </AnimatePresence>
          </div>,
          document.body,
        )}
    </>
  );
}
