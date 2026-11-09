// Who is logged in. Holds the token and the /auth/me profile for the whole app.

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";
import type { Me } from "./types";

type AuthState = {
  me: Me | null;
  ready: boolean; // false while we check a saved token on first load
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  const logout = useCallback(() => {
    setToken(null);
    setMe(null);
  }, []);

  const refreshMe = useCallback(async () => {
    setMe(await api<Me>("/auth/me"));
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout); // an expired token anywhere sends us back to login
    if (!getToken()) {
      setReady(true);
      return;
    }
    refreshMe()
      .catch(logout)
      .finally(() => setReady(true));
  }, [logout, refreshMe]);

  const login = useCallback(
    async (username: string, password: string) => {
      const { access_token } = await api<{ access_token: string }>("/auth/login", {
        method: "POST",
        body: { username, password },
      });
      setToken(access_token);
      await refreshMe();
    },
    [refreshMe],
  );

  return <AuthContext.Provider value={{ me, ready, login, logout, refreshMe }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
