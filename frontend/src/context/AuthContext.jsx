import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { clearToken, fetchMe, getToken, loginRequest, setToken } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // If a token is already saved, we're "checking" it with the server on first load.
  const [checking, setChecking] = useState(() => Boolean(getToken()));

  useEffect(() => {
    if (!getToken()) return;
    fetchMe()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setChecking(false));
  }, []);

  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener("agriaura:unauthorized", onUnauthorized);
    return () => window.removeEventListener("agriaura:unauthorized", onUnauthorized);
  }, []);

  const login = useCallback(async (username, password) => {
    const token = await loginRequest(username, password);
    setToken(token);
    try {
      setUser(await fetchMe());
    } catch (err) {
      clearToken();
      throw err;
    }
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, checking, login, logout }),
    [user, checking, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}