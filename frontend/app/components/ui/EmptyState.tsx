"use client";

import { FolderOpen } from "lucide-react";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
}

export default function EmptyState({
  icon = <FolderOpen size={48} className="opacity-20" />,
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="glass-card flex h-64 w-full flex-col items-center justify-center rounded-2xl border-dashed p-8 text-center">
      <div className="text-muted-foreground bg-muted/50 mb-4 flex h-20 w-20 items-center justify-center rounded-full">
        {icon}
      </div>
      <h3 className="text-foreground mb-1 text-lg font-bold">{title}</h3>
      <p className="text-muted-foreground mb-6 max-w-sm text-sm leading-relaxed">{description}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
