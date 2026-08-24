"use client";

import { createContext, useContext, useEffect, useState } from "react";
import {
  fetchWithAuth,
  getAccessTokenExpiry,
  getRequestTenantId,
  invalidateAuthSession,
  isDesktopEnvironment,
  refreshAccessToken,
  resetAuthSessionState,
  shouldRefreshAccessToken,
} from "../../lib/api";

interface User {
  id: string;
  email: string;
  tenant_id: string;
  roles: string[];
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  userDisabled: boolean;
  login: (token: string, tenantId: string, user: User, remember?: boolean) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [userDisabled, setUserDisabled] = useState(false);

  useEffect(() => {
    const clearClientSession = () => {
      invalidateAuthSession({ broadcast: false, notify: false });
      setUser(null);
      setUserDisabled(false);
    };

    let cancelled = false;

    const bootstrapSession = async () => {
      const desktopSession = isDesktopEnvironment();
      let storedToken = localStorage.getItem("averqel_token");
      const storedUser = localStorage.getItem("averqel_user");
      const storedRemember = localStorage.getItem("averqel_remember") === "true";

      // Electron keeps the secure refresh cookie in its session cookie store.
      // Recover a missing access token from that cookie before showing login.
      if (!storedToken && desktopSession) {
        storedToken = await refreshAccessToken(null);
      }

      const tokenExpiry = getAccessTokenExpiry(storedToken);

      if (storedToken && tokenExpiry === null) {
        clearClientSession();
        if (!cancelled) {
          setLoading(false);
        }
        return;
      }

      if (
        storedToken &&
        tokenExpiry &&
        tokenExpiry <= Date.now() &&
        !storedRemember &&
        !desktopSession
      ) {
        clearClientSession();
        if (!cancelled) {
          setLoading(false);
        }
        return;
      }

      if (storedToken && shouldRefreshAccessToken(storedToken)) {
        const refreshedToken = await refreshAccessToken(getRequestTenantId(storedToken));
        if (!refreshedToken) {
          clearClientSession();
          if (!cancelled) {
            setLoading(false);
          }
          return;
        }
        storedToken = refreshedToken;
      }

      if (cancelled) {
        return;
      }

      let restoredUser: User | null = null;
      if (storedUser) {
        try {
          restoredUser = JSON.parse(storedUser) as User;
        } catch {
          clearClientSession();
        }
      }

      // Verify the account on every desktop launch so disabled/deleted users
      // do not continue with stale local profile data. A temporary profile
      // outage does not discard an otherwise valid cached session.
      if (desktopSession && storedToken) {
        try {
          const profileResponse = (await fetchWithAuth("/auth/profile", {
            timeoutMs: 15_000,
          })) as Response;
          if (profileResponse.status === 401 || profileResponse.status === 404) {
            clearClientSession();
            if (!cancelled) {
              setLoading(false);
            }
            return;
          }
          if (profileResponse.ok) {
            const profile = (await profileResponse.json()) as {
              user_id?: unknown;
              tenant_id?: unknown;
              email?: unknown;
              roles?: unknown;
            };
            if (
              typeof profile.user_id === "string" &&
              typeof profile.tenant_id === "string" &&
              typeof profile.email === "string" &&
              Array.isArray(profile.roles)
            ) {
              restoredUser = {
                id: profile.user_id,
                email: profile.email,
                tenant_id: profile.tenant_id,
                roles: profile.roles.filter((role): role is string => typeof role === "string"),
              };
              localStorage.setItem("averqel_user", JSON.stringify(restoredUser));
              localStorage.setItem("averqel_tenant_id", restoredUser.tenant_id);
            }
          }
        } catch {
          // Keep a cached user during a transient network outage. Protected
          // API calls remain responsible for detecting a genuinely invalid
          // session and redirecting to login.
        }
      }

      if (restoredUser) {
        setUser(restoredUser);
      }

      if (!cancelled) {
        setLoading(false);
      }
    };

    void bootstrapSession();

    const handleUnauthorized = () => {
      clearClientSession();
    };

    const handleUserDisabled = () => {
      setUserDisabled(true);
    };

    const handleStorage = (event: StorageEvent) => {
      if (event.key === "averqel_user") {
        try {
          setUser(event.newValue ? JSON.parse(event.newValue) : null);
        } catch {
          clearClientSession();
        }
        setUserDisabled(false);
      }
      if (event.key === "averqel_token") {
        if (event.newValue) {
          resetAuthSessionState();
        } else {
          clearClientSession();
        }
      }
    };

    window.addEventListener("averqel_unauthorized", handleUnauthorized);
    window.addEventListener("averqel_user_disabled", handleUserDisabled);
    window.addEventListener("storage", handleStorage);

    return () => {
      cancelled = true;
      window.removeEventListener("averqel_unauthorized", handleUnauthorized);
      window.removeEventListener("averqel_user_disabled", handleUserDisabled);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  const login = (token: string, tenantId: string, userData: User, remember: boolean = false) => {
    const persistentSession = remember || isDesktopEnvironment();
    resetAuthSessionState();
    localStorage.setItem("averqel_token", token);
    localStorage.setItem("averqel_tenant_id", tenantId);
    localStorage.setItem("averqel_user", JSON.stringify(userData));
    localStorage.setItem("averqel_remember", persistentSession ? "true" : "false");
    setUser(userData);
    setUserDisabled(false);
  };

  const logout = async () => {
    // Clear the local session first. Logout must remain usable when the API,
    // proxy, or refresh-token endpoint is unavailable.
    const serverLogout = fetchWithAuth("/auth/logout", {
      method: "POST",
      timeoutMs: 5_000,
      _skipAuthRefresh: true,
    });

    invalidateAuthSession({ broadcast: false, notify: false });
    setUser(null);
    setUserDisabled(false);

    try {
      await serverLogout;
    } catch (err) {
      console.warn("Server logout was unavailable; local session was cleared.", err);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, userDisabled, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
