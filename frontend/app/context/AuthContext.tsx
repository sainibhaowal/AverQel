"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
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
  display_name?: string | null;
  avatar?: string | null;
  account_status?: string;
  totp_enabled?: boolean;
  onboarding_completed?: boolean;
}

interface ProfileResponse {
  user_id: string;
  tenant_id: string;
  email: string;
  roles: string[];
  display_name: string | null;
  avatar: string | null;
  status: string;
  totp_enabled: boolean;
  onboarding_completed: boolean;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  profileReady: boolean;
  userDisabled: boolean;
  login: (token: string, tenantId: string, user: User, remember?: boolean) => void;
  updateUserProfile: (profile: Partial<User>) => void;
  refreshProfile: () => Promise<ProfileResponse>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [profileLoadedUserId, setProfileLoadedUserId] = useState<string | null>(null);
  const [userDisabled, setUserDisabled] = useState(false);
  const profileReady = !user?.id || profileLoadedUserId === user.id;

  const updateUserProfile = useCallback((profile: Partial<User>) => {
    setUser((current) => (current ? { ...current, ...profile } : current));
  }, []);

  const refreshProfile = useCallback(async (): Promise<ProfileResponse> => {
    const response = (await fetchWithAuth("/auth/profile")) as Response;
    if (!response.ok) throw new Error("Could not load your account profile.");
    const profile = (await response.json()) as ProfileResponse;
    if (
      typeof profile.user_id !== "string" ||
      typeof profile.tenant_id !== "string" ||
      typeof profile.email !== "string" ||
      !Array.isArray(profile.roles)
    ) {
      throw new Error("The account profile response was invalid.");
    }
    setUser((current) =>
      current && current.id === profile.user_id
        ? {
            ...current,
            email: profile.email,
            tenant_id: profile.tenant_id,
            roles: profile.roles.filter((role): role is string => typeof role === "string"),
            display_name: profile.display_name,
            avatar: profile.avatar,
            account_status: profile.status,
            totp_enabled: profile.totp_enabled,
            onboarding_completed: profile.onboarding_completed,
          }
        : current,
    );
    return profile;
  }, []);

  useEffect(() => {
    if (!user) return;
    localStorage.setItem("averqel_user", JSON.stringify(user));
  }, [user]);

  useEffect(() => {
    if (!user?.id) return;

    let active = true;
    void Promise.resolve()
      .then(() => refreshProfile())
      .catch(() => undefined)
      .finally(() => {
        if (active) setProfileLoadedUserId(user.id);
      });
    return () => {
      active = false;
    };
  }, [user?.id, refreshProfile]);

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
              display_name?: unknown;
              avatar?: unknown;
              status?: unknown;
              totp_enabled?: unknown;
              onboarding_completed?: unknown;
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
                display_name:
                  typeof profile.display_name === "string" ? profile.display_name : null,
                avatar: typeof profile.avatar === "string" ? profile.avatar : null,
                account_status: typeof profile.status === "string" ? profile.status : undefined,
                totp_enabled:
                  typeof profile.totp_enabled === "boolean" ? profile.totp_enabled : undefined,
                onboarding_completed:
                  typeof profile.onboarding_completed === "boolean"
                    ? profile.onboarding_completed
                    : undefined,
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
    setProfileLoadedUserId(null);
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
    setProfileLoadedUserId(null);
    setUser(null);
    setUserDisabled(false);

    try {
      await serverLogout;
    } catch (err) {
      console.warn("Server logout was unavailable; local session was cleared.", err);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        profileReady,
        userDisabled,
        login,
        updateUserProfile,
        refreshProfile,
        logout,
      }}
    >
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
