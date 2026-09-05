import { createContext, useContext, useEffect, useState } from "react";
import { fetchCurrentUser, login as loginRequest } from "../api/auth";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setIsLoading(false);
      return;
    }
    fetchCurrentUser()
      .then(setUser)
      .catch(() => localStorage.removeItem("access_token"))
      .finally(() => setIsLoading(false));
  }, []);

  async function login(email, password) {
    const { access_token } = await loginRequest({ email, password });
    localStorage.setItem("access_token", access_token);
    const currentUser = await fetchCurrentUser();
    setUser(currentUser);
  }

  async function loginWithToken(token) {
    localStorage.setItem("access_token", token);
    const currentUser = await fetchCurrentUser();
    setUser(currentUser);
  }

  function logout() {
    localStorage.removeItem("access_token");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, loginWithToken, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
