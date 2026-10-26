"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ListChecks, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { fetchWithAuth } from "@/lib/api";

export interface SupportedFormat {
  extension: string;
  category: string;
  extraction_method: string;
  needs_conversion: boolean;
}

async function requestSupportedFormats(): Promise<SupportedFormat[]> {
  const response = (await fetchWithAuth("/documents/supported-formats")) as Response;
  if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
  const data = (await response.json()) as { items: SupportedFormat[] };
  return data.items;
}

export default function ProtocolMatrixDialog() {
  const [showFormats, setShowFormats] = useState(false);
  const [formats, setFormats] = useState<SupportedFormat[]>([]);
  const [formatsLoading, setFormatsLoading] = useState(true);
  const [formatsError, setFormatsError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    void requestSupportedFormats()
      .then((items) => {
        if (active) setFormats(items);
      })
      .catch((error: unknown) => {
        console.error("Failed to load supported format list", error);
        if (active) setFormatsError(true);
      })
      .finally(() => {
        if (active) setFormatsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loadAttempt]);

  return (
    <>
      <button
        type="button"
        onClick={() => setShowFormats(true)}
        className="theme-pill hover-yellow border-accent/10 h-12 px-6 transition-all"
      >
        <ListChecks size={18} className="stroke-[2.5]" />
        <span className="font-bold">Protocol Matrix</span>
      </button>

      {typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence initial={false}>
            {showFormats ? (
              <motion.div
                key="protocol-matrix-overlay"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.14, ease: "easeOut" }}
                className="fixed inset-0 z-[100] flex items-center justify-center p-4"
              >
                <button
                  type="button"
                  aria-label="Close supported formats"
                  className="absolute inset-0 bg-black/60"
                  onClick={() => setShowFormats(false)}
                />
                <motion.div
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="protocol-matrix-title"
                  initial={{ y: 8 }}
                  animate={{ y: 0 }}
                  exit={{ y: 4 }}
                  transition={{ duration: 0.16, ease: "easeOut" }}
                  className="bg-surface-0 border-glass-border relative max-h-[85vh] w-[min(96vw,64rem)] overflow-hidden rounded-3xl border p-5 shadow-2xl sm:p-8"
                >
                  <div className="mb-6 flex items-center justify-between">
                    <div>
                      <h3
                        id="protocol-matrix-title"
                        className="text-foreground text-2xl font-extrabold tracking-tight"
                      >
                        Supported Formats
                      </h3>
                      <p className="text-foreground/40 mt-1 text-sm font-medium">
                        Native pipeline coverage coverage currently available.
                      </p>
                    </div>
                    <button
                      type="button"
                      aria-label="Close supported formats dialog"
                      onClick={() => setShowFormats(false)}
                      className="bg-foreground/5 text-foreground/40 hover:text-foreground hover:bg-foreground/10 flex h-10 w-10 items-center justify-center rounded-xl transition-all"
                    >
                      <X size={20} className="stroke-[2.5]" />
                    </button>
                  </div>

                  {formatsLoading ? (
                    <div
                      role="status"
                      className="text-muted-foreground flex min-h-40 items-center justify-center text-sm"
                    >
                      Loading supported formats…
                    </div>
                  ) : formatsError ? (
                    <div className="flex min-h-40 flex-col items-center justify-center gap-3">
                      <p role="alert" className="text-muted-foreground text-sm">
                        Supported formats could not be loaded.
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          setFormatsLoading(true);
                          setFormatsError(false);
                          setLoadAttempt((attempt) => attempt + 1);
                        }}
                        className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg px-3 py-2 text-sm font-semibold transition-colors"
                      >
                        Retry
                      </button>
                    </div>
                  ) : (
                    <div className="border-glass-border bg-foreground/[0.01] max-h-[60vh] overflow-y-auto rounded-2xl border shadow-inner">
                      <table className="w-full table-fixed border-collapse text-left">
                        <thead className="bg-surface-0 border-glass-border sticky top-0 z-10 border-b">
                          <tr className="text-foreground/40 text-[10px] font-bold tracking-[0.2em] uppercase">
                            <th className="w-[24%] px-3 py-3 sm:px-5 sm:py-4">Extension</th>
                            <th className="w-[28%] px-3 py-3 sm:px-5 sm:py-4">Category</th>
                            <th className="hidden w-[28%] px-3 py-3 sm:table-cell sm:px-5 sm:py-4">
                              Method
                            </th>
                            <th className="w-[48%] px-3 py-3 text-right sm:w-[20%] sm:px-5 sm:py-4">
                              Mode
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-glass-border divide-y">
                          {formats.map((item) => (
                            <tr
                              key={`${item.extension}-${item.extraction_method}`}
                              className="hover-yellow transition-colors"
                            >
                              <td className="text-primary truncate px-3 py-3 font-mono text-[12px] font-bold sm:px-5 sm:py-4 sm:text-[13px]">
                                {item.extension}
                              </td>
                              <td className="text-foreground/60 truncate px-3 py-3 text-[12px] font-medium sm:px-5 sm:py-4 sm:text-[13px]">
                                {item.category}
                              </td>
                              <td className="text-foreground/30 hidden truncate px-3 py-3 font-mono text-[11px] italic sm:table-cell sm:px-5 sm:py-4">
                                {item.extraction_method}
                              </td>
                              <td className="px-3 py-3 text-right sm:px-5 sm:py-4">
                                <span
                                  className={`theme-pill ${
                                    item.needs_conversion
                                      ? "!text-warning !bg-warning/10 !border-warning/20"
                                      : "!text-primary !bg-primary/10 !border-primary/20"
                                  }`}
                                >
                                  {item.needs_conversion ? "conversion" : "native"}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </motion.div>
              </motion.div>
            ) : null}
          </AnimatePresence>,
          document.body,
        )}
    </>
  );
}
