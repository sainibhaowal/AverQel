"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { BellRing, Loader2, Save } from "lucide-react";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";

const domains = [
  "support",
  "feedback",
  "query",
  "provider",
  "storage",
  "plan",
  "system",
  "collection_moderation",
] as const;
type Domain = (typeof domains)[number];
type Preferences = {
  email_enabled: boolean;
  email_delivery_available: boolean;
  digest_frequency: "none" | "daily" | "weekly";
  muted_domains: Domain[];
};

export default function NotificationSettingsPage() {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    void fetchWithAuth("/notifications/preferences")
      .then(async (response) => {
        if (!response.ok) throw new Error(`Settings could not be loaded (${response.status})`);
        const value = (await response.json()) as Preferences;
        if (active) setPreferences(value);
      })
      .catch((error) => {
        console.error(error);
        toast.error("Could not load notification settings.");
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const save = async () => {
    if (!preferences) return;
    setSaving(true);
    try {
      const response = await fetchWithAuth("/notifications/preferences", {
        method: "PUT",
        body: JSON.stringify({
          email_enabled: preferences.email_enabled,
          digest_frequency: preferences.digest_frequency,
          muted_domains: preferences.muted_domains,
        }),
      });
      if (!response.ok) throw new Error(`Settings could not be saved (${response.status})`);
      setPreferences((await response.json()) as Preferences);
      toast.success("Notification settings saved.");
    } catch (error) {
      console.error(error);
      toast.error("Could not save notification settings.");
    } finally {
      setSaving(false);
    }
  };

  const toggleDomain = (domain: Domain) => {
    if (!preferences) return;
    setPreferences({
      ...preferences,
      muted_domains: preferences.muted_domains.includes(domain)
        ? preferences.muted_domains.filter((item) => item !== domain)
        : [...preferences.muted_domains, domain],
    });
  };

  return (
    <div className="dashboard-theme-scope w-full space-y-6">
      <DashboardSectionHeader
        title="Notification preferences"
        subtitle="Choose how operational updates reach you"
        icon={BellRing}
        backHref="/dashboard/settings"
        backLabel="Settings"
      />
      {loading || !preferences ? (
        <div className="theme-panel flex min-h-56 items-center justify-center rounded-2xl">
          <Loader2 className="text-primary animate-spin" />
        </div>
      ) : (
        <section className="theme-panel max-w-3xl space-y-7 rounded-2xl p-6">
          <div>
            <h2 className="text-foreground text-sm font-bold">Email delivery</h2>
            <p className="text-muted-foreground mt-1 text-xs">
              In-app notifications remain available. Email is sent through the deployment’s
              configured SMTP service.
            </p>
            <label className="text-foreground mt-4 flex items-center gap-3 text-sm">
              <input
                type="checkbox"
                checked={preferences.email_enabled}
                disabled={!preferences.email_delivery_available}
                onChange={(event) =>
                  setPreferences({ ...preferences, email_enabled: event.target.checked })
                }
              />
              Send notification email
            </label>
            {!preferences.email_delivery_available && (
              <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                Email delivery is not enabled for this deployment yet.
              </p>
            )}
            <label className="text-foreground mt-4 grid max-w-sm gap-2 text-xs font-semibold">
              Email cadence
              <select
                value={preferences.digest_frequency}
                disabled={!preferences.email_enabled}
                onChange={(event) =>
                  setPreferences({
                    ...preferences,
                    digest_frequency: event.target.value as Preferences["digest_frequency"],
                  })
                }
                className="border-border bg-background rounded-lg border px-3 py-2"
              >
                <option value="none">As events happen</option>
                <option value="daily">Daily digest</option>
                <option value="weekly">Weekly digest</option>
              </select>
            </label>
          </div>
          <div>
            <h2 className="text-foreground text-sm font-bold">Muted categories</h2>
            <p className="text-muted-foreground mt-1 text-xs">
              Muted categories stay stored, are hidden from the in-app list, and are omitted from
              email delivery.
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {domains.map((domain) => (
                <label
                  key={domain}
                  className="border-border text-foreground flex items-center gap-2 rounded-lg border px-3 py-2 text-xs capitalize"
                >
                  <input
                    type="checkbox"
                    checked={preferences.muted_domains.includes(domain)}
                    onChange={() => toggleDomain(domain)}
                  />
                  {domain.replace("_", " ")}
                </label>
              ))}
            </div>
          </div>
          <button
            onClick={() => void save()}
            disabled={saving}
            className="bg-primary text-primary-foreground inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
          >
            <Save size={15} />
            {saving ? "Saving…" : "Save preferences"}
          </button>
        </section>
      )}
    </div>
  );
}
