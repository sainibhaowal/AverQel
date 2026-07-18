"use client";

interface SkeletonProps {
  className?: string;
  shape?: "rect" | "circle" | "text";
}

export default function Skeleton({ className = "", shape = "rect" }: SkeletonProps) {
  const baseClasses =
    "animate-pulse bg-muted ring-1 ring-glass-border isolate overflow-hidden relative";

  // Create a shimmer effect over the skeleton
  const shimmer =
    "before:absolute before:inset-0 before:-translate-x-full before:animate-[shimmer_2s_infinite] before:bg-gradient-to-r before:from-transparent before:via-white/5 before:to-transparent";

  let shapeClasses = "";
  if (shape === "circle") {
    shapeClasses = "rounded-full";
  } else if (shape === "rect") {
    shapeClasses = "rounded-lg";
  } else if (shape === "text") {
    shapeClasses = "rounded h-4 w-3/4";
  }

  return <div className={`${baseClasses} ${shapeClasses} ${shimmer} ${className}`} />;
}
