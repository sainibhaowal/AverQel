"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AverQelLogo from "@/app/components/ui/AverQelLogo";
import { getApiBaseUrl } from "../../../lib/api";

function getPasswordStrength(pw: string): {
  score: number;
  label: string;
  color: string;
  checks: { label: string; met: boolean }[];
} {
  const checks = [
    { label: "At least 8 characters", met: pw.length >= 8 },
    { label: "Uppercase letter", met: /[A-Z]/.test(pw) },
    { label: "Lowercase letter", met: /[a-z]/.test(pw) },
    { label: "Number", met: /\d/.test(pw) },
    { label: "Special character", met: /[^A-Za-z0-9]/.test(pw) },
  ];
  const score = checks.filter((c) => c.met).length;
  const label = score <= 2 ? "Weak" : score <= 3 ? "Fair" : score <= 4 ? "Good" : "Strong";
  const color =
    score <= 2
      ? "bg-red-500"
      : score <= 3
        ? "bg-yellow-500"
        : score <= 4
          ? "bg-primary"
          : "bg-green-500";
  return { score, label, color, checks };
}

export default function SignupPage() {
  const router = useRouter();
  const [formData, setFormData] = useState({ email: "", password: "", confirmPassword: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const strength = getPasswordStrength(formData.password);

  const readApiErrorMessage = (data: unknown, fallback: string): string => {
    if (!data || typeof data !== "object") {
      return fallback;
    }
    const payload = data as {
      message?: unknown;
      error?: { message?: unknown; code?: unknown };
    };
    if (payload.error?.code === "USER_ALREADY_EXISTS") {
      return "An account already exists for that email. Log in instead.";
    }
    if (typeof payload.error?.message === "string" && payload.error.message.trim()) {
      return payload.error.message;
    }
    if (typeof payload.message === "string" && payload.message.trim()) {
      return payload.message;
    }
    return fallback;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    if (formData.password !== formData.confirmPassword) {
      setError("Passwords do not match.");
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(`${getApiBaseUrl()}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: formData.email, password: formData.password }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(readApiErrorMessage(data, "Registration failed."));
      }

      setSuccess(true);
      setTimeout(() => router.push("/auth/login"), 1800);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mesh-bg relative flex min-h-[100svh] items-center justify-center overflow-hidden px-4 sm:px-6">
      <div className="pointer-events-none absolute inset-0">
        <div className="bg-primary/10 absolute top-[-10%] left-[-10%] h-[40%] w-[40%] rounded-full blur-[120px]" />
        <div className="absolute right-[-10%] bottom-[-10%] h-[40%] w-[40%] rounded-full bg-purple-500/10 blur-[120px]" />
      </div>

      <motion.div
        className="relative z-10 w-full max-w-md"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
      >
        <div className="mb-10 flex justify-center">
          <Link href="/">
            <AverQelLogo size="hero" />
          </Link>
        </div>

        <div className="card-elevated p-6 sm:p-8 md:p-10">
          <h1 className="text-foreground mb-2 text-2xl font-bold sm:text-3xl">Create Account</h1>
          <p className="text-muted-foreground mb-8 text-sm">
            Join AverQel and start your personal search engine.
          </p>

          {error && (
            <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300">
              {error}
            </div>
          )}

          {success && (
            <div className="mb-6 rounded-lg border border-green-500/30 bg-green-500/10 p-3 text-sm text-green-700 dark:text-green-300">
              Registration successful. Redirecting to login...
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label className="text-muted-foreground mb-2 block text-xs font-semibold tracking-wider uppercase">
                Email Address
              </label>
              <input
                type="email"
                required
                className="ui-input w-full px-4 py-3"
                placeholder="you@example.com"
                autoComplete="username"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="none"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="text-muted-foreground mb-2 block text-xs font-semibold tracking-wider uppercase">
                  Password
                </label>
                <input
                  type="password"
                  required
                  minLength={1}
                  className="ui-input w-full px-4 py-3"
                  placeholder="••••••••"
                  autoComplete="new-password"
                  spellCheck={false}
                  autoCorrect="off"
                  autoCapitalize="none"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                />
              </div>
              <div>
                <label className="text-muted-foreground mb-2 block text-xs font-semibold tracking-wider uppercase">
                  Confirm
                </label>
                <input
                  type="password"
                  required
                  className="ui-input w-full px-4 py-3"
                  placeholder="••••••••"
                  autoComplete="new-password"
                  spellCheck={false}
                  autoCorrect="off"
                  autoCapitalize="none"
                  value={formData.confirmPassword}
                  onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                />
              </div>
            </div>

            {formData.password && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="bg-muted h-1.5 flex-1 overflow-hidden rounded-full">
                    <div
                      className={`h-full rounded-full transition-all ${strength.color}`}
                      style={{ width: `${(strength.score / 5) * 100}%` }}
                    />
                  </div>
                  <span
                    className={`text-[10px] font-bold tracking-widest uppercase ${strength.score <= 2 ? "text-red-500" : strength.score <= 3 ? "text-yellow-500" : strength.score <= 4 ? "text-primary" : "text-green-500"}`}
                  >
                    {strength.label}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
                  {strength.checks.map((c) => (
                    <span
                      key={c.label}
                      className={`text-[10px] ${c.met ? "text-green-500" : "text-muted-foreground"}`}
                    >
                      {c.met ? "\u2713" : "\u2022"} {c.label}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <button type="submit" disabled={loading} className="btn-primary mt-2 w-full py-3.5">
              {loading ? "Creating..." : "Sign Up"}
            </button>
          </form>

          <div className="mt-5 rounded-xl border border-white/8 bg-white/[0.03] p-4">
            <p className="text-muted-foreground text-xs leading-6">
              By creating an account, you agree to the{" "}
              <Link
                href="/legal/terms"
                className="text-foreground hover:text-primary font-semibold"
              >
                Terms of Service
              </Link>{" "}
              and acknowledge the{" "}
              <Link
                href="/legal/privacy"
                className="text-foreground hover:text-primary font-semibold"
              >
                Privacy Policy
              </Link>
              . AverQel uses account and security data to run the service. Workspace content such as
              documents and queries is stored to deliver the product and should not be accessed
              casually outside support, security, abuse, or legal handling.
            </p>
          </div>

          <p className="text-muted-foreground mt-8 text-center text-sm">
            Already have an account?{" "}
            <Link
              href="/auth/login"
              className="text-foreground hover:text-primary font-medium transition-colors"
            >
              Log in
            </Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
