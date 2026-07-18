"use client";

interface ProviderDeleteDialogProps {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function ProviderDeleteDialog({
  open,
  title,
  body,
  confirmLabel,
  busy = false,
  onCancel,
  onConfirm,
}: ProviderDeleteDialogProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 p-4 sm:p-6">
      <div className="relative flex h-full w-full items-center justify-center overflow-hidden rounded-[2.5rem] border border-white/10 bg-[rgba(3,6,4,0.82)] shadow-[0_28px_90px_rgba(0,0,0,0.6)] ring-1 ring-white/5 backdrop-blur-[2px]">
        <div className="w-full max-w-sm space-y-5 rounded-[2.25rem] border border-white/10 bg-[rgba(10,14,11,0.96)] p-8 shadow-[0_18px_60px_rgba(0,0,0,0.5)]">
          <div className="space-y-2">
            <h3 className="text-foreground text-xl font-bold">{title}</h3>
            <p className="text-muted-foreground text-sm">{body}</p>
          </div>
          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onCancel}
              className="border-glass-border text-muted-foreground hover:text-foreground rounded-full border px-4 py-2 text-sm font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy}
              className="rounded-full bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-60"
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
