import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { bootstrapAuthSession, registerAuthListener, setInMemoryAccessToken, type AuthSession, type UserData } from './api';

interface AuthContextValue {
  session: AuthSession | null;
  user: UserData | null;
  accessToken: string | null;
  isLoading: boolean;
  setSession: (session: AuthSession | null) => void;
  setUser: (user: UserData | null) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSessionState] = useState<AuthSession | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    registerAuthListener((nextSession) => {
      setSessionState(nextSession);
    });

    let cancelled = false;

    void bootstrapAuthSession()
      .then((nextSession) => {
        if (!cancelled) {
          setSessionState(nextSession);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSessionState(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
      registerAuthListener(null);
    };
  }, []);

  const setSession = (nextSession: AuthSession | null) => {
    setInMemoryAccessToken(nextSession?.access_token ?? null);
    setSessionState(nextSession);
  };

  const setUser = (user: UserData | null) => {
    if (!user) {
      setInMemoryAccessToken(null);
      setSessionState(null);
      return;
    }

    setSessionState((current) => {
      if (!current) return null;
      return { ...current, user };
    });
  };

  const logout = () => {
    setInMemoryAccessToken(null);
    setSessionState(null);
  };

  return (
    <AuthContext.Provider
      value={{
        session,
        user: session?.user ?? null,
        accessToken: session?.access_token ?? null,
        isLoading,
        setSession,
        setUser,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
