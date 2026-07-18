"use client";

import { createContext, useContext, useEffect, useState } from "react";
import {
  fetchWithAuth,
  getAccessTokenExpiry,
  invalidateAuthSession,
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
      const storedToken = localStorage.getItem("averqel_token");
      const storedUser = localStorage.getItem("averqel_user");
      const storedRemember = localStorage.getItem("averqel_remember") === "true";
      const tokenExpiry = getAccessTokenExpiry(storedToken);

      if (storedToken && tokenExpiry === null) {
        clearClientSession();
        if (!cancelled) {
          setLoading(false);
        }
        return;
      }

      if (storedToken && tokenExpiry && tokenExpiry <= Date.now() && !storedRemember) {
        clearClientSession();
        if (!cancelled) {
          setLoading(false);
        }
        return;
      }

      if (storedToken && shouldRefreshAccessToken(storedToken)) {
        const refreshedToken = await refreshAccessToken(localStorage.getItem("averqel_tenant_id"));
        if (!refreshedToken) {
          clearClientSession();
          if (!cancelled) {
            setLoading(false);
          }
          return;
        }
      }

      if (cancelled) {
        return;
      }

      if (storedUser) {
        try {
          setUser(JSON.parse(storedUser));
        } catch {
          clearClientSession();
        }
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
    resetAuthSessionState();
    localStorage.setItem("averqel_token", token);
    localStorage.setItem("averqel_tenant_id", tenantId);
    localStorage.setItem("averqel_user", JSON.stringify(userData));
    localStorage.setItem("averqel_remember", remember ? "true" : "false");
    setUser(userData);
    setUserDisabled(false);
  };

  const logout = async () => {
    try {
      await fetchWithAuth("/auth/logout", { method: "POST" });
    } catch (err) {
      console.error("Logout error:", err);
    } finally {
      invalidateAuthSession({ broadcast: false, notify: false });
      setUser(null);
      setUserDisabled(false);
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
