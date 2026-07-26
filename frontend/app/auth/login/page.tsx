"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Github } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AverQelLogo from "@/app/components/ui/AverQelLogo";
import { useAuth } from "../../context/AuthContext";
import { getApiBaseUrl } from "../../../lib/api";

function GoogleMark() {
  return (
    <svg aria-hidden="true" className="h-5 w-5 shrink-0" viewBox="0 0 24 24" role="img">
      <path
        fill="#4285F4"
        d="M21.35 12.27c0-.72-.06-1.42-.18-2.09H12v3.96h5.24a4.48 4.48 0 0 1-1.94 2.94v2.45h3.14c1.84-1.7 2.91-4.2 2.91-7.26Z"
      />
      <path
        fill="#34A853"
        d="M12 21.75c2.63 0 4.84-.87 6.45-2.36l-3.14-2.45c-.87.58-1.98.92-3.31.92-2.54 0-4.69-1.72-5.46-4.03H3.3v2.53A9.74 9.74 0 0 0 12 21.75Z"
      />
      <path
        fill="#FBBC05"
        d="M6.54 13.83A5.85 5.85 0 0 1 6.23 12c0-.64.11-1.26.31-1.83V7.64H3.3A9.75 9.75 0 0 0 2.25 12c0 1.57.38 3.05 1.05 4.36l3.24-2.53Z"
      />
      <path
        fill="#EA4335"
        d="M12 6.14c1.43 0 2.71.49 3.72 1.45l2.79-2.79C16.84 3.23 14.63 2.25 12 2.25a9.74 9.74 0 0 0-8.7 5.39l3.24 2.53C7.31 7.86 9.46 6.14 12 6.14Z"
      />
    </svg>
  );
}

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

  // OAuth callbacks return here after the server has exchanged the provider
  // code and set the secure refresh cookie.
  useEffect(() => {
    const oauthResult = new URLSearchParams(window.location.search).get("oauth");
    if (!oauthResult) {
      return;
    }

    if (oauthResult === "2fa") {
      setOauthTwoFactor(true);
      setShow2fa(true);
      setError("Complete two-factor authentication to finish signing in.");
      router.replace("/auth/login");
      return;
    }

    if (oauthResult !== "success") {
      setError("Social login could not be completed. Please try again.");
      router.replace("/auth/login");
      return;
    }

    let cancelled = false;
    const finishOAuthLogin = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`${getApiBaseUrl()}/auth/refresh`, {
          method: "POST",
          credentials: "include",
        });
        const data = await safeReadJson(response);
        if (!response.ok || !data || typeof data !== "object" || !("access_token" in data)) {
          throw new Error("The social login session could not be established.");
        }
        const accessToken = (data as { access_token: unknown }).access_token;
        if (typeof accessToken !== "string" || !accessToken) {
          throw new Error("The social login session returned an invalid token.");
        }
        const profileResponse = await fetch(`${getApiBaseUrl()}/auth/profile`, {
          headers: { Authorization: `Bearer ${accessToken}` },
          credentials: "include",
        });
        const profile = await safeReadJson(profileResponse);
        if (!profileResponse.ok || !profile || typeof profile !== "object") {
          throw new Error("The social login profile could not be loaded.");
        }
        const userProfile = profile as {
          user_id: string;
          tenant_id: string;
          email: string;
          roles: string[];
        };
        if (!userProfile.user_id || !userProfile.tenant_id || !userProfile.email) {
          throw new Error("The social login profile was incomplete.");
        }
        if (!cancelled) {
          completeLogin(
            {
              access_token: accessToken,
              user: {
                user_id: userProfile.user_id,
                tenant_id: userProfile.tenant_id,
                roles: userProfile.roles,
              },
            },
            userProfile.email,
          );
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Social login could not be completed.");
          router.replace("/auth/login");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void finishOAuthLogin();
    return () => {
      cancelled = true;
    };
    // completeLogin intentionally uses the current form/session state and is
    // only invoked when an OAuth result is present in the callback URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  // 2FA challenge state
  const [show2fa, setShow2fa] = useState(false);
  const [oauthTwoFactor, setOauthTwoFactor] = useState(false);
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

  const completeLogin = (
    data: {
      access_token: string;
      user: { user_id: string; tenant_id: string; roles: string[] };
    },
    emailOverride?: string,
  ) => {
    const email = emailOverride || formData.email;
    // Save credentials if Remember Me is checked
    if (rememberMe) {
      localStorage.setItem("averqel_saved_email", email);
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
        email,
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
        setOauthTwoFactor(false);
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
      const response = await fetch(
        `${getApiBaseUrl()}${oauthTwoFactor ? "/auth/oauth/2fa/verify" : "/auth/2fa/verify"}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(
            oauthTwoFactor ? { code: totpCode } : { pending_token: pendingToken, code: totpCode },
          ),
        },
      );

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

      const tokenData = data as {
        access_token: string;
        user: { user_id: string; tenant_id: string; roles: string[] };
      };
      let emailOverride: string | undefined;
      if (oauthTwoFactor) {
        const profileResponse = await fetch(`${getApiBaseUrl()}/auth/profile`, {
          headers: { Authorization: `Bearer ${tokenData.access_token}` },
          credentials: "include",
        });
        const profile = await safeReadJson(profileResponse);
        if (
          !profileResponse.ok ||
          !profile ||
          typeof profile !== "object" ||
          !("email" in profile)
        ) {
          throw new Error("The social login profile could not be loaded.");
        }
        const profileEmail = (profile as { email?: unknown }).email;
        if (typeof profileEmail !== "string" || !profileEmail) {
          throw new Error("The social login profile was incomplete.");
        }
        emailOverride = profileEmail;
      }
      completeLogin(tokenData, emailOverride);
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

              <div className="mb-6 grid gap-3 sm:grid-cols-2">
                <a
                  href={`${getApiBaseUrl()}/auth/oauth/google/start?return_to=%2Fauth%2Flogin`}
                  className="border-glass-border bg-surface-1 text-foreground hover:border-primary/60 hover:bg-surface-2 flex min-h-14 items-center justify-center rounded-lg border px-4 py-3 text-sm leading-tight font-semibold transition-colors"
                >
                  <span className="flex items-center gap-2.5">
                    <GoogleMark />
                    <span>Continue with Google</span>
                  </span>
                </a>
                <a
                  href={`${getApiBaseUrl()}/auth/oauth/github/start?return_to=%2Fauth%2Flogin`}
                  className="border-glass-border bg-surface-1 text-foreground hover:border-primary/60 hover:bg-surface-2 flex min-h-14 items-center justify-center rounded-lg border px-4 py-3 text-sm leading-tight font-semibold transition-colors"
                >
                  <span className="flex items-center gap-2.5">
                    <Github aria-hidden="true" className="h-5 w-5 shrink-0" strokeWidth={2} />
                    <span>Continue with GitHub</span>
                  </span>
                </a>
              </div>

              <div className="text-muted-foreground mb-6 flex items-center gap-3 text-[10px] font-semibold tracking-[0.2em] uppercase">
                <span className="bg-glass-border h-px flex-1" />
                <span>or use email</span>
                <span className="bg-glass-border h-px flex-1" />
              </div>

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
                  setOauthTwoFactor(false);
                  setPendingToken("");
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
