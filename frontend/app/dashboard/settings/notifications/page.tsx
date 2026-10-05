"use client";

import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { BellRing, Loader2, RefreshCw, Save } from "lucide-react";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";

type Category = { code: string; label: string; channels: ("in_app" | "email")[] };
type Preferences = {
  email_enabled: boolean;
  email_delivery_available: boolean;
  digest_frequency: "none" | "daily" | "weekly";
  timezone: string;
  preferences_configured: boolean;
  muted_domains: string[];
  categories: Category[];
};

async function responseError(response: Response, fallback: string) {
  try {
    const body = (await response.json()) as {
      detail?: string;
      message?: string;
      error?: { message?: string };
    };
    return body.error?.message || body.detail || body.message || fallback;
  } catch {
    return fallback;
  }
}

export default function NotificationSettingsPage() {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [baseline, setBaseline] = useState("");
  const emailAvailable = preferences?.email_delivery_available ?? false;
  const showEmailSettings = emailAvailable || Boolean(preferences?.email_enabled);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const response = await fetchWithAuth("/notifications/preferences");
      if (!response.ok)
        throw new Error(await responseError(response, "Settings could not be loaded."));
      const value = (await response.json()) as Preferences;
      if (!value.preferences_configured && typeof Intl !== "undefined") {
        value.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      }
      setPreferences(value);
      setBaseline(JSON.stringify(value));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Could not load notification settings.";
      setLoadError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  const save = async () => {
    if (!preferences || saving) return;
    setSaving(true);
    setSaved(false);
    try {
      const response = await fetchWithAuth("/notifications/preferences", {
        method: "PUT",
        body: JSON.stringify({
          email_enabled: preferences.email_enabled,
          digest_frequency: preferences.digest_frequency,
          timezone: preferences.timezone,
          muted_domains: preferences.muted_domains,
        }),
      });
      if (!response.ok)
        throw new Error(await responseError(response, "Settings could not be saved."));
      const savedPreferences = (await response.json()) as Preferences;
      setPreferences(savedPreferences);
      setBaseline(JSON.stringify(savedPreferences));
      setSaved(true);
      toast.success("Notification settings saved.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save notification settings.");
    } finally {
      setSaving(false);
    }
  };

  const toggleDomain = (domain: string) => {
    setSaved(false);
    setPreferences((current) =>
      current
        ? {
            ...current,
            muted_domains: current.muted_domains.includes(domain)
              ? current.muted_domains.filter((item) => item !== domain)
              : [...current.muted_domains, domain],
          }
        : current,
    );
  };

  return (
    <div className="dashboard-theme-scope w-full min-w-0 space-y-6">
      <DashboardSectionHeader
        title="Notification Preferences"
        subtitle={
          emailAvailable
            ? "Choose which updates appear in your workspace and whether they arrive by email"
            : "Choose which updates appear in your in-app notification center"
        }
        icon={BellRing}
        backHref="/dashboard/settings"
        backLabel="Back"
      />
      {loading ? (
        <div
          className="theme-panel flex min-h-56 items-center justify-center rounded-2xl"
          role="status"
        >
          <Loader2 className="text-primary animate-spin" />
          <span className="sr-only">Loading notification preferences</span>
        </div>
      ) : loadError ? (
        <section className="theme-panel w-full space-y-3 rounded-2xl p-6" role="alert">
          <h2 className="text-foreground text-sm font-bold">Preferences could not be loaded</h2>
          <p className="text-muted-foreground text-sm">{loadError}</p>
          <button
            onClick={() => void load()}
            className="border-border text-foreground inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm"
          >
            <RefreshCw size={15} /> Try again
          </button>
        </section>
      ) : preferences ? (
        <section className="theme-panel w-full space-y-7 rounded-2xl p-6">
          {showEmailSettings && (
            <div>
              <h2 className="text-foreground text-sm font-bold">
                {emailAvailable ? "Email delivery" : "Email delivery unavailable"}
              </h2>
              <p className="text-muted-foreground mt-1 text-xs">
                {emailAvailable
                  ? "In-app updates are always available. Email uses the address on your account."
                  : "Email is unavailable in this deployment. Turn off your saved email opt-in here; in-app notifications remain available."}
              </p>
              <label className="text-foreground mt-4 flex items-center gap-3 text-sm">
                <input
                  type="checkbox"
                  checked={preferences.email_enabled}
                  disabled={!emailAvailable && !preferences.email_enabled}
                  onChange={(event) => {
                    if (!emailAvailable && event.target.checked) return;
                    setSaved(false);
                    setPreferences({ ...preferences, email_enabled: event.target.checked });
                  }}
                />
                Send notification email
              </label>
              {emailAvailable && (
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <label className="text-foreground grid gap-2 text-xs font-semibold">
                    Email cadence
                    <select
                      value={preferences.digest_frequency}
                      disabled={!preferences.email_enabled}
                      onChange={(event) => {
                        setSaved(false);
                        setPreferences({
                          ...preferences,
                          digest_frequency: event.target.value as Preferences["digest_frequency"],
                        });
                      }}
                      className="border-border bg-background rounded-lg border px-3 py-2"
                    >
                      <option value="none">As events happen</option>
                      <option value="daily">Daily digest</option>
                      <option value="weekly">Weekly digest</option>
                    </select>
                  </label>
                  <label className="text-foreground grid gap-2 text-xs font-semibold">
                    Digest time zone
                    <input
                      value={preferences.timezone}
                      disabled={
                        !preferences.email_enabled || preferences.digest_frequency === "none"
                      }
                      onChange={(event) => {
                        setSaved(false);
                        setPreferences({ ...preferences, timezone: event.target.value });
                      }}
                      list="notification-timezones"
                      className="border-border bg-background rounded-lg border px-3 py-2"
                      aria-describedby="notification-timezone-help"
                    />
                    <datalist id="notification-timezones">
                      <option value="UTC" />
                      <option value="Europe/Berlin" />
                      <option value="America/New_York" />
                      <option value="America/Los_Angeles" />
                      <option value="Asia/Kolkata" />
                    </datalist>
                    <span
                      id="notification-timezone-help"
                      className="text-muted-foreground font-normal"
                    >
                      Daily digests arrive around 08:00 local time; weekly digests arrive Monday
                      around 08:00.
                    </span>
                  </label>
                </div>
              )}
            </div>
          )}
          <div>
            <h2 className="text-foreground text-sm font-bold">
              {emailAvailable ? "Muted categories" : "In-app notification categories"}
            </h2>
            <p className="text-muted-foreground mt-1 text-xs">
              {emailAvailable
                ? "Check a category to mute it. Muted notifications are hidden in-app and excluded from future email. This does not delete source records or collection history."
                : "Check a category to mute it. Muted notifications are hidden from your in-app notification center. This does not delete source records or collection history."}
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {preferences.categories.map((category) => (
                <label
                  key={category.code}
                  className="border-border bg-background/30 text-foreground hover:bg-surface-1/60 flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 text-xs transition-colors"
                >
                  <input
                    type="checkbox"
                    aria-label={`Mute ${category.label} notifications`}
                    checked={preferences.muted_domains.includes(category.code)}
                    onChange={() => toggleDomain(category.code)}
                    className="accent-primary h-4 w-4 shrink-0 cursor-pointer"
                  />
                  <span className="min-w-0 flex-1 font-medium">{category.label}</span>
                  <span
                    className={`rounded-full px-2 py-1 text-[10px] font-semibold ${
                      preferences.muted_domains.includes(category.code)
                        ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
                        : "bg-success/10 text-success"
                    }`}
                  >
                    {preferences.muted_domains.includes(category.code) ? "Muted" : "Active"}
                  </span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => void save()}
              disabled={saving || baseline === JSON.stringify(preferences)}
              className="bg-primary text-primary-foreground inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
            >
              {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
              {saving ? "Saving…" : "Save preferences"}
            </button>
            {saved && (
              <span className="text-muted-foreground text-xs" role="status">
                Saved
              </span>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}
