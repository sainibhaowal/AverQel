"use client";

import React from "react";
import "katex/dist/katex.min.css";
import { BlockMath } from "react-katex";
import { FunctionSquare } from "lucide-react";

interface MathMessageBlockProps {
  value: string;
  incomplete?: boolean;
}

export default function MathMessageBlock({ value, incomplete }: MathMessageBlockProps) {
  const content = value.trim();

  return (
    <div className="theme-panel w-full overflow-hidden rounded-[1.8rem] shadow-[0_24px_70px_-44px_rgba(8,47,73,0.16)] dark:shadow-[0_24px_70px_-44px_rgba(8,47,73,0.82)]">
      <div className="border-b border-black/5 px-5 py-4 sm:px-6 dark:border-white/8">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-emerald-500/15 bg-emerald-500/10 text-emerald-700 dark:text-emerald-100/80">
            <FunctionSquare className={`h-5 w-5 ${incomplete ? "animate-pulse" : ""}`} />
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h4 className="text-foreground text-[15px] font-semibold tracking-[-0.015em]">
                {incomplete ? "Solving Equation..." : "Mathematical Equation"}
              </h4>
              {incomplete && (
                <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold tracking-[0.16em] text-amber-700 uppercase dark:text-amber-200">
                  live
                </span>
              )}
            </div>
            <div className="text-foreground/40 text-[10px] tracking-tight">
              {incomplete ? "Rendering scientific notation..." : "LaTeX High-Fidelity Render"}
            </div>
          </div>
        </div>
      </div>

      <div className="custom-scrollbar flex items-center justify-center overflow-x-auto bg-black/[0.02] p-6 sm:p-10 dark:bg-white/[0.01]">
        {content ? (
          <div className="text-foreground max-w-full overflow-x-auto py-4 text-lg sm:text-xl">
            <BlockMath math={content} />
          </div>
        ) : (
          <div className="text-foreground/30 flex items-center gap-3 py-8 text-sm italic">
            Waiting for formula...
          </div>
        )}
      </div>

      {incomplete && (
        <div className="border-t border-black/5 px-5 py-3 dark:border-white/8">
          <div className="text-foreground/40 flex items-center gap-2 text-[10px] tracking-widest uppercase">
            <div className="h-1.5 w-1.5 animate-ping rounded-full bg-amber-500" />
            Computing scientific data
          </div>
        </div>
      )}
    </div>
  );
}
