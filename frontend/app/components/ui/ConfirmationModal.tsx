"use client";

import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Loader2, X } from "lucide-react";

interface ConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: "danger" | "warning" | "info" | "success";
  loading?: boolean;
}

export default function ConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel,
  cancelLabel = "Cancel",
  variant = "danger",
  loading = false,
}: ConfirmationModalProps) {
  const getVariantStyles = () => {
    switch (variant) {
      case "danger":
        return "bg-danger text-white hover:bg-danger/90 shadow-[0_8px_16px_rgba(var(--danger),0.25)]";
      case "warning":
        return "bg-warning text-black hover:bg-warning/90 shadow-[0_8px_16px_rgba(var(--warning),0.25)]";
      case "success":
        return "bg-success text-white hover:bg-success/90 shadow-[0_8px_16px_rgba(var(--success),0.25)]";
      default:
        return "bg-primary text-black hover:bg-primary/90 shadow-[0_8px_16px_rgba(var(--primary),0.25)]";
    }
  };

  const getIconColor = () => {
    switch (variant) {
      case "danger":
        return "text-danger";
      case "warning":
        return "text-warning";
      case "success":
        return "text-success";
      default:
        return "text-primary";
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirmation-modal-title"
          aria-describedby="confirmation-modal-message"
        >
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12, ease: "easeOut" }}
            onClick={onClose}
            className="absolute inset-0 bg-black/60"
          />
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.14, ease: "easeOut" }}
            className="confirmation-modal relative w-full max-w-md overflow-hidden rounded-[2rem] border border-white/10 bg-[#0f0f11] p-8 text-slate-100 shadow-2xl"
          >
            <div className="flex flex-col items-center text-center">
              <div
                className={`confirmation-modal-icon mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-white/5 ${getIconColor()}`}
              >
                <AlertTriangle size={32} />
              </div>

              <h3
                id="confirmation-modal-title"
                className="confirmation-modal-title mb-2 text-xl font-bold"
              >
                {title}
              </h3>
              <p
                id="confirmation-modal-message"
                className="confirmation-modal-message mb-8 text-sm leading-relaxed"
              >
                {message}
              </p>

              <div className="flex w-full flex-col gap-3 sm:flex-row">
                <button
                  onClick={onClose}
                  disabled={loading}
                  className="confirmation-modal-cancel flex-1 rounded-xl border border-white/10 bg-white/5 py-3 text-sm font-bold transition hover:bg-white/10 disabled:opacity-50"
                >
                  {cancelLabel}
                </button>
                <button
                  onClick={() => void onConfirm()}
                  disabled={loading}
                  className={`confirmation-modal-confirm flex flex-1 items-center justify-center gap-2 rounded-xl py-3 text-sm font-bold transition disabled:opacity-50 ${getVariantStyles()}`}
                >
                  {loading && <Loader2 className="animate-spin" size={16} />}
                  {confirmLabel}
                </button>
              </div>
            </div>

            <button
              onClick={onClose}
              className="confirmation-modal-close absolute top-6 right-6 transition"
            >
              <X size={20} />
            </button>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
