"use client";

import Image from "next/image";
import React, { useEffect, useState, useSyncExternalStore } from "react";
import { X, Minus, Square, Copy } from "lucide-react";
import { APP_VERSION } from "@/lib/release";

export default function TitleBar() {
  const isElectron = useSyncExternalStore(
    () => () => undefined,
    () => typeof window !== "undefined" && Boolean(window.electron),
    () => false,
  );
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    const electron = window.electron;
    if (!electron) return;
    const checkMaximized = async () => {
      try {
        setIsMaximized(await electron.window.isMaximized());
      } catch {
        // The native Electron window is not available during SSR or shutdown.
      }
    };
    void checkMaximized();
  }, []);

  const handleMinimize = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await window.electron?.window.minimize();
  };

  const handleMaximize = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const nextState = await window.electron?.window.toggleMaximize();
    if (typeof nextState === "boolean") setIsMaximized(nextState);
  };

  const handleClose = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await window.electron?.window.hide();
  };

  if (!isElectron) return null;

  return (
    <div className="fixed top-0 right-0 left-0 z-[9999] flex h-10 items-center justify-between border-b border-white/5 bg-[#0a0a0b]/80 backdrop-blur-md select-none">
      {/* Background drag region */}
      <div
        data-electron-drag-region
        className="absolute inset-0 h-full w-full"
        style={{ zIndex: 0 }}
      />

      {/* App Logo & Title */}
      <div
        className="pointer-events-none relative flex items-center gap-3 pl-4"
        style={{ zIndex: 10 }}
      >
        <Image
          src="/logo_icon.png"
          alt="AverQel logo"
          width={28}
          height={28}
          className="h-7 w-7 shrink-0 object-contain"
        />
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
