"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";

import { getCurrentUser, login as apiLogin, logout as apiLogout, UserRole } from "@/lib/api";

export type AuthUser = {
  username: string;
  role: UserRole;
};

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const response = await getCurrentUser();
      setUser(response.user);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const response = await apiLogin(username, password);
    setUser(response.user);
    return response.user;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout, refresh }),
    [user, loading, login, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}

export function ProtectedRoute({
  children,
  roles
}: {
  children: ReactNode;
  roles?: UserRole[];
}) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    if (roles && !roles.includes(user.role)) {
      router.replace("/app");
    }
  }, [loading, pathname, roles, router, user]);

  if (loading || !user || (roles && !roles.includes(user.role))) {
    return <div className="route-state">Sprawdzam dostęp...</div>;
  }

  return <>{children}</>;
}

export function useLoginTarget() {
  const searchParams = useSearchParams();
  return searchParams.get("next") || "/app";
}

export function resolvePostLoginTarget(user: AuthUser, requestedTarget: string) {
  if (user.role === "user") {
    return "/chat";
  }
  return requestedTarget || "/app";
}
