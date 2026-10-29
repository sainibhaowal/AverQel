"use client";

import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Cable,
  Check,
  FileSearch,
  FileText,
  Moon,
  Sparkles,
  Sun,
} from "lucide-react";
import { useAuth } from "@/app/context/AuthContext";
import { useTheme } from "@/app/context/ThemeContext";
import DeepSpaceMark from "@/app/components/ui/DeepSpaceMark";
import QelConnectMark from "@/app/components/ui/QelConnectMark";
import AverQelLogo from "@/app/components/ui/AverQelLogo";
import ProfileIdentityEditor, {
  type ProfileIdentityDraft,
} from "@/app/components/profile/ProfileIdentityEditor";
import QuickProviderSetup from "./QuickProviderSetup";
import { fetchWithAuth } from "@/lib/api";

const SLIDES = ["Welcome", "Your workspace", "Make it yours", "AI setup"];

async function responseError(response: Response, fallback: string): Promise<string> {
  try {
    const data = (await response.json()) as {
      detail?: string;
      message?: string;
      error?: { message?: string };
    };
    return data.error?.message || data.detail || data.message || fallback;
  } catch {
    return fallback;
  }
}

export default function WelcomeFlow() {
  const router = useRouter();
  const { user, profileReady, updateUserProfile } = useAuth();
  const { theme, setTheme } = useTheme();
  const [step, setStep] = useState(0);
  const [completing, setCompleting] = useState(false);
  const [providerSaving, setProviderSaving] = useState(false);
  const [error, setError] = useState("");
  const [stepDirection, setStepDirection] = useState<1 | -1>(1);
  const prefersReducedMotion = useReducedMotion();

  const open = profileReady && user?.onboarding_completed === false;

  const saveIdentity = async (draft: ProfileIdentityDraft) => {
    const response = (await fetchWithAuth("/auth/profile", {
      method: "PUT",
      body: JSON.stringify(draft),
    })) as Response;
    if (!response.ok) {
      throw new Error(await responseError(response, "Your profile changes could not be saved."));
    }
    const profile = (await response.json()) as {
      display_name?: string | null;
      avatar?: string | null;
    };
    updateUserProfile({
      display_name: profile.display_name ?? null,
      avatar: profile.avatar ?? null,
    });
  };

  const finish = async (destination?: string) => {
    setCompleting(true);
    setError("");
    try {
      const response = (await fetchWithAuth("/auth/profile", {
        method: "PUT",
        body: JSON.stringify({ onboarding_completed: true }),
      })) as Response;
      if (!response.ok) {
        throw new Error(
          await responseError(response, "AverQel could not save that this setup is finished."),
        );
      }
      updateUserProfile({ onboarding_completed: true });
      if (destination) router.push(destination);
    } catch (finishError) {
      setError(
        finishError instanceof Error ? finishError.message : "Setup could not be completed.",
      );
    } finally {
      setCompleting(false);
    }
  };

  if (!open || !user) return null;

  const goNext = () => {
    setError("");
    setStepDirection(1);
    setStep((current) => Math.min(SLIDES.length - 1, current + 1));
  };

  const goBack = () => {
    setError("");
    setStepDirection(-1);
    setStep((current) => Math.max(0, current - 1));
  };

  const slideMotion = prefersReducedMotion
    ? {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: { duration: 0.14 },
      }
    : {
        initial: { opacity: 0, x: stepDirection * 22, filter: "blur(3px)" },
        animate: { opacity: 1, x: 0, filter: "blur(0px)" },
        exit: { opacity: 0, x: stepDirection * -16, filter: "blur(2px)" },
        transition: { duration: 0.3, ease: [0.22, 1, 0.36, 1] as const },
      };

  return (
    <div className="welcome-flow-backdrop fixed inset-0 z-[100] flex items-center justify-center p-3 backdrop-blur-xl sm:p-6">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="welcome-flow-title"
        className="welcome-flow-dialog relative flex max-h-[min(900px,calc(100svh-1.5rem))] w-full max-w-4xl flex-col overflow-hidden rounded-[1.75rem]"
      >
        <header className="flex items-center justify-between gap-4 border-b border-white/[0.07] px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <AverQelLogo size="footer" showWordmark disableAnimation />
            <span className="hidden rounded-lg border border-teal-300/15 bg-teal-300/[0.06] px-2.5 py-1 text-[9px] font-semibold tracking-[0.12em] text-teal-100/70 uppercase sm:inline-flex">
              Welcome
            </span>
          </div>
          <button
            type="button"
            onClick={() => void finish()}
            disabled={completing || providerSaving}
            className="rounded-lg px-3 py-2 text-xs font-medium text-slate-400 transition hover:bg-white/5 hover:text-white disabled:opacity-50"
          >
            Skip setup
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-9 sm:py-8">
          <div
            className="mb-7 flex items-center gap-2"
            aria-label={`Slide ${step + 1} of ${SLIDES.length}`}
          >
            {SLIDES.map((label, index) => (
              <div key={label} className="flex min-w-0 flex-1 items-center gap-2">
                <span
                  className={`h-1.5 flex-1 rounded-sm transition-colors ${index <= step ? "bg-teal-300" : "bg-white/10"}`}
                />
                {index === step ? (
                  <span className="hidden text-[10px] font-medium text-slate-300 sm:inline">
                    {label}
                  </span>
                ) : null}
              </div>
            ))}
          </div>

          <AnimatePresence mode="wait" initial>
            <motion.div key={step} {...slideMotion} className="will-change-transform">
              {step === 0 ? (
                <div className="mx-auto max-w-2xl py-3 text-center sm:py-7">
                  <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-teal-200/15 bg-teal-300/[0.07] text-teal-100">
                    <Sparkles size={28} strokeWidth={1.5} />
                  </div>
                  <p className="text-[10px] font-semibold tracking-[0.22em] text-teal-200/70 uppercase">
                    A calmer place for complex work
                  </p>
                  <h1
                    id="welcome-flow-title"
                    className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl"
                  >
                    Welcome to AverQel
                    {user.display_name?.trim() ? `, ${user.display_name.trim()}` : ""}
                  </h1>
                  <p className="mx-auto mt-4 max-w-xl text-sm leading-6 text-slate-400 sm:text-base">
                    Bring your documents, AI models, and connected tools into one focused workspace.
                    Choose what to set up now; you can change it later.
                  </p>
                  <div className="mt-8 grid gap-3 text-left sm:grid-cols-2">
                    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4">
                      <div className="flex items-center gap-3">
                        <DeepSpaceMark size={22} />
                        <span className="text-sm font-semibold text-white">DeepSpace</span>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-slate-400">
                        Research, draft, and work through ideas with connected tools.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4">
                      <div className="flex items-center gap-3">
                        <QelConnectMark size={22} />
                        <span className="text-sm font-semibold text-white">Your workspace</span>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-slate-400">
                        Organize source material, grounded answers, Qel Connect spaces, and provider
                        connections.
                      </p>
                    </div>
                  </div>
                </div>
              ) : null}

              {step === 1 ? (
                <div>
                  <div className="max-w-2xl">
                    <h1
                      id="welcome-flow-title"
                      className="text-2xl font-semibold tracking-tight text-white sm:text-3xl"
                    >
                      Your work, in one place
                    </h1>
                    <p className="mt-3 text-sm leading-6 text-slate-400">
                      Start with the part that helps today. Feature access and beta status are shown
                      in the workspace.
                    </p>
                  </div>
                  <div className="mt-7 grid gap-3 sm:grid-cols-2">
                    {[
                      {
                        title: "Documents Hub",
                        text: "Add and organize source files.",
                        icon: FileText,
                      },
                      {
                        title: "Grounded Query",
                        text: "Ask focused questions about sources you can access.",
                        icon: FileSearch,
                      },
                      {
                        title: "Qel Connect",
                        text: "Share selected work with your collaborators.",
                        icon: QelConnectMark,
                      },
                      {
                        title: "MCP Servers",
                        text: "Connect supported external tools when you need them.",
                        icon: Cable,
                      },
                    ].map(({ title, text, icon: Icon }) => (
                      <div
                        key={title}
                        className="flex items-start gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4"
                      >
                        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-300/[0.08] text-teal-200">
                          <Icon size={17} />
                        </span>
                        <div>
                          <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
                          <p className="mt-1 text-xs leading-5 text-slate-400">{text}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="mt-5 rounded-xl border border-amber-200/10 bg-amber-100/[0.035] px-4 py-3 text-xs leading-5 text-amber-100/75">
                    AverQel is in beta. Features that are still evolving are marked in the app; some
                    tools may depend on your account role or deployment.
                  </p>
                </div>
              ) : null}

              {step === 2 ? (
                <div className="grid gap-7 lg:grid-cols-[minmax(0,1fr)_210px]">
                  <div>
                    <h1
                      id="welcome-flow-title"
                      className="text-2xl font-semibold tracking-tight text-white sm:text-3xl"
                    >
                      Make it feel like yours
                    </h1>
                    <p className="mt-3 mb-6 text-sm leading-6 text-slate-400">
                      Choose a display name and avatar. Your sign-in email and account role are not
                      changed.
                    </p>
                    <ProfileIdentityEditor
                      displayName={user.display_name}
                      avatar={user.avatar}
                      submitLabel="Save and continue"
                      onSave={saveIdentity}
                      onSaved={goNext}
                    />
                  </div>
                  <aside className="h-fit rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4">
                    <h2 className="text-sm font-semibold text-white">Workspace appearance</h2>
                    <p className="mt-1 text-xs leading-5 text-slate-400">
                      You can change this any time from the top bar.
                    </p>
                    <div className="mt-4 grid gap-2">
                      {(
                        [
                          { value: "dark", title: "Dark", icon: Moon },
                          { value: "light", title: "Light", icon: Sun },
                        ] as const
                      ).map(({ value, title, icon: Icon }) => (
                        <button
                          key={value}
                          type="button"
                          onClick={() => setTheme(value)}
                          aria-pressed={theme === value}
                          className={`flex h-11 items-center justify-between rounded-xl border px-3 text-xs font-medium transition ${theme === value ? "border-teal-300/40 bg-teal-300/[0.08] text-teal-100" : "border-white/10 text-slate-300 hover:bg-white/[0.04]"}`}
                        >
                          <span className="flex items-center gap-2">
                            <Icon size={15} /> {title}
                          </span>
                          {theme === value ? <Check size={14} /> : null}
                        </button>
                      ))}
                    </div>
                  </aside>
                </div>
              ) : null}

              {step === 3 ? (
                <div>
                  <h1
                    id="welcome-flow-title"
                    className="text-2xl font-semibold tracking-tight text-white sm:text-3xl"
                  >
                    Connect the AI you want to use
                  </h1>
                  <p className="mt-3 mb-6 max-w-2xl text-sm leading-6 text-slate-400">
                    This step is optional. Add a provider now, or finish setup and do it later in
                    Settings. Credentials use the existing encrypted provider storage.
                  </p>
                  <QuickProviderSetup
                    onConfigured={() => setError("")}
                    onBusyChange={setProviderSaving}
                    onOpenSettings={() => void finish("/dashboard/settings/providers")}
                  />
                </div>
              ) : null}
            </motion.div>
          </AnimatePresence>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.07] px-5 py-4 sm:px-8">
          <p className="text-xs text-slate-500">
            Step {step + 1} of {SLIDES.length}
          </p>
          <div className="flex items-center gap-2">
            {step > 0 ? (
              <button
                type="button"
                onClick={goBack}
                className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-white/10 px-3 text-xs font-medium text-slate-300 hover:bg-white/5"
              >
                <ArrowLeft size={14} /> Back
              </button>
            ) : null}
            {step === 2 ? null : step < SLIDES.length - 1 ? (
              <button
                type="button"
                onClick={goNext}
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-teal-300 px-4 text-xs font-semibold text-slate-950 transition hover:bg-teal-200"
              >
                Continue <ArrowRight size={14} />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void finish()}
                disabled={completing || providerSaving}
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-teal-300 px-4 text-xs font-semibold text-slate-950 transition hover:bg-teal-200 disabled:cursor-wait disabled:opacity-60"
              >
                {completing ? "Saving…" : "Start using AverQel"} <ArrowRight size={14} />
              </button>
            )}
          </div>
          {error ? (
            <p role="alert" className="w-full text-right text-xs text-red-300">
              {error}
            </p>
          ) : null}
        </footer>
      </section>
    </div>
  );
}
