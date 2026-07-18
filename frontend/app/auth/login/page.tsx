"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AverQelLogo from "@/app/components/ui/AverQelLogo";
import { useAuth } from "../../context/AuthContext";
import { getApiBaseUrl } from "../../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { login: setAuthData } = useAuth();
  const [formData, setFormData] = useState({ email: "", password: "" });
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Load remembered credentials on mount
  useEffect(() => {
    const savedEmail = localStorage.getItem("averqel_saved_email");
    const savedRemember = localStorage.getItem("averqel_remember") === "true";

    if (savedRemember) {
      setRememberMe(true);
      if (savedEmail) {
        setFormData((current) => ({
          ...current,
          email: savedEmail,
        }));
      }
      localStorage.removeItem("averqel_saved_pass");
    }
  }, []);

  // 2FA challenge state
  const [show2fa, setShow2fa] = useState(false);
  const [pendingToken, setPendingToken] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [verifying2fa, setVerifying2fa] = useState(false);

  const readApiErrorMessage = (data: unknown, fallback: string): string => {
    if (!data || typeof data !== "object") {
      return fallback;
    }
    const payload = data as { message?: unknown; error?: { message?: unknown } };
    if (typeof payload.error?.message === "string" && payload.error.message.trim()) {
      return payload.error.message;
    }
    if (typeof payload.message === "string" && payload.message.trim()) {
      return payload.message;
    }
    return fallback;
  };

  const safeReadJson = async (response: Response): Promise<unknown | null> => {
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      return null;
    }
    try {
      return await response.json();
    } catch {
      return null;
    }
  };

  const completeLogin = (data: {
    access_token: string;
    user: { user_id: string; tenant_id: string; roles: string[] };
  }) => {
    // Save credentials if Remember Me is checked
    if (rememberMe) {
      localStorage.setItem("averqel_saved_email", formData.email);
      localStorage.setItem("averqel_remember", "true");
    } else {
      localStorage.removeItem("averqel_saved_email");
      localStorage.setItem("averqel_remember", "false");
    }

    setAuthData(
      data.access_token,
      data.user.tenant_id,
      {
        id: data.user.user_id,
        email: formData.email,
        tenant_id: data.user.tenant_id,
        roles: data.user.roles,
      },
      rememberMe,
    );
    router.push("/dashboard");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 15_000);
      const response = await fetch(`${getApiBaseUrl()}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: formData.email, password: formData.password }),
        signal: controller.signal,
      });
      window.clearTimeout(timeout);

      const data = await safeReadJson(response);
      if (!response.ok) {
        throw new Error(
          readApiErrorMessage(
            data,
            response.status >= 500
              ? "The login service is temporarily unavailable."
              : "Invalid email or password.",
          ),
        );
      }

      if (!data || typeof data !== "object") {
        throw new Error("The login service returned an unexpected response.");
      }

      const pendingTokenValue =
        "pending_token" in data && typeof data.pending_token === "string"
          ? data.pending_token
          : null;

      if ("requires_2fa" in data && data.requires_2fa && pendingTokenValue) {
        setPendingToken(pendingTokenValue);
        setShow2fa(true);
        return;
      }

      completeLogin(
        data as {
          access_token: string;
          user: { user_id: string; tenant_id: string; roles: string[] };
        },
      );
    } catch (err: unknown) {
      const message =
        err instanceof DOMException && err.name === "AbortError"
          ? "Login timed out. Please check the server connection and try again."
          : err instanceof Error
            ? err.message
            : "Something went wrong.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleVerify2fa = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setVerifying2fa(true);

    try {
      const response = await fetch(`${getApiBaseUrl()}/auth/2fa/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ pending_token: pendingToken, code: totpCode }),
      });

      const data = await safeReadJson(response);
      if (!response.ok) {
        throw new Error(
          readApiErrorMessage(
            data,
            response.status >= 500
              ? "The authentication service is temporarily unavailable."
              : "Invalid authentication code.",
          ),
        );
      }

      if (!data || typeof data !== "object") {
        throw new Error("The authentication service returned an unexpected response.");
      }

      completeLogin(
        data as {
          access_token: string;
          user: { user_id: string; tenant_id: string; roles: string[] };
        },
      );
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      setError(message);
    } finally {
      setVerifying2fa(false);
    }
  };

  return (
    <div className="mesh-bg relative flex min-h-[100svh] items-center justify-center overflow-hidden px-4 sm:px-6">
      <div className="pointer-events-none absolute inset-0">
        <div className="bg-primary/10 absolute top-[20%] right-[-10%] h-[40%] w-[40%] rounded-full blur-[120px]" />
        <div className="bg-accent/10 absolute bottom-[20%] left-[-10%] h-[40%] w-[40%] rounded-full blur-[120px]" />
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
          {!show2fa ? (
            <>
              <h1 className="text-foreground mb-2 text-2xl font-bold sm:text-3xl">Welcome Back</h1>
              <p className="text-muted-foreground mb-8 text-sm">
                Log in to manage your document intelligence.
              </p>

              {error && (
                <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300">
                  {error}
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
                    placeholder="you@company.com"
                    autoComplete="username"
                    spellCheck={false}
                    autoCorrect="off"
                    autoCapitalize="none"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  />
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <label className="text-muted-foreground block text-xs font-semibold tracking-wider uppercase">
                      Password
                    </label>
                    <Link
                      href="#"
                      className="text-primary text-xs transition-colors hover:brightness-110"
                    >
                      Forgot password?
                    </Link>
                  </div>
                  <input
                    type="password"
                    required
                    className="ui-input w-full px-4 py-3"
                    placeholder="••••••••"
                    autoComplete="current-password"
                    spellCheck={false}
                    autoCorrect="off"
                    autoCapitalize="none"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <label className="flex cursor-pointer items-center gap-2 select-none">
                    <div className="relative flex items-center">
                      <input
                        type="checkbox"
                        checked={rememberMe}
                        onChange={(e) => setRememberMe(e.target.checked)}
                        className="peer border-glass-border bg-surface-1 checked:bg-primary checked:border-primary h-4 w-4 cursor-pointer appearance-none rounded border transition-all"
                      />
                      <svg
                        className="pointer-events-none absolute top-0 left-0 h-4 w-4 scale-0 text-white transition-transform peer-checked:scale-100"
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="4"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    </div>
                    <span className="text-muted-foreground text-xs font-medium">
                      Remember me on this device
                    </span>
                  </label>
                </div>

                <button type="submit" disabled={loading} className="btn-primary mt-2 w-full py-3.5">
                  {loading ? "Logging in..." : "Log In"}
                </button>
              </form>

              <p className="text-muted-foreground mt-8 text-center text-sm">
                Don&apos;t have an account?{" "}
                <Link
                  href="/auth/signup"
                  className="text-foreground hover:text-primary font-medium transition-colors"
                >
                  Sign up
                </Link>
              </p>
            </>
          ) : (
            <>
              <h1 className="text-foreground mb-2 text-2xl font-bold sm:text-3xl">
                Two-Factor Authentication
              </h1>
              <p className="text-muted-foreground mb-8 text-sm">
                Enter the 6-digit code from your authenticator app, or a backup code.
              </p>

              {error && (
                <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300">
                  {error}
                </div>
              )}

              <form onSubmit={handleVerify2fa} className="space-y-6">
                <div>
                  <label className="text-muted-foreground mb-2 block text-xs font-semibold tracking-wider uppercase">
                    Authentication Code
                  </label>
                  <input
                    type="text"
                    required
                    autoFocus
                    className="ui-input w-full px-4 py-3 text-center font-mono text-2xl tracking-[0.5em]"
                    placeholder="000000"
                    maxLength={16}
                    spellCheck={false}
                    autoCorrect="off"
                    autoComplete="one-time-code"
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value.replace(/\s/g, ""))}
                  />
                </div>

                <button
                  type="submit"
                  disabled={verifying2fa || totpCode.length < 6}
                  className="btn-primary mt-2 w-full py-3.5"
                >
                  {verifying2fa ? "Verifying..." : "Verify"}
                </button>
              </form>

              <button
                onClick={() => {
                  setShow2fa(false);
                  setTotpCode("");
                  setError("");
                }}
                className="text-muted-foreground hover:text-primary mt-6 block w-full text-center text-sm transition-colors"
              >
                Back to login
              </button>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}
