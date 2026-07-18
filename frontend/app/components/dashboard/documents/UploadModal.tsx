"use client";

import { useState, useEffect, type MouseEvent as ReactMouseEvent } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { X, Info } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import Dropzone from "./Dropzone";

interface SupportedFormat {
  extension: string;
  category: string;
  extraction_method: string;
  needs_conversion: boolean;
}

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function UploadModal({ isOpen, onClose, onSuccess }: UploadModalProps) {
  const [showFormats, setShowFormats] = useState(false);
  const [formats, setFormats] = useState<SupportedFormat[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setMounted(true), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const fetchFormats = async () => {
    try {
      const response = await fetchWithAuth("/capabilities");
      if (response.ok) {
        const data = await response.json();
        setFormats(data.supported_formats);
      }
    } catch (error) {
      console.error("Failed to fetch formats:", error);
    }
  };

  if (!mounted) return null;

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="bg-black/60 absolute inset-0 backdrop-blur-sm"
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="border-glass-border bg-surface-0 relative flex max-h-[90vh] w-full max-w-lg flex-col overflow-y-auto rounded-[1.6rem] border px-8 py-10 shadow-2xl"
            onClick={(e: ReactMouseEvent<HTMLDivElement>) => e.stopPropagation()}
          >
          <div className="mb-10 flex items-center justify-between">
            <div className="flex flex-col">
              <h2 className="text-foreground flex items-center gap-3 text-2xl font-black tracking-tight">
                <div className="bg-primary h-8 w-1.5 rounded-full shadow-[0_0_15px_rgba(var(--primary),0.3)]" />
                Ingest Intelligence
              </h2>
              <p className="text-muted-foreground/60 border-primary/20 mt-1 ml-4 border-l-2 py-0.5 pl-3 text-[11px] font-black tracking-widest uppercase">
                Vectorization Gateway
              </p>
            </div>
            <button
              onClick={onClose}
              className="bg-foreground/5 text-foreground/70 hover:text-accent hover:bg-accent/10 hover:border-accent/20 flex h-10 w-10 items-center justify-center rounded-xl border border-transparent font-black transition-all"
            >
              <X size={20} className="stroke-[3]" />
            </button>
          </div>

          <Dropzone
            onSuccess={() => {
              onSuccess();
              onClose();
            }}
            onCancel={onClose}
            allowedExtensions={formats.map((f) => f.extension.toLowerCase())}
          />

          <div className="mt-8 flex justify-center">
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowFormats(true);
                if (formats.length === 0) fetchFormats();
              }}
              className="theme-pill hover-yellow border-accent/20 px-6 py-2 transition-all hover:scale-105"
            >
              <Info size={14} className="text-accent stroke-[2.5]" />
              <span className="font-bold">Matrix Configuration</span>
            </button>
          </div>

          <p className="text-foreground/40 mt-10 text-center text-[10px] font-bold tracking-[0.2em] uppercase">
            Zero-Knowledge Encryption • Isolated Compute Shards
          </p>

          <AnimatePresence>
            {showFormats && (
              <motion.div
                initial={{ opacity: 0, x: "100%" }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: "100%" }}
                className="dark:bg-surface-0 absolute inset-0 z-10 flex flex-col bg-white p-8"
              >
                <div className="mb-8 flex items-center justify-between">
                  <div>
                    <h3 className="flex items-center gap-2 text-xl font-extrabold tracking-tight">
                      <div className="bg-primary h-6 w-1 rounded-full shadow-[0_0_10px_rgba(var(--primary),0.3)]" />
                      Supported Matrix
                    </h3>
                    <p className="text-foreground/80 mt-1 text-[10px] font-black tracking-widest uppercase">
                      Native pipeline coverage
                    </p>
                  </div>
                  <button
                    onClick={() => setShowFormats(false)}
                    className="bg-foreground/5 text-foreground/60 hover:text-accent hover:bg-accent/10 flex h-10 w-10 items-center justify-center rounded-xl transition-all"
                  >
                    <X size={20} className="stroke-[2.5]" />
                  </button>
                </div>

                <div className="custom-scrollbar flex-1 space-y-6 overflow-y-auto pr-2">
                  {Object.entries(
                    formats.reduce(
                      (acc, curr) => {
                        const cat = curr.category;
                        if (!acc[cat]) acc[cat] = [];
                        acc[cat].push(curr);
                        return acc;
                      },
                      {} as Record<string, SupportedFormat[]>,
                    ),
                  ).map(([category, items]) => (
                    <div key={category} className="space-y-3">
                      <h4 className="text-primary/80 flex items-center gap-2 text-[9px] font-black tracking-[0.3em] uppercase">
                        <div className="bg-primary/40 h-1.5 w-1.5 rounded-full" />
                        {category.replace("-", " ")}
                      </h4>
                      <div className="grid grid-cols-2 gap-2">
                        {items.map((item) => (
                          <div
                            key={item.extension}
                            className="theme-card hover-yellow flex items-center justify-between !p-3"
                          >
                            <span className="text-foreground text-[11px] font-black tracking-tight uppercase">
                              {item.extension.replace(".", "")}
                            </span>
                            <span className="text-foreground/40 text-[9px] font-bold tracking-tighter italic">
                              {item.extraction_method.split("_")[0]}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="border-glass-border mt-8 border-t pt-6">
                  <p className="text-foreground/30 text-[10px] leading-relaxed font-bold tracking-tight uppercase italic">
                    * Legacy extensions (.doc, .xls, .ppt) are auto-converted to OOXML before
                    ingestion.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>
      )}
    </AnimatePresence>,
    document.body
  );
}
