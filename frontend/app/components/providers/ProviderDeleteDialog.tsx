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
      <div className="provider-delete-dialog-frame border-glass-border bg-foreground/20 ring-foreground/5 relative flex h-full w-full items-center justify-center overflow-hidden rounded-[2.5rem] border shadow-[0_28px_90px_rgba(0,0,0,0.6)] ring-1 backdrop-blur-[2px] dark:border-white/10 dark:bg-[rgba(3,6,4,0.82)] dark:ring-white/5">
        <div className="provider-delete-dialog-panel border-glass-border bg-surface-0 w-full max-w-sm space-y-5 rounded-[2.25rem] border p-8 shadow-[0_18px_60px_rgba(0,0,0,0.14)] dark:border-white/10 dark:bg-[rgba(10,14,11,0.96)] dark:shadow-[0_18px_60px_rgba(0,0,0,0.5)]">
          <div className="space-y-2">
            <h3 className="text-foreground text-xl font-bold">{title}</h3>
            <p className="text-muted-foreground text-sm">{body}</p>
          </div>
          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onCancel}
              className="border-glass-border bg-surface-1 text-foreground hover:bg-surface-2 dark:text-muted-foreground dark:hover:text-foreground rounded-lg border px-4 py-2 text-sm font-semibold dark:bg-transparent dark:hover:bg-transparent"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy}
              className="bg-danger text-primary-foreground hover:bg-danger/90 rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-60 dark:bg-red-600 dark:text-white dark:hover:bg-red-500"
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
