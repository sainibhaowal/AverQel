"use client";

import Image from "next/image";
import React, { useEffect, useState } from "react";
import { X, Minus, Square, Copy } from "lucide-react";
import { APP_VERSION } from "@/lib/release";

export default function TitleBar() {
  const [isTauri, setIsTauri] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      setIsTauri(true);
    }
    const checkMaximized = async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const window = getCurrentWindow();
        setIsMaximized(await window.isMaximized());

        window.onResized(async () => {
          setIsMaximized(await window.isMaximized());
        });
      } catch {
        // Not running in Tauri
      }
    };
    checkMaximized();
  }, []);

  const handleMinimize = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().minimize();
    } catch {}
  };

  const handleMaximize = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      const window = getCurrentWindow();
      if (await window.isMaximized()) {
        await window.unmaximize();
      } else {
        await window.maximize();
      }
      setIsMaximized(await window.isMaximized());
    } catch {}
  };

  const handleClose = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().hide();
    } catch {}
  };

  if (!isTauri) return null;

  return (
    <div className="fixed top-0 right-0 left-0 z-[9999] flex h-10 items-center justify-between border-b border-white/5 bg-[#0a0a0b]/80 backdrop-blur-md select-none">
      {/* Background drag region */}
      <div
        data-tauri-drag-region
        className="absolute inset-0 h-full w-full"
        style={{ zIndex: 0 }}
      />

      {/* App Logo & Title */}
      <div
        className="pointer-events-none relative flex items-center gap-3 pl-4"
        style={{ zIndex: 10 }}
      >
        <Image src="/logo_icon.svg" alt="Logo" width={16} height={16} className="opacity-80" />
        <span className="text-[11px] font-bold tracking-[0.2em] text-slate-400 uppercase">
          AverQel {APP_VERSION}
        </span>
      </div>

      {/* Window Controls */}
      <div className="relative flex h-full items-center" style={{ zIndex: 10 }}>
        <button
          onClick={handleMinimize}
          className="flex h-full w-12 items-center justify-center text-slate-400 transition-colors hover:bg-white/5 hover:text-white"
        >
          <Minus size={14} className="pointer-events-none" />
        </button>
        <button
          onClick={handleMaximize}
          className="flex h-full w-12 items-center justify-center text-slate-400 transition-colors hover:bg-white/5 hover:text-white"
        >
          {isMaximized ? (
            <Copy size={12} className="pointer-events-none" />
          ) : (
            <Square size={12} className="pointer-events-none" />
          )}
        </button>
        <button
          onClick={handleClose}
          className="flex h-full w-12 items-center justify-center text-slate-400 transition-colors hover:bg-red-500/80 hover:text-white"
        >
          <X size={14} className="pointer-events-none" />
        </button>
      </div>
    </div>
  );
}
