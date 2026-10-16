"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, ChevronRight, CircleUserRound, KeyRound, ShieldCheck } from "lucide-react";
import { useAuth } from "@/app/context/AuthContext";
import { getRoleLabel } from "@/lib/roles";

function initials(name: string): string {
  return name.trim().slice(0, 1).toUpperCase() || "U";
}

export default function AccountProfileMenu() {
  const { user, profileReady } = useAuth();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !menuRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  if (!user) return null;

  const displayName = user.display_name?.trim() || user.email.split("@")[0] || "Account";
  const role = user.roles[0] ? getRoleLabel(user.roles[0]) : "User";
  const status = user.account_status || "Status unavailable";

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        aria-label={`Account menu for ${displayName}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="group hover:bg-muted/70 flex max-w-[min(18rem,46vw)] items-center gap-2 rounded-xl px-1.5 py-1 transition-colors"
      >
        <span className="text-foreground hidden min-w-0 flex-col items-end sm:flex">
          <span className="max-w-[12rem] truncate text-xs font-semibold">{displayName}</span>
          <span className="text-primary text-[9px] font-bold tracking-[0.14em] uppercase">
            {role}
          </span>
        </span>
        <span className="dashboard-user-avatar relative inline-flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full border text-sm font-bold">
          {user.avatar ? (
            // OAuth avatars and user-uploaded images are rendered as image resources only.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={user.avatar} alt="" className="absolute inset-0 h-full w-full object-cover" />
          ) : (
            <span className="dashboard-user-avatar-letter relative z-10">
              {initials(displayName)}
            </span>
          )}
          <span className="dashboard-user-avatar-status" aria-hidden="true" />
        </span>
      </button>

      {open ? (
        <section
          role="dialog"
          aria-label="Account information"
          className="theme-panel-strong !absolute top-[calc(100%+0.65rem)] right-0 z-50 w-[min(22rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border p-4 shadow-2xl"
        >
          <div className="flex items-start gap-3">
            <span className="bg-primary/10 text-primary border-primary/20 flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full border">
              {user.avatar ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={user.avatar} alt="" className="h-full w-full object-cover" />
              ) : (
                <span className="font-semibold">{initials(displayName)}</span>
              )}
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-foreground truncate text-sm font-semibold">{displayName}</h2>
              <p className="text-muted-foreground mt-0.5 truncate text-xs">{user.email}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="bg-primary/10 text-primary rounded-md px-2 py-1 text-[10px] font-semibold">
                  {role}
                </span>
                {status ? (
                  <span
                    className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-semibold ${status === "active" ? "bg-emerald-400/10 text-emerald-300" : "bg-amber-400/10 text-amber-300"}`}
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                    {status}
                  </span>
                ) : null}
              </div>
            </div>
          </div>

          <div className="border-glass-border mt-4 space-y-2 border-t pt-3">
            <div className="text-muted-foreground flex items-center justify-between gap-3 text-xs">
              <span className="inline-flex items-center gap-2">
                <ShieldCheck size={14} /> Two-step verification
              </span>
              <span className="text-foreground inline-flex items-center gap-1 font-medium">
                {profileReady ? (
                  user.totp_enabled === true ? (
                    <>
                      <Check size={13} className="text-emerald-400" /> Enabled
                    </>
                  ) : user.totp_enabled === false ? (
                    "Not enabled"
                  ) : (
                    "Unavailable"
                  )
                ) : (
                  "Checking…"
                )}
              </span>
            </div>
            <p className="text-muted-foreground flex items-center gap-2 text-xs">
              <CircleUserRound size={14} /> Account email and role are managed by AverQel.
            </p>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2">
            <Link
              href="/dashboard/settings/profile"
              onClick={() => setOpen(false)}
              className="theme-chip inline-flex h-10 items-center justify-between gap-2 rounded-xl px-3 text-xs font-semibold"
            >
              Profile <ChevronRight size={14} />
            </Link>
            <Link
              href="/dashboard/settings/providers"
              onClick={() => setOpen(false)}
              className="theme-chip inline-flex h-10 items-center justify-between gap-2 rounded-xl px-3 text-xs font-semibold"
            >
              <span className="inline-flex items-center gap-1.5">
                <KeyRound size={13} /> Providers
              </span>
              <ChevronRight size={14} />
            </Link>
          </div>
        </section>
      ) : null}
    </div>
  );
}
